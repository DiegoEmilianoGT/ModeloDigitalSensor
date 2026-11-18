import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from comun.calibracion import leer_offsets


def calibrar(df):
    offsets = leer_offsets()
    df = df.copy()
    for columna in df.columns:
        nodo, _, metrica = columna.partition(" -_")
        offset = offsets.get(nodo, {}).get(metrica, 0.0)
        if offset:
            df[columna] = (df[columna] + offset).round(2)
    return df
