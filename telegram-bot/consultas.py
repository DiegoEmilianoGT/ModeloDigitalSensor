from datetime import datetime

from config import ETIQUETAS, MEDIDAS, log
from comun import prometheus as prom
from comun.calibracion import calibrar, cargar_offsets
from comun.nombres import acortar, etiqueta, sensor_extra
from modelo import gemelo
from texto import bloque, esc


def leer(consulta):
    # lecturas (calibradas)
    lecturas, nodos_up = {}, {}
    offsets = cargar_offsets()
    try:
        for r in prom.instantanea(consulta):
            metrica = r["metric"]["__name__"]
            if metrica == "up":
                nodos_up[r["metric"].get("nodo") or r["metric"].get("instance", "?")] = float(r["value"][1])
            else:
                location = r["metric"].get("location", "desconocido")
                lecturas.setdefault(location, {})[metrica] = calibrar(offsets, location, metrica, float(r["value"][1]))
    except prom.ERRORES as exc:
        log.warning("No se pudieron consultar las metricas: %s", exc)
    return lecturas, nodos_up


def con_unidad(valor, unidad):
    decimales = 0 if unidad == "dBm" else 2 
    return f"{valor:.{decimales}f} {unidad}"


def formatear_estado():
    lecturas, nodos_up = leer('{__name__=~"up|%s"}' % "|".join(ETIQUETAS))
    if not lecturas and not nodos_up:
        return "No se pudo contactar a Prometheus."

    partes = []
    if nodos_up:
        partes.append(bloque("Conexion", [
            (acortar(nodo), "en linea" if valor == 1 else "SIN RESPUESTA")
            for nodo, valor in sorted(nodos_up.items())
        ]))

    for location in sorted(lecturas):
        filas = []
        for metrica, (nombre, unidad) in ETIQUETAS.items():
            if metrica not in lecturas[location]:
                continue
            valor = lecturas[location][metrica]
            if metrica.endswith("_up"):
                if valor == 1:
                    continue 
                texto = "SIN LECTURA"
            else:
                texto = con_unidad(valor, unidad)
            filas.append((nombre + sensor_extra(location, metrica), texto))
        partes.append(bloque(acortar(location), filas))
    return "\n".join(partes)


def formatear_metrica(clave):
    sufijo, nombre, unidad = MEDIDAS[clave]
    lecturas, _ = leer('{__name__=~"(bme280|dht22)_%s"}' % sufijo)
    filas = [
        (etiqueta(location, metrica), con_unidad(valor, unidad))
        for location, valores in sorted(lecturas.items())
        for metrica, valor in valores.items()
    ]
    if not filas:
        return f"Sin datos de {nombre.lower()} por ahora."
    return bloque(nombre, filas)


def formatear_gemelo():
    try:
        estado = gemelo.calcular()
    except gemelo.SinModelo:
        return "El modelo termico todavia no esta entrenado (modelo/entrenar.py)."
    except prom.ERRORES as exc:
        log.warning("No se pudo calcular el gemelo: %s", exc)
        return "No se pudo contactar a Prometheus."

    hora = lambda iso: datetime.fromisoformat(iso).strftime("%H:%M")
    filas, anomalias = [], []
    for s in estado["series"]:
        nombre = etiqueta(s["nodo"], s["sensor"])
        ultimo = next((p for p in reversed(s["historial"]) if p[1] is not None and p[2] is not None), None)
        if ultimo is None:
            filas.append((nombre, "sin datos"))
        else:
            _, medido, previsto, tolerancia, _ = ultimo
            aviso = "  ANOMALIA" if s["estado"] == "anomalia" else ""
            filas.append((nombre, f"{medido:.1f} °C (previsto {previsto:.1f}, tolerancia ±{tolerancia:.1f}){aviso}"))
        for e in s["episodios"]:
            anomalias.append(f"{nombre}: {hora(e['inicio'])}-{hora(e['fin'])} ({e['desviacion']:+.1f} °C)")
    texto = bloque(f"Medido frente a lo previsto {estado['horizonte_min'] // 60} h antes", filas)
    if anomalias:
        return texto + "\nAnomalias en 24 h:\n" + esc("\n".join(anomalias))
    return texto + "\nSin anomalias en las ultimas 24 h."
