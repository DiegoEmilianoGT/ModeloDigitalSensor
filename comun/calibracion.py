"""Offsets de calibracion. Los datos se guardan crudos y el offset actual se suma al leer."""
import json
import logging
import os

RUTA_OFFSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "calibracion.json")


def leer_offsets():
    # nodo -> {metrica: offset}; sin archivo no hay offsets, y si esta dañado lanza ValueError
    try:
        with open(RUTA_OFFSETS, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def cargar_offsets():
    # para lo que solo muestra datos: un archivo dañado no debe tumbar la consulta
    try:
        return leer_offsets()
    except (OSError, ValueError) as exc:
        logging.getLogger("comun").warning("No se pudo cargar %s: %s", RUTA_OFFSETS, exc)
        return {}


def calibrar(offsets, nodo, metrica, valor):
    return round(valor + offsets.get(nodo, {}).get(metrica, 0.0), 2)
