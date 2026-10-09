import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from estadisticas import cargar_datos, limpiar_datos, calibrar

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_RESULTADOS = os.path.join(CARPETA_SCRIPT, "resultados")


def graficar(df):
    por_hora = df.resample("h").mean()

    fig, (ax_temp, ax_hum) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    for columna in por_hora.columns:
        if "temperatura" in columna:
            ax_temp.plot(por_hora.index, por_hora[columna], label=columna, linewidth=1)
        elif "humedad" in columna:
            ax_hum.plot(por_hora.index, por_hora[columna], label=columna, linewidth=1)

    ax_temp.set_ylabel("Temperatura (°C)")
    ax_temp.legend(fontsize=7)
    ax_temp.grid(alpha=0.3)

    ax_hum.set_ylabel("Humedad (%)")
    ax_hum.set_xlabel("Fecha")
    ax_hum.legend(fontsize=7)
    ax_hum.grid(alpha=0.3)

    fig.tight_layout()
    return fig


if __name__ == "__main__":
    try:
        datos = calibrar(cargar_datos())
        datos = limpiar_datos(datos)
        figura = graficar(datos)

        os.makedirs(CARPETA_RESULTADOS, exist_ok=True)
        ruta = os.path.join(CARPETA_RESULTADOS, "grafica_30_dias.png")
        figura.savefig(ruta, dpi=120)
        print(f"Grafica guardada en {ruta}")
    except FileNotFoundError as e:
        print(e)
