import csv
import os
import time
from datetime import datetime
import requests

PROMETHEUS_URL = "http://localhost:9090"
DIAS = 30
PASO = 15
VENTANA = PASO * 10_000

METRICAS = (
    "bme280_temperatura_celsius",
    "bme280_humedad_porcentaje",
    "bme280_presion_hpa",

    "dht22_temperatura_celsius",
    "dht22_humedad_porcentaje"
)

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
RUTA_SALIDA = os.path.join(CARPETA_SCRIPT, "datos", "dataset_sensores.csv")

def preparar_carpeta():
    carpeta_datos = os.path.dirname(RUTA_SALIDA)
    os.makedirs(carpeta_datos, exist_ok=True)

def pedir_datos():
    consulta = '{__name__=~"%s"}' % "|".join(METRICAS)
    fin = int(time.time())
    inicio = fin - (DIAS * 24 * 3600)

    filas = {}
    columnas = set()

    for desde in range(inicio, fin, VENTANA):
        hasta = min(desde + VENTANA, fin)
        respuesta = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={
                "query": consulta,
                "start": desde,
                "end": hasta,
                "step": PASO
            }
        )

        respuesta.raise_for_status()
        series = respuesta.json()["data"]["result"]

        for serie in series:
            ubicacion = serie["metric"].get("location", "desconocida")
            nombre_metrica = serie["metric"]["__name__"]
            columna = f"{ubicacion} -_{nombre_metrica}"
            columnas.add(columna)
            for marca_de_tiempo, valor in serie["values"]:
                filas.setdefault(int(marca_de_tiempo), {})[columna] = valor

    return filas, columnas


def cargar_existente():
    if not os.path.exists(RUTA_SALIDA):
        return {}, set()

    filas, columnas = {}, set()
    with open(RUTA_SALIDA, newline="", encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            marca = int(datetime.strptime(fila["Times"], "%Y-%m-%d %H:%M:%S").timestamp())
            valores = {k: v for k, v in fila.items() if k != "Times" and v != ""}
            filas[marca] = valores
            columnas.update(valores)
    return filas, columnas


def fusionar(filas_base, columnas_base, filas_nuevas, columnas_nuevas, dias=DIAS):
    filas = {marca: dict(valores) for marca, valores in filas_base.items()}
    for marca, valores in filas_nuevas.items():
        filas.setdefault(marca, {}).update(valores)

    limite = int(time.time()) - dias * 24 * 3600
    filas = {marca: valores for marca, valores in filas.items() if marca >= limite}
    columnas = {c for c in (columnas_base | columnas_nuevas)}
    return filas, columnas


def guardar_csv(filas, columnas):
    if not filas:
        print("No se encontraron datos para las métricas especificadas.")
        return

    with open(RUTA_SALIDA, "w", newline="", encoding="utf-8") as archivo:
        columnas_ordenadas = ["Times"] + sorted(columnas)
        escritor = csv.DictWriter(archivo, fieldnames=columnas_ordenadas, restval="")
        escritor.writeheader()
        for marca in sorted(filas):
            fecha = datetime.fromtimestamp(marca).strftime("%Y-%m-%d %H:%M:%S")
            escritor.writerow({"Times": fecha, **filas[marca]})

    print(f"Datos guardados en {RUTA_SALIDA} ({len(filas)} filas)")


if __name__ == "__main__":
    preparar_carpeta()
    existentes, columnas_existentes = cargar_existente()
    nuevas, columnas_nuevas = pedir_datos()
    filas, columnas = fusionar(existentes, columnas_existentes, nuevas, columnas_nuevas)
    guardar_csv(filas, columnas)