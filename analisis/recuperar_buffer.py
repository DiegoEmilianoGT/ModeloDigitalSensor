import json
import os
import time
import requests

from dataset import CARPETA_BUFFER, dataset_bloqueado
from comun.nodos import nodos_conocidos

RUTA_ESTADO = os.path.join(CARPETA_BUFFER, "estado.json")
ADELANTO_MAXIMO = 24 * 3600  # una marca mas adelantada que esto es basura, no una lectura


def cargar_estado():
    try:
        with open(RUTA_ESTADO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar_estado(estado):
    temporal = RUTA_ESTADO + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=4)
    os.replace(temporal, RUTA_ESTADO)


def marca_de(linea):
    inicio = linea.split(",", 1)[0]
    return int(inicio) if inicio.isdigit() else None


def recuperar_de(nodo, host, desde):
    try:
        resp = requests.get(f"http://{host}/buffer", params={"desde": desde}, timeout=(5, 60))
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"{nodo} ({host}): no se pudo contactar - {exc}")
        return []
    # sin el tope, una sola marca corrupta en el futuro dejaria al nodo sin recuperar nada mas
    tope = time.time() + ADELANTO_MAXIMO
    return [
        linea.strip() for linea in resp.text.splitlines()
        if desde < (marca_de(linea) or 0) <= tope
    ]


if __name__ == "__main__":
    with dataset_bloqueado():
        estado = cargar_estado()

    nuevas_en_total = 0
    for nodo, host in sorted(nodos_conocidos().items()):
        lineas = recuperar_de(nodo, host, estado.get(nodo, 0))
        if not lineas:
            continue
        with dataset_bloqueado():
            with open(os.path.join(CARPETA_BUFFER, f"{nodo}.csv"), "a", encoding="utf-8") as f:
                f.write("\n".join(lineas) + "\n")
        estado[nodo] = max(marca_de(linea) for linea in lineas)
        guardar_estado(estado)
        nuevas_en_total += len(lineas)
        print(f"{nodo} ({host}): {len(lineas)} lecturas nuevas del buffer")

    if nuevas_en_total == 0:
        print("No habia lecturas nuevas en el buffer")
