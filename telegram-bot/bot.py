#!/usr/bin/env python3
"""Bot de Telegram para consultar y vigilar los nodos via Prometheus."""

import html
import io
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime

import requests

os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "telegram-bot-mpl"))
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    GRAFICAS_OK = True
except ImportError:
    GRAFICAS_OK = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram-bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_CHAT_IDS = {c.strip() for c in os.environ["TELEGRAM_ALLOWED_CHAT_IDS"].split(",") if c.strip()}
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
CHECK_INTERVAL_SEC = int(os.environ.get("CHECK_INTERVAL_SEC", "30"))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "300"))

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

ETIQUETAS = {
    "bme280_sensor_up": ("Sensor", None),
    "bme280_temperatura_celsius": ("Temperatura", "°C"),
    "bme280_humedad_porcentaje": ("Humedad", "%"),
    "bme280_presion_hpa": ("Presion", "hPa"),
    "bme280_alert_active": ("Alerta", None),
    "bme280_wifi_rssi_dbm": ("RSSI", "dBm"),
    "bme280_errores_total": ("Errores", ""),
    "dht22_sensor_up": ("Sensor", None),
    "dht22_temperatura_celsius": ("Temperatura", "°C"),
    "dht22_humedad_porcentaje": ("Humedad", "%"),
    "dht22_wifi_rssi_dbm": ("RSSI", "dBm"),
    "dht22_errores_total": ("Errores", ""),
}

GRAFICAS = {
    "temp": ("Temp", "°C", '{__name__=~"(bme280|dht22)_temperatura_celsius"}'),
    "hum": ("Hum", "%", '{__name__=~"(bme280|dht22)_humedad_porcentaje"}'),
    "pres": ("Presion", "hPa", "bme280_presion_hpa"),
}
RANGOS = {"1h": 3600, "6h": 6 * 3600, "24h": 24 * 3600}

MEDIDAS = {
    "temp": ("temperatura_celsius", "Temperatura", "°C"),
    "humedad": ("humedad_porcentaje", "Humedad", "%"),
    "presion": ("presion_hpa", "Presion", "hPa"),
    "rssi": ("wifi_rssi_dbm", "Senal WiFi", "dBm"),
}

esc = html.escape

NOMBRE_RE = re.compile(r"\b([a-z0-9]+)_[a-z0-9]+_(\d+)\b")
SANGRIA = " " * 4


def acortar(texto):
    return NOMBRE_RE.sub(lambda m: f"{m.group(1).upper()} #{int(m.group(2))}", texto)


def bloque(titulo, filas):
    ancho = max((len(k) for k, _ in filas), default=0)
    lineas = [titulo] + [f"  {k.ljust(ancho)}  {v}" for k, v in filas]
    return "<pre>" + esc("\n".join(lineas)) + "</pre>"


def sin_token(exc):
    return str(exc).replace(BOT_TOKEN, "<token>")


# Telegram

def telegram(metodo, timeout=15, **kwargs):
    try:
        resp = requests.post(f"{API_BASE}/{metodo}", timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        log.warning("Telegram %s: %s", metodo, sin_token(exc))
        return None
    if not resp.ok:
        log.warning("Telegram %s fallo: %s %s", metodo, resp.status_code, resp.text[:200])
        return None
    return resp.json()


def enviar_mensaje(chat_id, texto, teclado=None):
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if teclado:
        payload["reply_markup"] = teclado
    telegram("sendMessage", json=payload)


def avisar_a_todos(texto, teclado=None):
    for chat_id in ALLOWED_CHAT_IDS:
        enviar_mensaje(chat_id, texto, teclado)


def boton(texto, data):
    return {"text": texto, "callback_data": data}


FILAS_GRAFICAS = [
    [boton(f"{nombre} {rango}", f"graf:{clave}:{rango}") for rango in RANGOS]
    for clave, (nombre, _, _) in GRAFICAS.items()
]
TECLADO_GRAFICAS = {"inline_keyboard": FILAS_GRAFICAS}
TECLADO_MENU = {"inline_keyboard": [
    [boton("Estado", "cmd:estado"), boton("Alertas", "cmd:alertas")],
    [boton("Temperatura", "cmd:temp"), boton("Humedad", "cmd:humedad")],
    [boton("Presion", "cmd:presion"), boton("Senal WiFi", "cmd:rssi")],
] + FILAS_GRAFICAS + [
    [boton("Silenciar alertas", "cmd:silenciar"), boton("Activar alertas", "cmd:activar")],
]}


# Prometheus

def prom_query(expr):
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "success":
        return []
    return data["data"]["result"]


def prom_alertas():
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/alerts", timeout=10)
    resp.raise_for_status()
    return resp.json()["data"]["alerts"]


def leer_todo():
    """Devuelve ({location: {metrica: valor}}, {job: up})."""
    lecturas = {}
    try:
        resultados = prom_query('{__name__=~"(bme280|dht22)_.+"}')
    except requests.RequestException as exc:
        log.warning("No se pudieron consultar las metricas: %s", exc)
        resultados = []
    for r in resultados:
        metrica = r["metric"].get("__name__")
        if metrica not in ETIQUETAS:
            continue
        location = r["metric"].get("location", "desconocido")
        lecturas.setdefault(location, {})[metrica] = float(r["value"][1])

    jobs_up = {}
    try:
        for r in prom_query('up{job=~"bme280|dht22"}'):
            jobs_up[r["metric"].get("job", "?")] = float(r["value"][1])
    except requests.RequestException as exc:
        log.warning("No se pudo consultar up: %s", exc)

    return lecturas, jobs_up


# Consultas

def formatear_estado():
    lecturas, jobs_up = leer_todo()
    if not lecturas and not jobs_up:
        return "No se pudo contactar a Prometheus. Revisa que el servicio este activo."

    partes = []
    
    for location in sorted(lecturas):
        filas = []
        for metrica, (nombre, unidad) in ETIQUETAS.items():
            if metrica not in lecturas[location]:
                continue
            valor = lecturas[location][metrica]
            if metrica.endswith("_active"):
                texto = "ALERTA" if valor == 1 else "normal"
            elif metrica.endswith("_up"):
                texto = "En linea" if valor == 1 else "SIN RESPUESTA"
            elif metrica.endswith("_total"):
                texto = f"{valor:.0f}"
            else:
                texto = f"{valor:.2f} {unidad}"
            filas.append((nombre, texto))
        partes.append(bloque(acortar(location), filas))
    return "\n".join(partes)


def formatear_metrica(clave):
    sufijo, nombre, unidad = MEDIDAS[clave]
    lecturas, _ = leer_todo()
    filas = [
        (acortar(location), f"{valor:.2f} {unidad}")
        for location, valores in sorted(lecturas.items())
        for metrica, valor in valores.items()
        if metrica.endswith(sufijo)
    ]
    if not filas:
        return f"Sin datos de {nombre.lower()} por ahora."
    return bloque(nombre, filas)


# Alertas

estado_alertas = {}  
ultimo_aviso = {}     
alertas_silenciadas = False
alertas_inicializadas = False


TITULOS = {
    "NodoCaido": "Nodo caido",
    "SensorSinLectura": "Sensor sin lectura",
    "TemperaturaAlta": "Temperatura alta",
    "TemperaturaBaja": "Temperatura baja",
    "HumedadAlta": "Humedad alta",
    "HumedadBaja": "Humedad baja",
    "PresionFueraDeRango": "Presion fuera de rango",
    "SenalWiFiDebil": "Senal WiFi debil",
}


def parsear_iso(iso):
    try:
        return datetime.fromisoformat(re.sub(r"\.\d+", "", iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def hora_local(iso):
    dt = parsear_iso(iso)
    return dt.astimezone().strftime("%H:%M") if dt else "?"


def duracion(segundos):
    minutos = max(int(segundos // 60), 1)
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60} h {minutos % 60} min"


def clave_alerta(alerta):
    return json.dumps(alerta.get("labels", {}), sort_keys=True)


def info_alerta(alerta):
    labels = alerta.get("labels", {})
    notas = alerta.get("annotations", {})
    inicio = parsear_iso(alerta.get("activeAt"))
    return {
        "nombre": labels.get("alertname", "?"),
        "nodo": acortar(labels.get("nodo") or labels.get("location") or labels.get("job", "?").upper()),
        "ip": labels.get("instance", "").split(":")[0],
        "resumen": notas.get("resumen") or notas.get("summary") or "",
        "desde": hora_local(alerta.get("activeAt")),
        "desde_ts": inicio.timestamp() if inicio else None,
        "estado": alerta.get("state", "?"),
        "notificada": False,
    }


def linea_alerta(info):
    lineas = [f"<b>{esc(TITULOS.get(info['nombre'], info['nombre']))}: {esc(info['nodo'])}</b>"]
    if info["nombre"] == "NodoCaido":
        lineas.append(f"{SANGRIA}Sin respuesta desde las {info['desde']}")
        if info["ip"]:
            lineas.append(f"{SANGRIA}IP {esc(info['ip'])}")
    else:
        if info["resumen"]:
            lineas.append(f"{SANGRIA}{esc(acortar(info['resumen']))}")
        lineas.append(f"{SANGRIA}Desde las {info['desde']}")
    return "\n".join(lineas)


def linea_resuelta(info):
    if info["nombre"] == "NodoCaido":
        titulo, etiqueta = f"Nodo recuperado: {info['nodo']}", "Estuvo caido"
    else:
        titulo = f"Resuelto: {TITULOS.get(info['nombre'], info['nombre'])} - {info['nodo']}"
        etiqueta = "Duro"
    texto = f"<b>{esc(titulo)}</b>"
    if info["desde_ts"]:
        texto += f"\n{SANGRIA}{etiqueta} {duracion(time.time() - info['desde_ts'])}"
    return texto


def estado_silencio():
    if alertas_silenciadas:
        return "Alertas silenciadas. Usa /activar para reanudarlas."
    return "Las alertas estan activas."


def formatear_alertas():
    try:
        activas = [info_alerta(a) for a in prom_alertas()]
    except (requests.RequestException, ValueError, KeyError) as exc:
        log.warning("No se pudo consultar las alertas: %s", exc)
        return "No se pudo contactar a Prometheus."
    cuerpo = "\n\n".join(
        linea_alerta(info) + ("" if info["estado"] == "firing" else " (pendiente)")
        for info in sorted(activas, key=lambda i: i["nombre"])
    ) or "Sin alertas activas."
    return f"<b>Alertas</b>\n{cuerpo}\n\n{estado_silencio()}"


def revisar_alertas():
    global alertas_inicializadas
    try:
        crudas = prom_alertas()
    except (requests.RequestException, ValueError, KeyError) as exc:
        log.warning("No se pudo consultar las alertas: %s", exc)
        return  # Prometheus no respondio: no asumir que se resolvieron

    firing = {clave_alerta(a): info_alerta(a) for a in crudas if a.get("state") == "firing"}
    ahora = time.time()

    resueltas = []
    for clave in list(estado_alertas):
        if clave not in firing:
            info = estado_alertas.pop(clave)
            if info["notificada"]:
                resueltas.append(info)

    for clave, info in firing.items():
        if clave not in estado_alertas:
            info["notificada"] = not alertas_inicializadas  # al arrancar solo se registran
            estado_alertas[clave] = info
    alertas_inicializadas = True

    nuevas = []
    if not alertas_silenciadas:
        for clave, info in estado_alertas.items():
            if info["notificada"]:
                continue
            if info["nombre"] != "NodoCaido" and ahora - ultimo_aviso.get(clave, 0.0) < ALERT_COOLDOWN_SEC:
                continue  # el enfriamiento no aplica a caidas de nodo: siempre se avisan
            info["notificada"] = True
            ultimo_aviso[clave] = ahora
            nuevas.append(info)
    else:
        resueltas = []

    if not nuevas and not resueltas:
        return
    partes = [linea_alerta(i) for i in nuevas] + [linea_resuelta(i) for i in resueltas]
    avisar_a_todos("\n\n".join(partes))


def comando_silenciar(chat_id):
    global alertas_silenciadas
    alertas_silenciadas = True
    enviar_mensaje(chat_id, "Alertas silenciadas. Los comandos siguen funcionando; usa /activar para reanudarlas.")


def comando_activar(chat_id):
    global alertas_silenciadas
    alertas_silenciadas = False
    enviar_mensaje(chat_id, "Alertas activadas.")


#  Graficas

def generar_grafica(clave, rango):
    nombre, unidad, consulta = GRAFICAS[clave]
    segundos = RANGOS[rango]
    fin = time.time()
    paso = max(15, segundos // 300)
    resp = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query_range",
        params={"query": consulta, "start": fin - segundos, "end": fin, "step": paso},
        timeout=20,
    )
    resp.raise_for_status()
    series = resp.json()["data"]["result"]
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
                    ys.append(float("nan"))  # corta la linea donde el nodo no reporto
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


MENSAJE_GRAFICAS = "<b>Graficas</b>\nElige que medir y de cuanto tiempo"


def enviar_grafica(chat_id, clave, rango):
    if not GRAFICAS_OK:
        enviar_mensaje(chat_id, "Las graficas no estan disponibles (matplotlib no esta instalado).")
        return
    if clave not in GRAFICAS or rango not in RANGOS:
        enviar_mensaje(chat_id, MENSAJE_GRAFICAS, TECLADO_GRAFICAS)
        return
    try:
        png, resumen = generar_grafica(clave, rango)
    except (requests.RequestException, ValueError, KeyError) as exc:
        log.warning("No se pudo generar la grafica: %s", exc)
        enviar_mensaje(chat_id, "No se pudo generar la grafica (Prometheus no respondio).")
        return
    if png is None:
        enviar_mensaje(chat_id, "Sin datos para ese rango.")
        return
    pie = bloque(f"{GRAFICAS[clave][0]} - ultimas {rango}", resumen)
    telegram(
        "sendPhoto",
        timeout=30,
        data={"chat_id": chat_id, "caption": pie, "parse_mode": "HTML"},
        files={"photo": ("grafica.png", png, "image/png")},
    )


# Comandos

AYUDA = (
    "<b>SrSensor</b> - monitoreo de sensores\n"
    "Usa los botones o los comandos:\n"
    "/estado - resumen de todos los nodos\n"
    "/alertas - alertas activas\n"
    "/temp /humedad /presion /rssi - lecturas actuales\n"
    "/grafica temp|hum|pres 1h|6h|24h\n"
    "/silenciar - pausa los avisos\n"
    "/activar - reanuda los avisos"
)

COMANDOS_BOT = [
    ("menu", "Menu con botones"),
    ("estado", "Resumen de nodos"),
    ("alertas", "Alertas activas"),
    ("temp", "Temperatura actual"),
    ("humedad", "Humedad actual"),
    ("presion", "Presion actual"),
    ("rssi", "Senal WiFi actual"),
    ("grafica", "Grafica"),
    ("silenciar", "Silenciar avisos"),
    ("activar", "Reanudar avisos"),
]


def ejecutar(chat_id, accion, args):
    if accion == "estado":
        enviar_mensaje(chat_id, formatear_estado())
    elif accion == "alertas":
        enviar_mensaje(chat_id, formatear_alertas())
    elif accion in MEDIDAS:
        enviar_mensaje(chat_id, formatear_metrica(accion))
    elif accion in ("grafica", "graficas"):
        if len(args) >= 2:
            enviar_grafica(chat_id, args[0].lower(), args[1].lower())
        else:
            enviar_mensaje(chat_id, MENSAJE_GRAFICAS, TECLADO_GRAFICAS)
    elif accion == "silenciar":
        comando_silenciar(chat_id)
    elif accion == "activar":
        comando_activar(chat_id)
    else:
        enviar_mensaje(chat_id, AYUDA, TECLADO_MENU)


def parsear_comando(texto):
    partes = texto.strip().split()
    if not partes or not partes[0].startswith("/"):
        return "menu", []
    return partes[0][1:].split("@")[0].lower(), partes[1:]


def accion_de_callback(data):
    partes = data.split(":")
    if partes[0] == "cmd":
        return partes[1], []
    if partes[0] == "graf":
        return "grafica", partes[1:]
    return "menu", []


def procesar_update(update):
    cb = update.get("callback_query")
    if cb:
        chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
        if chat_id not in ALLOWED_CHAT_IDS:
            log.info("Boton ignorado de chat no autorizado: %s", chat_id)
            return
        telegram("answerCallbackQuery", json={"callback_query_id": cb["id"]})
        accion, args = accion_de_callback(cb.get("data", ""))
        log.info("Boton de %s: %s %s", chat_id, accion, args)
        ejecutar(chat_id, accion, args)
        return

    mensaje = update.get("message")
    if not mensaje or "text" not in mensaje:
        return
    chat_id = str(mensaje["chat"]["id"])
    if chat_id not in ALLOWED_CHAT_IDS:
        log.info("Mensaje ignorado de chat no autorizado: %s", chat_id)
        return
    accion, args = parsear_comando(mensaje["text"])
    log.info("Comando de %s: %s %s", chat_id, accion, args)
    ejecutar(chat_id, accion, args)


def registrar_comandos():
    telegram("setMyCommands", json={
        "commands": [{"command": c, "description": d} for c, d in COMANDOS_BOT]})


def bucle_principal():
    log.info("Bot iniciado. Chats permitidos: %s", ALLOWED_CHAT_IDS)
    if not GRAFICAS_OK:
        log.warning("matplotlib no esta instalado: /grafica deshabilitado")
    registrar_comandos()
    offset = 0
    ultima_verificacion = 0.0
    while True:
        if time.time() - ultima_verificacion >= CHECK_INTERVAL_SEC:
            ultima_verificacion = time.time()
            try:
                revisar_alertas()
            except Exception:
                log.exception("Error revisando alertas")

        datos = telegram(
            "getUpdates",
            timeout=25,
            json={"offset": offset, "timeout": 10, "allowed_updates": ["message", "callback_query"]},
        )
        if datos is None:
            time.sleep(5)
            continue

        for update in datos.get("result", []):
            offset = update["update_id"] + 1
            try:
                procesar_update(update)
            except Exception:
                log.exception("Error procesando update %s", update.get("update_id"))


if __name__ == "__main__":
    bucle_principal()

