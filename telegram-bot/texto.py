import html
import re

from config import BOT_TOKEN

esc = html.escape

NOMBRE_RE = re.compile(r"\b([a-z0-9]+)_[a-z0-9]+_(\d+)\b")
SANGRIA = " " * 4


def acortar(texto):
    #bme280_esp32c3_01 -> BME280 #1
    return NOMBRE_RE.sub(lambda m: f"{m.group(1).upper()} #{int(m.group(2))}", texto)


def bloque(titulo, filas):
    ancho = max((len(k) for k, _ in filas), default=0)
    lineas = [titulo] + [f"  {k.ljust(ancho)}  {v}" for k, v in filas]
    return "<pre>" + esc("\n".join(lineas)) + "</pre>"


def sin_token(exc):
    return str(exc).replace(BOT_TOKEN, "<token>")
