#!/usr/bin/env python3
"""Bot de Telegram para consultar el estado de los nodos ESP32-C3 via Prometheus."""

import os
import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram-bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_CHAT_IDS = {c.strip() for c in os.environ["TELEGRAM_ALLOWED_CHAT_IDS"].split(",") if c.strip()}
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
CHECK_INTERVAL_SEC = int(os.environ.get("CHECK_INTERVAL_SEC", "30"))

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

METRICS = [
    "bme280_sensor_up",
    "bme280_temperatura_celsius",
    "bme280_humedad_porcentaje",
    "bme280_presion_hpa",
    "bme280_alert_active",
    "bme280_wifi_rssi_dbm",
    "dht22_sensor_up",
    "dht22_temperatura_celsius",
    "dht22_humedad_porcentaje",
    "dht22_wifi_rssi_dbm",
]

ETIQUETAS = {
    "bme280_sensor_up": ("BME280 activo", None),
    "bme280_temperatura_celsius": ("Temperatura", "°C"),
    "bme280_humedad_porcentaje": ("Humedad", "%"),
    "bme280_presion_hpa": ("Presion", "hPa"),
    "bme280_alert_active": ("Alerta", None),
    "bme280_wifi_rssi_dbm": ("RSSI", "dBm"),
    "dht22_sensor_up": ("DHT22 activo", None),
    "dht22_temperatura_celsius": ("Temperatura", "°C"),
    "dht22_humedad_porcentaje": ("Humedad", "%"),
    "dht22_wifi_rssi_dbm": ("RSSI", "dBm"),
}


def prom_query(expr: str):
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "success":
        return []
    return data["data"]["result"]


def leer_todo():
    """Devuelve {location: {metrica: valor}} y {job: up} para todos los nodos."""
    lecturas: dict[str, dict[str, float]] = {}
    for metrica in METRICS:
        try:
            resultados = prom_query(metrica)
        except requests.RequestException as exc:
            log.warning("No se pudo consultar %s: %s", metrica, exc)
            continue
        for r in resultados:
            location = r["metric"].get("location", "desconocido")
            valor = float(r["value"][1])
            lecturas.setdefault(location, {})[metrica] = valor

    jobs_up: dict[str, float] = {}
    try:
        for r in prom_query('up{job=~"bme280|dht22"}'):
            jobs_up[r["metric"].get("job", "?")] = float(r["value"][1])
    except requests.RequestException as exc:
        log.warning("No se pudo consultar up: %s", exc)

    return lecturas, jobs_up


def formatear_estado() -> str:
    lecturas, jobs_up = leer_todo()

    if not lecturas and not jobs_up:
        return "No se pudo contactar a Prometheus. Revisa que el servicio este activo."

    partes = ["*Conexion de los nodos*"]
    for job, valor in sorted(jobs_up.items()):
        estado = "en linea" if valor == 1 else "SIN RESPUESTA"
        partes.append(f"- {job}: {estado}")

    for location in sorted(lecturas.keys()):
        partes.append(f"\n*{location}*")
        for metrica, (nombre, unidad) in ETIQUETAS.items():
            if metrica not in lecturas[location]:
                continue
            valor = lecturas[location][metrica]
            if metrica.endswith("_up") or metrica.endswith("_active"):
                if metrica.endswith("_active"):
                    texto = "ALERTA" if valor == 1 else "normal"
                else:
                    texto = "si" if valor == 1 else "NO"
                partes.append(f"- {nombre}: {texto}")
            else:
                sufijo = f" {unidad}" if unidad else ""
                partes.append(f"- {nombre}: {valor:.2f}{sufijo}")

    return "\n".join(partes)


def formatear_metrica(sufijo: str, nombre_bonito: str) -> str:
    lecturas, _ = leer_todo()
    lineas = [f"*{nombre_bonito}*"]
    encontrado = False
    for location, valores in sorted(lecturas.items()):
        for metrica, valor in valores.items():
            if metrica.endswith(sufijo):
                encontrado = True
                lineas.append(f"- {location}: {valor:.2f}")
    if not encontrado:
        return f"Sin datos de {nombre_bonito.lower()} por ahora."
    return "\n".join(lineas)


AYUDA = (
    "Comandos disponibles:\n"
    "/estado - resumen completo de todos los nodos\n"
    "/temp - temperatura de cada nodo\n"
    "/humedad - humedad de cada nodo\n"
    "/presion - presion del BME280\n"
    "/rssi - senal WiFi de cada nodo\n"
    "/ayuda - este mensaje"
)


def manejar_comando(comando: str) -> str:
    if comando in ("/start", "/ayuda", "/help"):
        return AYUDA
    if comando == "/estado":
        return formatear_estado()
    if comando == "/temp":
        return formatear_metrica("temperatura_celsius", "Temperatura")
    if comando == "/humedad":
        return formatear_metrica("humedad_porcentaje", "Humedad")
    if comando == "/presion":
        return formatear_metrica("presion_hpa", "Presion")
    if comando == "/rssi":
        return formatear_metrica("wifi_rssi_dbm", "Senal WiFi")
    return "Comando no reconocido.\n\n" + AYUDA


def enviar_mensaje(chat_id: str, texto: str):
    try:
        requests.post(
            f"{API_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"},
            timeout=10,
        )
    except requests.RequestException as exc:
        log.warning("No se pudo enviar mensaje a %s: %s", chat_id, exc)


def avisar_a_todos(texto: str):
    for chat_id in ALLOWED_CHAT_IDS:
        enviar_mensaje(chat_id, texto)


ultimo_estado_up: dict[str, float] = {}  # job -> ultimo valor de up, para detectar transiciones


def verificar_caidas():
    lecturas, jobs_up = leer_todo()
    if not lecturas and not jobs_up:
        return  # Prometheus no respondio; no asumir que los nodos cayeron

    ahora = time.strftime("%Y-%m-%d %H:%M:%S")
    for r in prom_query('up{job=~"bme280|dht22"}'):
        job = r["metric"].get("job", "?")
        instance = r["metric"].get("instance", "?")
        valor = float(r["value"][1])
        anterior = ultimo_estado_up.get(job)

        if anterior == 1.0 and valor == 0.0:
            avisar_a_todos(
                f"*ALERTA: nodo caido*\n"
                f"- Job: `{job}`\n"
                f"- Instance: `{instance}`\n"
                f"- Hora: {ahora}\n"
                f"Revisa alimentacion, WiFi o cableado del sensor."
            )
        elif anterior == 0.0 and valor == 1.0:
            avisar_a_todos(
                f"*Recuperado: nodo en linea*\n"
                f"- Job: `{job}`\n"
                f"- Instance: `{instance}`\n"
                f"- Hora: {ahora}"
            )

        ultimo_estado_up[job] = valor


def bucle_principal():
    log.info("Bot iniciado. Chats permitidos: %s", ALLOWED_CHAT_IDS)
    offset = 0
    ultima_verificacion = 0.0
    while True:
        ahora = time.time()
        if ahora - ultima_verificacion >= CHECK_INTERVAL_SEC:
            ultima_verificacion = ahora
            try:
                verificar_caidas()
            except requests.RequestException as exc:
                log.warning("No se pudo verificar caidas: %s", exc)

        try:
            resp = requests.get(
                f"{API_BASE}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            log.warning("Error consultando Telegram: %s", exc)
            time.sleep(5)
            continue

        for update in data.get("result", []):
            offset = update["update_id"] + 1
            mensaje = update.get("message")
            if not mensaje or "text" not in mensaje:
                continue

            chat_id = str(mensaje["chat"]["id"])
            if chat_id not in ALLOWED_CHAT_IDS:
                log.info("Mensaje ignorado de chat no autorizado: %s", chat_id)
                continue

            comando = mensaje["text"].strip().split()[0].lower()
            log.info("Comando de %s: %s", chat_id, comando)
            respuesta = manejar_comando(comando)
            enviar_mensaje(chat_id, respuesta)


if __name__ == "__main__":
    bucle_principal()
