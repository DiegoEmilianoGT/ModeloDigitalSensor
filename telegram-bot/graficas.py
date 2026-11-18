import io
import time
from datetime import datetime

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    GRAFICAS_OK = True
except ImportError:
    GRAFICAS_OK = False

try:
    from PIL import Image, features

    WEBP_OK = features.check("webp")
except ImportError:
    WEBP_OK = False

from config import GRAFICAS, RANGOS, log
from comun import prometheus as prom
from comun.calibracion import calibrar, cargar_offsets
from comun.estilo import FONDO, TINTA, dar_estilo, leyenda_arriba, trazo
from comun.nombres import etiqueta
from telegram_api import TECLADO_GRAFICAS, avisar_accion, enviar_mensaje, reenviar_foto, subir
from texto import bloque

MENSAJE_GRAFICAS = "<b>Graficas</b>\nElige que medir y cuanto tiempo"

# (clave, rango) -> (momento, file_id, pie): la misma grafica pedida de nuevo se reenvia sin
# volver a consultarla, dibujarla ni subirla
enviadas = {}


def paso_de(rango):
    return max(15, RANGOS[rango] // 300)


def vigencia(rango):
    # mientras no cambie el dato mas reciente la grafica sigue siendo la misma
    return min(max(paso_de(rango), 30), 300)


def generar_grafica(clave, rango):
    """Devuelve (imagen, resumen). La imagen es de Pillow, o PNG ya codificado si no hay Pillow."""
    nombre, unidad, consulta = GRAFICAS[clave]
    fin = time.time()
    paso = paso_de(rango)
    series = prom.rango(consulta, fin - RANGOS[rango], fin, paso)
    if not series:
        return None, []

    series.sort(key=lambda s: (s["metric"].get("location", "?"), s["metric"]["__name__"]))
    nodos = sorted({s["metric"].get("location", "?") for s in series})
    offsets = cargar_offsets()
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=110, facecolor=FONDO)
    try:
        resumen = []
        for s in series:
            xs, ys, previo = [], [], None
            metrica = s["metric"]["__name__"]
            ubicacion = s["metric"].get("location", "?")
            for marca, v in s["values"]:
                t = float(marca)
                if previo is not None and t - previo > 4 * paso:
                    xs.append(datetime.fromtimestamp(previo + paso))
                    ys.append(float("nan"))  # corta si el nodo no reporta
                xs.append(datetime.fromtimestamp(t))
                ys.append(calibrar(offsets, ubicacion, metrica, float(v)))
                previo = t
            nombre_serie = etiqueta(ubicacion, metrica)
            ax.plot(xs, ys, label=nombre_serie, linewidth=1.6, **trazo(nodos, ubicacion, metrica))
            validos = [y for y in ys if y == y]
            if validos:
                detalle = f"{validos[-1]:.1f} {unidad}  (min {min(validos):.1f} / max {max(validos):.1f})"
                resumen.append((nombre_serie, detalle))
        fig.suptitle(f"{nombre} - ultimas {rango}", x=0.01, ha="left", fontsize=11, color=TINTA)
        dar_estilo(ax, unidad)
        leyenda_arriba(ax)
        localizador = mdates.AutoDateLocator()
        ax.xaxis.set_major_locator(localizador)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(localizador))
        fig.tight_layout()
        if not WEBP_OK:
            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            return buf.getvalue(), resumen
        fig.canvas.draw()
        ancho, alto = fig.canvas.get_width_height()
        lienzo = Image.frombuffer("RGBA", (ancho, alto), fig.canvas.buffer_rgba(), "raw", "RGBA", 0, 1)
        return lienzo.convert("RGB"), resumen
    finally:
        plt.close(fig)


def codificar(imagen, formato):
    if isinstance(imagen, bytes):  # ya es PNG
        return imagen
    buf = io.BytesIO()
    if formato == "webp":
        imagen.save(buf, "WEBP", quality=90, method=4)  # ~30 KB frente a ~80 KB del PNG
    else:
        imagen.save(buf, "PNG")
    return buf.getvalue()


def enviar_foto(chat_id, imagen, pie):
    """Sube la grafica y devuelve el file_id que le dio Telegram, o None si no se pudo."""
    global WEBP_OK
    formatos = ["webp", "png"] if WEBP_OK and not isinstance(imagen, bytes) else ["png"]
    for intento, formato in enumerate(formatos):
        respuesta = subir(chat_id, "sendPhoto", "photo", f"grafica.{formato}",
                          codificar(imagen, formato), f"image/{formato}", pie)
        fotos = (respuesta or {}).get("result", {}).get("photo")
        if not fotos:
            continue
        if intento:  # Telegram rechazo el WebP y acepto el PNG: no se vuelve a intentar
            log.warning("Telegram no acepto la grafica en WebP; desde ahora se envia en PNG")
            WEBP_OK = False
        return fotos[-1]["file_id"]
    return None


def enviar_grafica(chat_id, clave, rango):
    if not GRAFICAS_OK:
        enviar_mensaje(chat_id, "Las graficas no estan disponibles.")
        return
    if clave not in GRAFICAS or rango not in RANGOS:
        enviar_mensaje(chat_id, MENSAJE_GRAFICAS, TECLADO_GRAFICAS)
        return
    guardada = enviadas.get((clave, rango))
    if guardada and time.time() - guardada[0] < vigencia(rango):
        if reenviar_foto(chat_id, guardada[1], guardada[2]) is not None:
            return
    avisar_accion(chat_id, "upload_photo")
    try:
        imagen, resumen = generar_grafica(clave, rango)
    except prom.ERRORES as exc:
        log.warning("No se pudo generar la grafica: %s", exc)
        enviar_mensaje(chat_id, "No se pudo generar la grafica.")
        return
    if imagen is None:
        enviar_mensaje(chat_id, "Sin datos para ese rango.")
        return
    pie = bloque(f"{GRAFICAS[clave][0]} - ultimas {rango}", resumen)
    file_id = enviar_foto(chat_id, imagen, pie)
    if file_id is None:
        enviar_mensaje(chat_id, "No se pudo enviar la grafica, intenta de nuevo.")
        return
    enviadas[(clave, rango)] = (time.time(), file_id, pie)
