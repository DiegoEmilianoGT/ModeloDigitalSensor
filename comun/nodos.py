"""Nodos que descubrir_nodos.sh tiene registrados en prometheus/targets."""
import glob
import json
import os

CARPETA_TARGETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prometheus", "targets")


def nodos_conocidos():
    # nodo -> "ip:puerto"
    nodos = {}
    for ruta in glob.glob(os.path.join(CARPETA_TARGETS, "*.json")):
        try:
            with open(ruta, encoding="utf-8") as f:
                for entrada in json.load(f):
                    nodos[entrada["labels"]["nodo"]] = entrada["targets"][0]
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            print(f"No se pudo leer {ruta}: {exc}")
    return nodos
