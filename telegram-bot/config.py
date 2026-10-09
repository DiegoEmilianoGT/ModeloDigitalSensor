#Configuracion: variables de entorno, constantes y textos

import logging
import os
import tempfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram-bot")

os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "telegram-bot-mpl"))

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_CHAT_IDS = {c.strip() for c in os.environ["TELEGRAM_ALLOWED_CHAT_IDS"].split(",") if c.strip()}
USUARIOS_PATH = os.environ.get("TELEGRAM_USERS_FILE",
                                os.path.join(os.path.dirname(os.path.abspath(__file__)), "usuarios.json"))
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
CHECK_INTERVAL_SEC = int(os.environ.get("CHECK_INTERVAL_SEC", "30"))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "300"))

ETIQUETAS = {
    "bme280_sensor_up": ("Sensor", None),
    "bme280_temperatura_celsius": ("Temperatura", "°C"),
    "bme280_humedad_porcentaje": ("Humedad", "%"),
    "bme280_presion_hpa": ("Presion", "hPa"),
    "bme280_wifi_rssi_dbm": ("RSSI", "dBm"),
    "dht22_sensor_up": ("Sensor", None),
    "dht22_temperatura_celsius": ("Temperatura", "°C"),
    "dht22_humedad_porcentaje": ("Humedad", "%"),
    "dht22_wifi_rssi_dbm": ("RSSI", "dBm"),
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

TITULOS = {
    "NodoCaido": "Nodo caido",
    "SensorSinLectura": "Sensor sin lectura",
    "TemperaturaAlta": "Temperatura alta",
    "TemperaturaBaja": "Temperatura baja",
    "HumedadAlta": "Humedad alta",
    "HumedadBaja": "Humedad baja",
    "PresionFueraDeRango": "Presion fuera de rango"
}

CSV_DIAS = 7
CSV_PASO = 15
CSV_VENTANA = CSV_PASO * 10_000  # Prometheus por bloques
CSV_METRICAS = (
    "bme280_temperatura_celsius", "bme280_humedad_porcentaje", "bme280_presion_hpa",
    "dht22_temperatura_celsius", "dht22_humedad_porcentaje",
)

AYUDA = (
    "<b>SrSensor</b> - monitoreo de sensores\n"
    "Usa los botones o los comandos:\n"
    "/estado - resumen de todos los nodos\n"
    "/alertas - alertas activas\n"
    "/temp /humedad /presion /rssi - lecturas actuales\n"
    "/grafica temp|hum|pres 1h|6h|24h\n"
    f"/csv - exporta los ultimos {CSV_DIAS} dias en CSV\n"
    "/silenciar - pausa los avisos\n"
    "/activar - reanuda los avisos"
)

SIN_ACCESO = (
    "No tienes acceso a este bot.\n"
    "Escribe /solicitar para pedirlo; un administrador lo debe aprobar."
)

COMANDOS_BOT = [
    ("menu", "Menu"),
    ("estado", "Estado de los nodos"),
    ("alertas", "Alertas activas"),
    ("temp", "Temperatura actual"),
    ("humedad", "Humedad actual"),
    ("presion", "Presion actual"),
    ("rssi", "Senal WiFi actual"),
    ("grafica", "Grafica"),
    ("csv", "Exportar CSV"),
    ("silenciar", "Silenciar avisos"),
    ("activar", "Reanudar avisos"),
]

COMANDOS_PUBLICOS = [("solicitar", "Pedir acceso al bot")]
COMANDOS_ADMIN = [
    ("usuarios", "Ver usuarios y solicitudes"),
    ("revocar", "Quitar el acceso a alguien"),
]
