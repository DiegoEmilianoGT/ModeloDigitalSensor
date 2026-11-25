"""El gemelo en vivo: lo medido en las ultimas 24 h frente a lo que el modelo previo 2 h antes.

Lo usan la API (/api/gemelo) y el bot (/gemelo).
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from comun import prometheus
from comun.calibracion import cargar_offsets
from modelo import termico

# apagado por ahora: con True vuelve a funcionar en la API, el panel y el bot
ACTIVO = False
RUTA_PARAMETROS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parametros.json")
PUNTOS = 144  # se devuelven las ultimas 24 h


class SinModelo(Exception):
    """Todavia no se ha corrido modelo/entrenar.py (o parametros.json esta dañado)."""


def fecha(marca):
    return datetime.fromtimestamp(marca).astimezone().isoformat(timespec="seconds")


def temperaturas(sensores, marcas):
    """(nodo, sensor) -> {marca: °C calibrados}, en promedios de 10 min."""
    paso = termico.PASO
    # una sola consulta: avg_over_time quita el nombre de la metrica, asi que el sensor viaja en una etiqueta
    consulta = " or ".join(
        f'label_replace(avg_over_time({s}_temperatura_celsius[{paso}s]), "sensor", "{s}", "", "")' for s in sensores)
    offsets = cargar_offsets()
    medidas = {}
    # evaluado en t promedia (t - paso, t]: ese promedio pertenece al punto que empieza en t - paso
    for serie in prometheus.rango(consulta, marcas[0] + paso, marcas[-1] + paso, paso):
        nodo, sensor = serie["metric"].get("location"), serie["metric"]["sensor"]
        offset = offsets.get(nodo, {}).get(f"{sensor}_temperatura_celsius", 0.0)
        medidas.setdefault((nodo, sensor), {}).update(
            {int(float(t)) - paso: float(v) + offset for t, v in serie["values"]})
    return medidas


def calcular():
    """Estado de cada sensor con modelo. Lanza SinModelo, o los errores de comun.prometheus."""
    try:
        with open(RUTA_PARAMETROS, encoding="utf-8") as f:
            parametros = json.load(f)
    except (OSError, ValueError) as exc:
        raise SinModelo(str(exc)) from exc

    paso = termico.PASO
    # ademas de las 24 h que se devuelven hacen falta el horizonte y las 24 h que promedia el nivel
    cuantos = PUNTOS + termico.HORIZONTE + termico.VENTANA_NIVEL
    fin = int(time.time()) // paso * paso
    marcas = [fin - (cuantos - i) * paso for i in range(cuantos)]
    medidas = temperaturas(sorted({m["sensor"] for m in parametros["sensores"]}), marcas)

    series = []
    for modelo in parametros["sensores"]:
        de_la_zona = medidas.get((modelo["nodo"], modelo["sensor"]), {})
        valores = [de_la_zona.get(m) for m in marcas]
        puntos = termico.seguir(modelo, marcas, valores)
        nivel = termico.niveles(valores)[-1]

        historial = []
        for m, valor, (previsto, _, anomalo) in list(zip(marcas, valores, puntos))[-PUNTOS:]:
            historial.append([
                fecha(m),
                None if valor is None else round(valor, 2),
                None if previsto is None else round(previsto, 2),
                round(termico.tolerancia(modelo, m), 2),
                anomalo,
            ])
        pronostico = []
        if valores[-1] is not None and nivel is not None:
            previstos = termico.pronosticar(modelo, valores[-1], nivel, marcas[-1])
            pronostico = [[fecha(marcas[-1] + (j + 1) * paso), round(v, 2), round(2 * modelo["error_por_paso"][j], 2)]
                          for j, v in enumerate(previstos)]

        if valores[-1] is None and valores[-2] is None:
            estado = "sin_datos"
        elif all(p[2] for p in puntos[-termico.DURACION_MINIMA:]):
            estado = "anomalia"
        else:
            estado = "normal"
        series.append({
            "nodo": modelo["nodo"],
            "sensor": modelo["sensor"],
            "tau_horas": round(modelo["tau_horas"], 1),
            "tau_rango_horas": modelo.get("tau_rango_horas"),
            "estado": estado,
            "historial": historial,
            "pronostico": pronostico,
            "episodios": [
                {"inicio": fecha(a), "fin": fecha(b + paso), "desviacion": round(d, 2)}
                for a, b, d in termico.episodios(marcas[-PUNTOS:], puntos[-PUNTOS:])
            ],
        })
    return {
        "entrenado": parametros["entrenado"],
        "horizonte_min": termico.HORIZONTE * paso // 60,
        "paso_min": paso // 60,
        "series": series,
    }
