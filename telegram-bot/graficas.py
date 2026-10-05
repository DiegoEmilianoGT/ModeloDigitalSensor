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

from config import GRAFICAS, RANGOS, log
from prometheus_api import ERRORES_PROM, prom_get
from telegram_api import TECLADO_GRAFICAS, enviar_archivo, enviar_mensaje
from texto import acortar, bloque

MENSAJE_GRAFICAS = "<b>Graficas</b>\nElige que medir y cuanto tiempo"


def generar_grafica(clave, rango):
    nombre, unidad, consulta = GRAFICAS[clave]
    segundos = RANGOS[rango]
    fin = time.time()
    paso = max(15, segundos // 300)
    series = prom_get("query_range", timeout=20, query=consulta, start=fin - segundos, end=fin, step=paso)["result"]
    if not series:
        return None, []

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=110)
    try:
        resumen = []
        for s in series:
            xs, ys, previo = [], [], None
            for t, v in s["values"]:
                t = float(t)
                if previo is not None and t - previo > 4 * paso:
                    xs.append(datetime.fromtimestamp(previo + paso))
                    ys.append(float("nan"))  # corta si el nodo no reporta
                xs.append(datetime.fromtimestamp(t))
                ys.append(float(v))
                previo = t
            etiqueta = acortar(s["metric"].get("location", "?"))
            ax.plot(xs, ys, label=etiqueta, linewidth=1.6)
            validos = [y for y in ys if y == y]
            if validos:
                detalle = f"{validos[-1]:.1f} {unidad}  (min {min(validos):.1f} / max {max(validos):.1f})"
                resumen.append((etiqueta, detalle))
        ax.set_title(f"{nombre} - ultimas {rango}")
        ax.set_ylabel(unidad)
        ax.grid(alpha=0.3)
        localizador = mdates.AutoDateLocator()
        ax.xaxis.set_major_locator(localizador)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(localizador))
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue(), resumen
    finally:
        plt.close(fig)


def enviar_grafica(chat_id, clave, rango):
    if not GRAFICAS_OK:
        enviar_mensaje(chat_id, "Las graficas no estan disponibles.")
        return
    if clave not in GRAFICAS or rango not in RANGOS:
        enviar_mensaje(chat_id, MENSAJE_GRAFICAS, TECLADO_GRAFICAS)
        return
    try:
        png, resumen = generar_grafica(clave, rango)
    except ERRORES_PROM as exc:
        log.warning("No se pudo generar la grafica: %s", exc)
        enviar_mensaje(chat_id, "No se pudo generar la grafica (Prometheus no respondio).")
        return
    if png is None:
        enviar_mensaje(chat_id, "Sin datos para ese rango.")
        return
    pie = bloque(f"{GRAFICAS[clave][0]}- ultimas {rango}", resumen)
    enviar_archivo(chat_id, "sendPhoto", "photo", "grafica.png", png, "image/png", pie)
