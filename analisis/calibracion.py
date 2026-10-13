import os
import json

RUTA_OFFSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "calibracion.json")

def cargar_offsets():
    with open(RUTA_OFFSETS, encoding="utf-8") as f:
        return json.load(f)

def calibrar_sensor(df, offsets):
    df= df.copy()
    for columna in df.columns:
        _,_, metrica = columna.partition("-_")
        if metrica in offsets:
            df[columna] = (df[columna] + offsets[metrica]).round(2)
    return df


