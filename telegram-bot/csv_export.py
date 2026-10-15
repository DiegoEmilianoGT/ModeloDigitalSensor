import csv
import io
import time
import os
from datetime import datetime

from config import CSV_DIAS, CSV_METRICAS, CSV_PASO, CSV_VENTANA, ETIQUETAS, log
from prometheus_api import ERRORES_PROM, prom_get
from telegram_api import enviar_archivo, enviar_mensaje
from texto import acortar, sensor_extra
from calibracion import calibrar, cargar_offsets

RUTA_DATASET_ANALISIS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analisis", "datos", "dataset_sensores.csv")
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"


def nombre_columna(ubicacion, metrica):
    nombre, unidad = ETIQUETAS[metrica]
    return f"{acortar(ubicacion)}{sensor_extra(ubicacion, metrica)} - {nombre} ({unidad})"


def leer_recuperadas(desde, offsets):
    if not os.path.exists(RUTA_DATASET_ANALISIS):
        return {}
    limite = datetime.fromtimestamp(desde).strftime(FORMATO_FECHA)
    filas = {}
    with open(RUTA_DATASET_ANALISIS, newline="", encoding="utf-8") as archivo:
        lector = csv.reader(archivo)
        columnas = []
        for indice, encabezado in enumerate(next(lector, [])):
            ubicacion, _, metrica = encabezado.partition(" -_")
            if metrica in CSV_METRICAS:
                columnas.append((indice, ubicacion, metrica, nombre_columna(ubicacion, metrica)))
        for fila in lector:
            if fila[0] < limite:
                continue
            marca = int(datetime.strptime(fila[0], FORMATO_FECHA).timestamp())
            for indice, ubicacion, metrica, columna in columnas:
                if indice < len(fila) and fila[indice] != "":
                    filas.setdefault(marca, {})[columna] = calibrar(offsets, ubicacion, metrica, float(fila[indice]))
    return filas

def armar_csv():
    offsets = cargar_offsets()
    consulta = '{__name__=~"%s"}' % "|".join(CSV_METRICAS)
    fin = int(time.time()) // CSV_PASO * CSV_PASO
    inicio = fin - CSV_DIAS * 24 * 3600
    filas = {}

    for desde in range(inicio, fin, CSV_VENTANA):
        hasta = min(desde + CSV_VENTANA, fin)
        series = prom_get("query_range", timeout=20, query=consulta, start=desde, end=hasta, step=CSV_PASO)["result"]
        for s in series:
            metrica = s["metric"]["__name__"]
            ubicacion = s["metric"].get("location", "?")
            columna = nombre_columna(ubicacion, metrica)
            for t, v in s["values"]:
                filas.setdefault(int(t), {})[columna] = calibrar(offsets, ubicacion, metrica, float(v))


    
    for ts, valores in leer_recuperadas(inicio, offsets).items():
        destino = filas.setdefault(ts, {})
        for columna, valor in valores.items():
            destino.setdefault(columna, valor)

    if not filas:
        return None

    columnas = sorted({columna for valores in filas.values() for columna in valores})
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["Times"] + columnas, restval="")
    writer.writeheader()
    for ts in sorted(filas):
        writer.writerow({"Times": datetime.fromtimestamp(ts).strftime(FORMATO_FECHA), **filas[ts]})
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
