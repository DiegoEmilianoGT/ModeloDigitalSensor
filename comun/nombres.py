"""Nombres cortos de nodos y sensores para mensajes y graficas."""
import re

NOMBRE_RE = re.compile(r"\b([a-z0-9]+)_[a-z0-9]+_(\d+)\b")


def acortar(texto):
    # bme280_esp32c3_01 -> BME280 #1
    return NOMBRE_RE.sub(lambda m: f"{m.group(1).upper()} #{int(m.group(2))}", texto)


def sensor_extra(nodo, metrica):
    # dice de cual sensor es la lectura cuando el nombre del nodo no lo deja claro
    sensor = metrica.split("_")[0]
    return "" if nodo.startswith(sensor) else f" {sensor.upper()}"


def etiqueta(nodo, metrica):
    return acortar(nodo) + sensor_extra(nodo, metrica)
