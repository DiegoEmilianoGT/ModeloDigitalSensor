import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from comun.estilo import FONDO, TINTA, dar_estilo, leyenda_arriba, trazo
from comun.nombres import etiqueta
from estadisticas import cargar_datos, limpiar_datos, calibrar

CARPETA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
CARPETA_RESULTADOS = os.path.join(CARPETA_SCRIPT, "resultados")


def graficar(df):
    por_hora = df.resample("h").mean()
    nodos = sorted({columna.partition(" -_")[0] for columna in por_hora.columns})

    fig, (ax_temp, ax_hum) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, facecolor=FONDO)

    for columna in por_hora.columns:
        nodo, _, metrica = columna.partition(" -_")
        if "temperatura" in metrica:
            ax = ax_temp
        elif "humedad" in metrica:
            ax = ax_hum
        else:
            continue
        ax.plot(por_hora.index, por_hora[columna], label=etiqueta(nodo, metrica), linewidth=1.2,
                **trazo(nodos, nodo, metrica))

    # una sola leyenda arriba, fuera de las curvas, para las dos graficas
    series = {}
    for ax in (ax_temp, ax_hum):
        for linea, nombre in zip(*ax.get_legend_handles_labels()):
            series.setdefault(nombre, linea)
    if series:
        leyenda_arriba(ax_temp, list(series.values()), list(series.keys()), columnas=5)

    fig.suptitle("Promedio por hora de los últimos 30 días (valores calibrados)",
                 x=0.01, ha="left", fontsize=10, color=TINTA)
    dar_estilo(ax_temp, "Temperatura (°C)")
    dar_estilo(ax_hum, "Humedad (%)")
    localizador = mdates.AutoDateLocator()
    ax_hum.xaxis.set_major_locator(localizador)
    ax_hum.xaxis.set_major_formatter(mdates.ConciseDateFormatter(localizador))

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
