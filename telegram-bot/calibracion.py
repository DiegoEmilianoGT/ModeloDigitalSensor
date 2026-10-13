import os
import json
import re
import requests

from config import ADMIN_CHAT_IDS, PROMETHEUS_URL, log, MEDIDAS
from prometheus_api import ERRORES_PROM
from telegram_api import enviar_mensaje


RUTA_OFFSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "calibracion.json")
RUTA_REGLAS_PROM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prometheus", "calibracion_sensor.yml")
SENSORES = ("bme280", "dht22")

def cargar_offsets():
    try:
        with open(RUTA_OFFSETS, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("No se pudo cargar el archivo de offsets: %s", exc)
        return {}
    
def calibrar(metrica, valor):
    return round(valor + cargar_offsets().get(metrica, 0.0), 2)

def guardar_offsets(metrica, offset):
    offsets = cargar_offsets()
    offsets[metrica] = offset
    tmp = RUTA_OFFSETS + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(offsets, f, ensure_ascii=False, indent=4)
        os.replace(tmp, RUTA_OFFSETS)
    except Exception as exc:
        log.warning("No se pudo guardar el archivo: %s", exc)

def actualizar_regla_prometheus(metrica, offset):
    with open(RUTA_REGLAS_PROM, encoding="utf-8") as f:
        contenido =f.read()
    patron = rf"(record: {metrica}_calibrada\s*\n\s*expr: {metrica} \+ )[\d.+-]+"
    nuevo, n = re.subn(patron, rf"\g<1>{offset}", contenido)
    if n == 0:
        raise ValueError(f"No se encontro la regla de calibracion")
    with open(RUTA_REGLAS_PROM, "w", encoding="utf-8") as f:
        f.write(nuevo)


def recargar_prometheus():
    requests.post(f"{PROMETHEUS_URL}/-/reload", timeout=10).raise_for_status()

def calibrar_y_propagar(metrica, offset):
    guardar_offsets(metrica, offset)
    actualizar_regla_prometheus(metrica, offset)
    recargar_prometheus()
    log.info("Calibracion actualizada: %s = %+g", metrica, offset)

def comando_calibrar(chat_id, args):
    if chat_id not in ADMIN_CHAT_IDS:
        enviar_mensaje(chat_id, "No tienes permisos para calibrar sensores.")
        return
    if len(args) != 3:
        enviar_mensaje(chat_id, "Uso: /calibrar <sensor> <medida> <offset>")
        return
    sensor, medida, texto_offset = args[0].lower(), args[1].lower(), args[2]
    if sensor not in SENSORES or medida not in ("temp", "humedad"):
        enviar_mensaje(chat_id, f"Sensor o medida no reconocida.")
        return
    try:
        offset = float(texto_offset)
    except ValueError:
        enviar_mensaje(chat_id, f"Offset no es un número válido.")
        return
    metrica = f"{sensor}_{MEDIDAS[medida][0]}"
    if metrica not in cargar_offsets():
        enviar_mensaje(chat_id, f"No se encontró la métrica {metrica} para calibrar.")
        return
    try:
        calibrar_y_propagar(metrica, offset)
    except (OSError, ValueError, *ERRORES_PROM) as exc:
        enviar_mensaje(chat_id, f"Error al calibrar: {exc}")
        return
    enviar_mensaje(chat_id, f"Calibración aplicada")