import os
import pandas as pd

from estadisticas import cargar_datos, limpiar_datos, resumen_estadistico, promedio_diario, resumen_limpieza, promedio_30_dias, calibrar

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_RESULTADOS = os.path.join(CARPETA_SCRIPT, "resultados")

def comparar_sensores(df, metrica):
    columnas = [c for c in df.columns if metrica in c]
    if len(columnas) < 2:
        raise ValueError(f"No hay suficientes sensores para comparar la métrica '{metrica}'.")

    comunes = df[columnas].dropna()
    resultado = {}
    for columna in columnas:
        otros = [c for c in columnas if c != columna]
        diferencias = comunes[otros].mean(axis=1)
        resultado[columna] = {
            "correlacion": comunes[columna].corr(diferencias),
            "diferencia_promedio": (comunes[columna] - diferencias).mean(),
            "puntos_comunes": len(comunes)
        }
    return pd.DataFrame(resultado).T


def guardar_resultados(limpieza, resumen, promedios, comparaciones, promedio_30d):
    os.makedirs(CARPETA_RESULTADOS, exist_ok=True)
    limpieza.to_csv(os.path.join(CARPETA_RESULTADOS, "resumen_limpieza.csv"))
    resumen.to_csv(os.path.join(CARPETA_RESULTADOS, "resumen_estadistico.csv"))
    promedios.to_csv(os.path.join(CARPETA_RESULTADOS, "promedio_diario.csv"))
    comparaciones.to_csv(os.path.join(CARPETA_RESULTADOS, "comparacion_sensores.csv"))
    promedio_30d.to_csv(os.path.join(CARPETA_RESULTADOS, "promedio_30_dias.csv"))
    print(f"Resultados guardados en la carpeta: {CARPETA_RESULTADOS}")


if __name__ == "__main__":
    try:
        crudos = cargar_datos()
        calibrados = calibrar(crudos)
        datos = limpiar_datos(calibrados)

        limpieza = resumen_limpieza(crudos, datos)
        resumen = resumen_estadistico(datos)
        promedios = promedio_diario(datos)
        promedio_30d = promedio_30_dias(datos)

        comparaciones = pd.concat({
            "humedad": comparar_sensores(datos, "humedad"),
            "temperatura": comparar_sensores(datos, "temperatura")
        })

        print("Resumen de limpieza:")
        print(limpieza)
        print("\nResumen estadístico:")
        print(resumen)
        print("\nPromedio diario:")
        print(promedios)
        print("\nPromedio de 30 días:")
        print(promedio_30d)
        print("\nComparación de sensores:")
        print(comparaciones)
        
        guardar_resultados(limpieza, resumen, promedios, comparaciones, promedio_30d)

    except FileNotFoundError as e:
        print(e)

