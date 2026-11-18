"""Aspecto de las graficas de matplotlib: mismos colores y ejes en el bot, analisis/ y modelo/."""

# un color por nodo, siempre en este orden; el DHT22 va punteado para distinguirlo
# cuando un mismo nodo trae los dos sensores
COLORES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
COLOR_EXTRA = "#898781"
ANOMALO = "#d03b3b"
FONDO, TINTA, TINTA_SUAVE, REJILLA, EJE = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"


def trazo(nodos, nodo, metrica):
    """color y linestyle de la serie de un nodo; nodos es la lista ordenada de todos los que se grafican."""
    indice = nodos.index(nodo)
    return {
        "color": COLORES[indice] if indice < len(COLORES) else COLOR_EXTRA,
        "linestyle": "--" if metrica.startswith("dht22") else "-",
    }


def dar_estilo(ax, titulo_eje):
    ax.set_facecolor(FONDO)
    ax.set_ylabel(titulo_eje, color=TINTA_SUAVE)
    ax.grid(color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=TINTA_SUAVE, labelsize=8)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(EJE)


def leyenda_arriba(ax, lineas=None, nombres=None, columnas=4):
    # fuera de las curvas, para que no las tape
    series = (lineas, nombres) if lineas is not None else ()
    ax.legend(*series, loc="lower left", bbox_to_anchor=(0, 1), ncol=columnas, fontsize=8, frameon=False,
              labelcolor=TINTA, borderaxespad=0.3)
