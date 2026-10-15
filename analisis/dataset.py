import csv
import fcntl
import os
import time
from contextlib import contextmanager
from datetime import datetime
import requests

PROMETHEUS_URL = "http://localhost:9090"
DIAS = 30
PASO = 15
VENTANA = PASO * 10_000
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"

METRICAS = (
    "bme280_temperatura_celsius",
    "bme280_humedad_porcentaje",
    "bme280_presion_hpa",

    "dht22_temperatura_celsius",
    "dht22_humedad_porcentaje"
)

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_DATOS = os.path.join(CARPETA_SCRIPT, "datos")
RUTA_SALIDA = os.path.join(CARPETA_DATOS, "dataset_sensores.csv")
CARPETA_HISTORICO = os.path.join(CARPETA_DATOS, "historico")
RUTA_CANDADO = os.path.join(CARPETA_DATOS, ".dataset.lock")

def preparar_carpeta():
    os.makedirs(CARPETA_HISTORICO, exist_ok=True)


@contextmanager
def dataset_bloqueado():
    # evita que dataset y recuperar_buffer modifiquen el CSV al mismo tiempo
    preparar_carpeta()
    with open(RUTA_CANDADO, "w") as candado:
        fcntl.flock(candado, fcntl.LOCK_EX)
        yield


def pedir_datos():
    consulta = '{__name__=~"%s"}' % "|".join(METRICAS)
    fin = int(time.time()) // PASO * PASO
    inicio = fin - (DIAS * 24 * 3600)

    filas = {}

    for desde in range(inicio, fin, VENTANA):
        hasta = min(desde + VENTANA, fin)
        respuesta = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={
                "query": consulta,
                "start": desde,
                "end": hasta,
                "step": PASO
            },
            timeout=60
        )

        respuesta.raise_for_status()
        series = respuesta.json()["data"]["result"]

        for serie in series:
            ubicacion = serie["metric"].get("location", "desconocida")
            nombre_metrica = serie["metric"]["__name__"]
            columna = f"{ubicacion} -_{nombre_metrica}"
            for marca_de_tiempo, valor in serie["values"]:
                filas.setdefault(int(marca_de_tiempo), {})[columna] = valor

    return filas


def leer_csv(ruta):
    if not os.path.exists(ruta):
        return {}

    filas = {}
    with open(ruta, newline="", encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            marca = int(datetime.strptime(fila["Times"], FORMATO_FECHA).timestamp())
            filas[marca] = {k: v for k, v in fila.items() if k != "Times" and v != ""}
    return filas


def cargar_existente():
    return leer_csv(RUTA_SALIDA)


def alinear(filas, paso=PASO):
    alineadas, sueltas = {}, {}
    for marca, valores in filas.items():
        base = marca - marca % paso
        if base == marca:
            alineadas.setdefault(base, {}).update(valores)
        else:
            destino = sueltas.setdefault(base, {})
            for columna, valor in valores.items():
                destino.setdefault(columna, []).append(valor)

    for base, columnas in sueltas.items():
        destino = alineadas.setdefault(base, {})
        for columna, lista in columnas.items():
            if columna not in destino:
                destino[columna] = lista[0] if len(lista) == 1 else str(round(sum(map(float, lista)) / len(lista), 2))
    return alineadas


def fusionar(filas_base, filas_nuevas):
    filas = {marca: dict(valores) for marca, valores in filas_base.items()}
    for marca, valores in filas_nuevas.items():
        filas.setdefault(marca, {}).update(valores)
    return alinear(filas)


def escribir_csv(ruta, filas):
    columnas = sorted({columna for valores in filas.values() for columna in valores})
    temporal = ruta + ".tmp"
    with open(temporal, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=["Times"] + columnas, restval="")
        escritor.writeheader()
        for marca in sorted(filas):
            fecha = datetime.fromtimestamp(marca).strftime(FORMATO_FECHA)
            escritor.writerow({"Times": fecha, **filas[marca]})
    os.replace(temporal, ruta)  


def archivar(filas):
    por_mes = {}
    for marca, valores in filas.items():
        mes = datetime.fromtimestamp(marca).strftime("%Y-%m")
        por_mes.setdefault(mes, {})[marca] = valores

    for mes, nuevas in sorted(por_mes.items()):
        ruta = os.path.join(CARPETA_HISTORICO, f"sensores_{mes}.csv")
        filas_mes = leer_csv(ruta)
        for marca, valores in nuevas.items():
            filas_mes.setdefault(marca, {}).update(valores)
        escribir_csv(ruta, filas_mes)
        print(f"Historico actualizado: {ruta} ({len(filas_mes)} filas)")


def guardar_csv(filas, dias=DIAS):
    if not filas:
        print("No se encontraron datos para las métricas especificadas.")
        return


    archivar(filas)

    limite = int(time.time()) - dias * 24 * 3600
    recientes = {marca: valores for marca, valores in filas.items() if marca >= limite}
    escribir_csv(RUTA_SALIDA, recientes)
    print(f"Datos guardados en {RUTA_SALIDA} ({len(recientes)} filas)")


if __name__ == "__main__":
    nuevas = pedir_datos()
    with dataset_bloqueado():
        guardar_csv(fusionar(cargar_existente(), nuevas))
