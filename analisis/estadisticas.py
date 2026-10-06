import os
import pandas as pd

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
RUTA_DATASET = os.path.join(CARPETA_SCRIPT, "datos", "dataset_sensores.csv")
UMBRALES = {"humedad": 5, "temperatura": 2, "presion": 10}

def cargar_datos():
    if not os.path.exists(RUTA_DATASET):
        raise FileNotFoundError(f"No se encontró el archivo de datos: {RUTA_DATASET}")

    df = pd.read_csv(RUTA_DATASET, parse_dates=["Times"])
    df = df.set_index("Times")
    return df

def resumen_estadistico(df):
    return df.describe()

def promedio_diario(df):
    return df.resample('D').mean()


def limpiar_picos(serie, ventana=5, umbral=5.0):

    # Elimina picos de datos basura
    
    mediana_movil = serie.rolling(ventana, center=True, min_periods=1).median()
    es_pico = (serie - mediana_movil).abs() > umbral
    return serie.mask(es_pico)

def limpiar_datos(df):
    df = df.copy()
    for columna in df.columns:
        for palabra, umbral in UMBRALES.items():
            if palabra in columna:
                df[columna] = limpiar_picos(df[columna], umbral=umbral)
    return df


def resumen_limpieza(original, limpio):
    filas = []
    for columna in original.columns:
        descartados = int(limpio[columna].isna().sum() - original[columna].isna().sum())
        filas.append({
            "columna": columna,
            "minimo": limpio[columna].min(),
            "maximo": limpio[columna].max(),
            "normales": int(limpio[columna].notna().sum()),
            "picos_descartados": descartados,
        })
    return pd.DataFrame(filas).set_index("columna")


if __name__ == "__main__":
    try:
        crudos = cargar_datos()
        datos = limpiar_datos(crudos)

        print("Resumen de limpieza (minimo, maximo, normales, picos descartados):")
        print(resumen_limpieza(crudos, datos))

        print("\nResumen estadístico:")
        print(resumen_estadistico(datos))

        print("\nPromedio diario:")
        print(promedio_diario(datos))
    except FileNotFoundError as e:
        print(e)

