import html

from config import BOT_TOKEN

esc = html.escape

SANGRIA = " " * 4


def bloque(titulo, filas):
    ancho = max((len(k) for k, _ in filas), default=0)
    lineas = [titulo] + [f"  {k.ljust(ancho)}  {v}" for k, v in filas]
    return "<pre>" + esc("\n".join(lineas)) + "</pre>"


def sin_token(exc):
    return str(exc).replace(BOT_TOKEN, "<token>")
