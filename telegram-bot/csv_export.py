import csv
import io
import time
import os
from datetime import datetime

from config import CSV_DIAS, CSV_METRICAS, CSV_PASO, CSV_VENTANA, ETIQUETAS, log
from prometheus_api import ERRORES_PROM, prom_get
from telegram_api import enviar_archivo, enviar_mensaje
from texto import acortar
from calibracion import calibrar

RUTA_DATASET_ANALISIS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analisis", "datos", "dataset_sensores.csv")

def leer_recuperadas():
    if not os.path.exists(RUTA_DATASET_ANALISIS):
        return {}
    limite =  time.time() - CSV_DIAS * 24 * 3600
    filas = {}
    with open(RUTA_DATASET_ANALISIS, newline="", encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            ts = datetime.strptime(fila["Times"], "%Y-%m-%d %H:%M:%S").timestamp()
            if ts < limite:
                continue
            for columna, valor in fila.items():
                if columna == "Times" or valor == "":
                    continue
                ubicacion, _, metrica = columna.partition(" -_")
                if metrica not in CSV_METRICAS:
                    continue
                nombre, unidad = ETIQUETAS[metrica]
                columna_bot = f"{ubicacion} - {nombre} ({unidad})"
                filas.setdefault(int(ts), {})[columna_bot] = calibrar(metrica, float(valor))
    return filas

def armar_csv():
    consulta = '{__name__=~"%s"}' % "|".join(CSV_METRICAS)
    fin = int(time.time())
    inicio = fin - CSV_DIAS * 24 * 3600
    filas = {}
    columnas = set()

    for desde in range(inicio, fin, CSV_VENTANA):
        hasta = min(desde + CSV_VENTANA, fin)
        series = prom_get("query_range", timeout=20, query=consulta, start=desde, end=hasta, step=CSV_PASO)["result"]
        for s in series:
            metrica = s["metric"]["__name__"]
            nombre, unidad = ETIQUETAS[metrica]
            columna = f"{acortar(s['metric'].get('location', '?'))} - {nombre} ({unidad})"
            columnas.add(columna)
            for t, v in s["values"]:
                filas.setdefault(int(t), {})[columna] = calibrar(metrica, float(v))

    for ts, valores in leer_recuperadas().items():
        destino = filas.setdefault(ts, {})
        for columna, valor in valores.items():
            destino.setdefault(columna, valor)
        columnas.update(valores.keys())

    if not filas:
        return None

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["Times"] + sorted(columnas), restval="")
    writer.writeheader()
    for ts in sorted(filas):
        writer.writerow({"Times": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"), **filas[ts]})
    return buffer.getvalue().encode("utf-8-sig")  # Excel "°"


def exportar_csv(chat_id):
    enviar_mensaje(chat_id, f"Generando CSV de los ultimos {CSV_DIAS} dias")
    try:
        contenido = armar_csv()
    except ERRORES_PROM as exc:
        log.warning("No se pudo generar CSV: %s", exc)
        enviar_mensaje(chat_id, "No se pudo generar el CSV (Prometheus no respondio).")
        return
    if contenido is None:
        enviar_mensaje(chat_id, "No hay datos para generar CSV.")
        return
    nombre = f"sensores_{datetime.now():%Y-%m-%d}.csv"
    pie = f"Datos de sensores: ultimos {CSV_DIAS} dias"
    enviar_archivo(chat_id, "sendDocument", "document", nombre, contenido, "text/csv", pie)
