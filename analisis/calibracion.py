import os
import json

RUTA_OFFSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "calibracion.json")

def cargar_offsets():
    with open(RUTA_OFFSETS, encoding="utf-8") as f:
        return json.load(f)

def calibrar(df):
    offsets = cargar_offsets()
    df = df.copy()
    for columna in df.columns:
        nodo, _, metrica = columna.partition(" -_")
        offset = offsets.get(nodo, {}).get(metrica, 0.0)
        if offset:
            df[columna] = (df[columna] + offset).round(2)
    return df
