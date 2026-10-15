import glob
import json
import os
import requests

from dataset import cargar_existente, dataset_bloqueado, fusionar, guardar_csv

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_TARGETS = os.path.join(CARPETA_SCRIPT, "..", "prometheus", "targets")

BME280 = ("bme280_temperatura_celsius", "bme280_humedad_porcentaje", "bme280_presion_hpa")
DHT22 = ("dht22_temperatura_celsius", "dht22_humedad_porcentaje")

# valores de cada linea del buffer despues del timestamp
METRICAS_POR_PREFIJO = {
    "bme280": BME280,
    "dht22": DHT22,
    "supermini": BME280 + DHT22,
}


def nodos_conocidos():
    nodos = []
    for ruta in glob.glob(os.path.join(CARPETA_TARGETS, "*.json")):
        try:
            with open(ruta, encoding="utf-8") as f:
                entradas = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"No se pudo leer {ruta}: {exc}")
            continue
        for entrada in entradas:
            host = entrada["targets"][0]
            nodo = entrada["labels"]["nodo"]
            nodos.append((nodo, host))
    return nodos


def prefijo_de(nodo):
    for prefijo in METRICAS_POR_PREFIJO:
        if nodo.startswith(prefijo):
            return prefijo
    return None


def parsear_buffer(nodo, texto, metricas):
    filas = {}
    for linea in texto.strip().splitlines():
        partes = linea.split(",")
        if len(partes) != len(metricas) + 1:
            print(f"{nodo}: linea con forma rara, se ignora: {linea!r}")
            continue
        try:
            marca = int(partes[0])
        except ValueError:
            print(f"{nodo}: timestamp invalido, se ignora: {linea!r}")
            continue
        valores = {
            f"{nodo} -_{metrica}": valor
            for metrica, valor in zip(metricas, partes[1:])
            if valor != ""
        }
        if valores:
            filas[marca] = valores
    return filas


def recuperar_de(nodo, host):
    prefijo = prefijo_de(nodo)
    if prefijo is None:
        print(f"{nodo}: no se reconoce el tipo de sensor por el nombre, se omite")
        return {}

    try:
        resp = requests.get(f"http://{host}/buffer", timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"{nodo} ({host}): no se pudo contactar - {exc}")
        return {}

    if not resp.text.strip():
        return {}

    filas = parsear_buffer(nodo, resp.text, METRICAS_POR_PREFIJO[prefijo])
    if filas:
        print(f"{nodo} ({host}): {len(filas)} lecturas recuperadas del buffer")
    return filas


def confirmar(nodo, host):
    try:
        requests.get(f"http://{host}/buffer/confirmar", timeout=10).raise_for_status()
        print(f"{nodo} ({host}): buffer confirmado y vaciado")
    except requests.RequestException as exc:
        print(f"{nodo} ({host}): no se pudo confirmar, se reintentara mas tarde - {exc} ")


if __name__ == "__main__":
    recuperadas = {}
    pendientes_de_confirmar = []
    for nodo, host in nodos_conocidos():
        filas = recuperar_de(nodo, host)
        if filas:
            for marca, valores in filas.items():
                recuperadas.setdefault(marca, {}).update(valores)
            pendientes_de_confirmar.append((nodo, host))

    if not pendientes_de_confirmar:
        print("Ningun nodo tenia datos pendientes en buffer.")
    else:
        with dataset_bloqueado():
            guardar_csv(fusionar(cargar_existente(), recuperadas))
        for nodo, host in pendientes_de_confirmar:
            confirmar(nodo, host)
