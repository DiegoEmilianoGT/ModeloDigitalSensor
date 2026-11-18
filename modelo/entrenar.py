"""Ajusta el modelo termico con el historico de analisis/ y lo deja listo para la API.

Uso: /usr/bin/python3 modelo/entrenar.py

Escribe modelo/parametros.json (lo lee la API en /api/gemelo) y, en modelo/resultados/,
la evaluacion, los episodios anomalos del historial y una grafica por sensor.
"""
import glob
import json
import os
import random
import sys
import time
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CARPETA, "..", "analisis"))
sys.path.append(os.path.join(CARPETA, ".."))

from calibracion import calibrar
from dataset import CARPETA_HISTORICO
from estadisticas import limpiar_datos
from comun.estilo import ANOMALO, COLOR_EXTRA, COLORES, FONDO, TINTA, TINTA_SUAVE, dar_estilo, leyenda_arriba

import termico

RUTA_PARAMETROS = os.path.join(CARPETA, "parametros.json")
CARPETA_RESULTADOS = os.path.join(CARPETA, "resultados")
DIAS_MINIMOS = 14       # con menos historia el perfil diario no es fiable
DIAS_DE_PRUEBA = 10     # lo ultimo se aparta para medir el error con datos que el ajuste no vio
PASOS_EVALUADOS = {"10 min": 1, "1 h": 6, "2 h": 12}
PUNTOS_POR_DIA = 86400 // termico.PASO

MEDIDO, PREVISTO = COLORES[0], COLOR_EXTRA
LABORAL, FIN_DE_SEMANA = COLORES[0], COLORES[1]


def cargar_temperaturas():
    """Temperaturas calibradas y sin picos de todo el historico, en promedios de 10 min."""
    archivos = sorted(glob.glob(os.path.join(CARPETA_HISTORICO, "*.csv")))
    if not archivos:
        raise FileNotFoundError(f"No hay historico en {CARPETA_HISTORICO}")
    crudo = pd.concat(pd.read_csv(a, parse_dates=["Times"], index_col="Times") for a in archivos).sort_index()
    crudo = crudo[~crudo.index.duplicated(keep="last")]
    datos = limpiar_datos(calibrar(crudo))
    return datos[[c for c in datos.columns if "temperatura" in c]].resample(f"{termico.PASO}s").mean()


def a_listas(serie):
    marcas = [int(time.mktime(t.timetuple())) for t in serie.index]
    return marcas, [None if pd.isna(v) else float(v) for v in serie]


def raiz_media(errores):
    return (sum(e * e for e in errores) / len(errores)) ** 0.5


def evaluar(marcas, valores):
    """Ajusta sin los ultimos dias y mide en ellos el error del modelo y el de suponer que nada cambia."""
    corte = len(valores) - DIAS_DE_PRUEBA * PUNTOS_POR_DIA
    modelo = termico.ajustar(marcas[:corte], valores[:corte])
    nivel = termico.niveles(valores)
    del_modelo = {nombre: [] for nombre in PASOS_EVALUADOS}
    de_persistir = {nombre: [] for nombre in PASOS_EVALUADOS}
    for k in range(corte, len(valores)):
        if valores[k] is None or nivel[k] is None:
            continue
        previstos = termico.pronosticar(modelo, valores[k], nivel[k], marcas[k])
        for nombre, pasos in PASOS_EVALUADOS.items():
            if k + pasos < len(valores) and valores[k + pasos] is not None:
                del_modelo[nombre].append(valores[k + pasos] - previstos[pasos - 1])
                de_persistir[nombre].append(valores[k + pasos] - valores[k])
    filas = []
    for nombre in PASOS_EVALUADOS:
        error, referencia = raiz_media(del_modelo[nombre]), raiz_media(de_persistir[nombre])
        filas.append({"plazo": nombre, "error_modelo": round(error, 3), "error_sin_modelo": round(referencia, 3),
                      "mejora_pct": round(100 * (1 - error / referencia), 1)})
    return filas


def rango_de_tau(marcas, valores, repeticiones=30):
    """Entre que valores cae la constante de tiempo al repetir el ajuste sin el 20 % de los dias, elegidos
    al azar. Con pocas semanas de datos unos cuantos dias raros la mueven bastante: conviene saberlo."""
    azar = random.Random(0)
    dias = len(valores) // PUNTOS_POR_DIA
    taus = []
    for _ in range(repeticiones):
        recortado = list(valores)
        for dia in azar.sample(range(dias), dias // 5):
            recortado[dia * PUNTOS_POR_DIA:(dia + 1) * PUNTOS_POR_DIA] = [None] * PUNTOS_POR_DIA
        try:
            taus.append(termico.ajustar(marcas, recortado)["tau_horas"])
        except ValueError:
            continue
    taus.sort()
    return [round(taus[len(taus) // 10], 1), round(taus[-1 - len(taus) // 10], 1)]


def graficar(nombre, modelo, marcas, valores, puntos):
    """Ultima semana (medido contra previsto) y el perfil diario de equilibrio que aprendio el modelo."""
    desde = max(len(valores) - 7 * PUNTOS_POR_DIA, 0)
    horas = [datetime.fromtimestamp(m) for m in marcas[desde:]]
    medido = [float("nan") if v is None else v for v in valores[desde:]]
    previsto = [float("nan") if p[0] is None else p[0] for p in puntos[desde:]]
    margen = [termico.tolerancia(modelo, m) for m in marcas[desde:]]
    raros = [(h, v) for h, v, p in zip(horas, medido, puntos[desde:]) if p[2]]

    fig, (ax_semana, ax_perfil) = plt.subplots(
        2, 1, figsize=(10, 7), facecolor=FONDO, gridspec_kw={"height_ratios": [3, 2]})
    ax_semana.fill_between(horas, [p - m for p, m in zip(previsto, margen)], [p + m for p, m in zip(previsto, margen)],
                           color=PREVISTO, alpha=0.18, linewidth=0, label="Tolerancia")
    ax_semana.plot(horas, previsto, color=PREVISTO, linewidth=1.2, label="Previsto 2 h antes")
    ax_semana.plot(horas, medido, color=MEDIDO, linewidth=1.4, label="Medido")
    if raros:
        ax_semana.plot(*zip(*raros), linestyle="none", marker="o", markersize=4, color=ANOMALO, label="Anómalo")
    dar_estilo(ax_semana, "Temperatura (°C)")
    leyenda_arriba(ax_semana)
    localizador = mdates.AutoDateLocator()
    ax_semana.xaxis.set_major_locator(localizador)
    ax_semana.xaxis.set_major_formatter(mdates.ConciseDateFormatter(localizador))

    # un lunes y un sabado cualesquiera: el perfil solo depende de la hora y del tipo de dia
    lunes = time.mktime((2026, 1, 5, 0, 0, 0, 0, 0, -1))
    reloj = [m / 6 for m in range(24 * 6 + 1)]
    for tipo, dia, color, raya in (("Día laboral", lunes, LABORAL, "-"), ("Fin de semana", lunes + 5 * 86400, FIN_DE_SEMANA, "--")):
        ax_perfil.plot(reloj, [termico.equilibrio(modelo, dia + h * 3600) for h in reloj],
                       color=color, linestyle=raya, linewidth=1.6, label=tipo)
    ax_perfil.set_xlim(0, 24)
    ax_perfil.set_xticks(range(0, 25, 3))
    ax_perfil.set_xlabel("Hora del día", color=TINTA_SUAVE)
    dar_estilo(ax_perfil, "Equilibrio − nivel (°C)")
    leyenda_arriba(ax_perfil)

    fig.suptitle(f"{nombre}: modelo térmico (constante de tiempo {modelo['tau_horas']:.1f} h), última semana",
                 x=0.01, ha="left", fontsize=10, color=TINTA)
    fig.tight_layout()
    return fig


def guardar(ruta, texto):
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        f.write(texto)
    os.replace(temporal, ruta)


if __name__ == "__main__":
    try:
        temperaturas = cargar_temperaturas()
    except FileNotFoundError as e:
        sys.exit(str(e))
    os.makedirs(CARPETA_RESULTADOS, exist_ok=True)

    sensores, evaluaciones, anomalias = [], [], []
    for columna in temperaturas.columns:
        nodo, _, metrica = columna.partition(" -_")
        sensor = metrica.split("_")[0]
        nombre = f"{nodo} ({sensor})"
        marcas, valores = a_listas(temperaturas[columna])
        dias = sum(v is not None for v in valores) / PUNTOS_POR_DIA
        if dias < DIAS_MINIMOS:
            print(f"{nombre}: solo {dias:.0f} dias de datos, se necesitan {DIAS_MINIMOS}; se omite")
            continue

        prueba = evaluar(marcas, valores)
        modelo = termico.ajustar(marcas, valores)
        modelo["tau_rango_horas"] = rango_de_tau(marcas, valores)
        modelo.update(termico.calibrar(modelo, marcas, valores))
        puntos = termico.seguir(modelo, marcas, valores)
        encontrados = termico.episodios(marcas, puntos)

        sensores.append({"nodo": nodo, "sensor": sensor, "dias": round(dias, 1), **modelo, "evaluacion": prueba})
        evaluaciones += [{"nodo": nodo, "sensor": sensor, **fila} for fila in prueba]
        for inicio, fin, desviacion in encontrados:
            anomalias.append({
                "nodo": nodo, "sensor": sensor,
                "inicio": datetime.fromtimestamp(inicio).strftime("%Y-%m-%d %H:%M"),
                "fin": datetime.fromtimestamp(fin + termico.PASO).strftime("%Y-%m-%d %H:%M"),
                "minutos": (fin - inicio + termico.PASO) // 60,
                "desviacion_max": round(desviacion, 2),
                "tolerancia": round(termico.tolerancia(modelo, inicio), 2),
            })

        figura = graficar(nombre, modelo, marcas, valores, puntos)
        figura.savefig(os.path.join(CARPETA_RESULTADOS, f"modelo_{nodo}_{sensor}.png"), dpi=120)
        plt.close(figura)

        print(f"{nombre}: {dias:.0f} dias, constante de tiempo {modelo['tau_horas']:.1f} h "
              f"(entre {modelo['tau_rango_horas'][0]} y {modelo['tau_rango_horas'][1]}), "
              f"umbral {modelo['umbral']:.1f} desviaciones, {len(encontrados)} episodios anomalos")
        for fila in prueba:
            print(f"    a {fila['plazo']:>6}: error {fila['error_modelo']:.2f} °C "
                  f"(sin modelo {fila['error_sin_modelo']:.2f} °C, mejora {fila['mejora_pct']:+.0f} %)")

    if not sensores:
        sys.exit("Ningun sensor tiene datos suficientes para ajustar el modelo.")

    guardar(RUTA_PARAMETROS, json.dumps({
        "entrenado": datetime.now().astimezone().isoformat(timespec="seconds"),
        "datos_desde": temperaturas.index[0].strftime("%Y-%m-%d"),
        "datos_hasta": temperaturas.index[-1].strftime("%Y-%m-%d"),
        "sensores": sensores,
    }, ensure_ascii=False, indent=1) + "\n")
    pd.DataFrame(evaluaciones).to_csv(os.path.join(CARPETA_RESULTADOS, "evaluacion.csv"), index=False)
    pd.DataFrame(anomalias, columns=["nodo", "sensor", "inicio", "fin", "minutos", "desviacion_max", "tolerancia"]).to_csv(
        os.path.join(CARPETA_RESULTADOS, "anomalias.csv"), index=False)
    print(f"Parametros guardados en {RUTA_PARAMETROS}; resultados en {CARPETA_RESULTADOS}")
