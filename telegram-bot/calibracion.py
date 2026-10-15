import os
import json
import math
import requests

from config import ADMIN_CHAT_IDS, PROMETHEUS_URL, log, MEDIDAS
from prometheus_api import ERRORES_PROM, prom_query
from telegram_api import enviar_mensaje
from texto import bloque, esc


CARPETA_PROYECTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RUTA_OFFSETS = os.path.join(CARPETA_PROYECTO, "calibracion.json")
RUTA_REGLAS_PROM = os.path.join(CARPETA_PROYECTO, "prometheus", "calibracion_sensor.yml")
SENSORES = ("bme280", "dht22")
MEDIDAS_CALIBRABLES = ("temp", "humedad")
METRICAS_CALIBRABLES = [f"{s}_{MEDIDAS[m][0]}" for s in SENSORES for m in MEDIDAS_CALIBRABLES]
USO = (
    "/calibrar &lt;nodo&gt; &lt;temp|humedad&gt; &lt;offset&gt;\n\n"
    "/calibrar bme280_esp32c3_00 temp|humedad 00.00\n"
)


def leer_offsets():
    # nodo{metrica offset}
    try:
        with open(RUTA_OFFSETS, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def cargar_offsets():
    try:
        return leer_offsets()
    except (OSError, ValueError) as exc:
        log.warning("No se pudo cargar el archivo de offsets: %s", exc)
        return {}


def calibrar(offsets, nodo, metrica, valor):
    return round(valor + offsets.get(nodo, {}).get(metrica, 0.0), 2)


def generar_reglas(offsets):
    lineas = [
        "groups:",
        "  - name: calibracion",
        "    rules:",
    ]
    for metrica in METRICAS_CALIBRABLES:
        calibrados = sorted(n for n, m in offsets.items() if m.get(metrica, 0.0) != 0)
        terminos = [f'{metrica}{{location="{nodo}"}} + ({offsets[nodo][metrica]})' for nodo in calibrados]
        terminos.append(f"{metrica} + 0")
        lineas += [f"      - record: {metrica}_calibrada", "        expr: |-"]
        lineas += [f"          {'or ' if i else ''}{termino}" for i, termino in enumerate(terminos)]
    return "\n".join(lineas) + "\n"


def escribir(ruta, texto):
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        f.write(texto)
    os.replace(temporal, ruta)


def recargar_prometheus():
    requests.post(f"{PROMETHEUS_URL}/-/reload", timeout=10).raise_for_status()


def aplicar_offsets(offsets):
    with open(RUTA_REGLAS_PROM, encoding="utf-8") as f:
        anteriores = f.read()
    try:
        escribir(RUTA_REGLAS_PROM, generar_reglas(offsets))
        recargar_prometheus()
        escribir(RUTA_OFFSETS, json.dumps(offsets, ensure_ascii=False, indent=4) + "\n")
    except (OSError, requests.RequestException):
        escribir(RUTA_REGLAS_PROM, anteriores)
        try:
            recargar_prometheus() 
        except requests.RequestException as exc:
            log.warning("No se pudo recargar Prometheus con las reglas anteriores: %s", exc)
        raise


def nodos_y_sensores():
    # nodo: {sensores}
    nodos = {}
    for sensor in SENSORES:
        for r in prom_query(f"last_over_time({sensor}_sensor_up[30d])"):
            nodo = r["metric"].get("location")
            if nodo:
                nodos.setdefault(nodo, set()).add(sensor)
    return nodos


def texto_calibracion(offsets):
    filas = []
    for nodo in sorted(offsets):
        for metrica, valor in sorted(offsets[nodo].items()):
            medida = next((m for m in MEDIDAS_CALIBRABLES if metrica.endswith(MEDIDAS[m][0])), metrica)
            filas.append((nodo, f"{metrica.split('_')[0]} {medida} {valor:+g}"))
    return bloque("Calibracion actual", filas) if filas else "Todavia no hay offsets."


def comando_calibrar(chat_id, args):
    if chat_id not in ADMIN_CHAT_IDS:
        enviar_mensaje(chat_id, "No tienes permisos para calibrar sensores.")
        return
    if not args:
        enviar_mensaje(chat_id, f"{texto_calibracion(cargar_offsets())}\n{USO}")
        return
    if len(args) not in (3, 4):
        enviar_mensaje(chat_id, USO)
        return

    nodo = args[0].lower()
    sensor = args[1].lower() if len(args) == 4 else nodo.split("_")[0]
    medida, texto_offset = args[-2].lower(), args[-1].replace(",", ".")
    if sensor not in SENSORES:
        enviar_mensaje(chat_id, f"Indica el sensor ({' o '.join(SENSORES)}) para el nodo {esc(nodo)}.\n{USO}")
        return
    if medida not in MEDIDAS_CALIBRABLES:
        enviar_mensaje(chat_id, f"Medida no reconocida.\n{USO}")
        return
    try:
        offset = float(texto_offset)
    except ValueError:
        offset = math.nan
    if not math.isfinite(offset):
        enviar_mensaje(chat_id, "El offset no es un número válido.")
        return

    metrica = f"{sensor}_{MEDIDAS[medida][0]}"
    try:
        nodos = nodos_y_sensores()
        if sensor not in nodos.get(nodo, set()):
            conocidos = ", ".join(f"{n} ({'/'.join(sorted(s))})" for n, s in sorted(nodos.items()))
            enviar_mensaje(chat_id, esc(f"No hay datos de {sensor} en el nodo {nodo}."))
            return
        offsets = leer_offsets()
        offsets.setdefault(nodo, {})[metrica] = offset
        aplicar_offsets(offsets)
    except (OSError, *ERRORES_PROM) as exc:
        enviar_mensaje(chat_id, f"Error al calibrar: {esc(str(exc))}")
        return
    log.info("Calibracion actualizada: %s %s = %+g", nodo, metrica, offset)
    enviar_mensaje(chat_id, esc(f"Calibración aplicada"))
