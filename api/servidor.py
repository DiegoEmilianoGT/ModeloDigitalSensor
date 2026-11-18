import json
import os
import re
import sys
import time
from typing import Annotated, Optional, Literal
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

CARPETA_PROYECTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.append(CARPETA_PROYECTO)

from comun import prometheus as prom
from comun.calibracion import calibrar, cargar_offsets
from modelo import gemelo as modelo_gemelo

RUTA_PANEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel.html")
RUTA_SALA = os.path.join(CARPETA_PROYECTO, "modelo", "sala.json")
NODO_RE = re.compile(r"^[a-z0-9_]+$")
# Se leen las metricas crudas y la calibracion se aplica aqui con el offset actual, igual que el bot
# y analisis/. Las series *_calibrada de Prometheus conservan el offset que habia en cada momento
# (incluidos los de prueba), asi que su historial no sirve.
MEDIDAS ={
    "temperatura": ("temperatura_celsius", "°C"),
    "humedad": ("humedad_porcentaje", "%"),
    "presion": ("presion_hpa", "hPa"),
}
MEDIDA_DE_SUFIJO = {sufijo: medida for medida, (sufijo, _) in MEDIDAS.items()}
PASO_MINIMO = 15
PUNTOS_POR_DEFECTO = 1000
PUNTOS_MAXIMOS = 11000
DIAS_MAXIMOS = 366


app = FastAPI(
    title = "API Red-Sensores",
    description = "Consulta de estado, historial y alertas de los nodos",
    version = "1.0.0",
    )
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])
app.add_middleware(GZipMiddleware, minimum_size=2000)  # el historial son cientos de KB

def prometheus(ruta, **params):
    try:
        return prom.consultar(ruta, timeout=20, **params)
    except ValueError as exc:
        raise HTTPException(502, f"Prometheus error: {exc}") from exc
    except prom.ERRORES as exc:
        raise HTTPException(503, f"Prometheus no respondio: {exc}") from exc

guardado = {}

def con_cache(clave, segundos, calcular):
    # varios paneles abiertos piden lo mismo cada pocos segundos: Prometheus se consulta una sola vez
    ahora = time.monotonic()
    if clave in guardado and ahora - guardado[clave][0] < segundos:
        return guardado[clave][1]
    for vieja in [c for c, (momento, _) in guardado.items() if ahora - momento > 120]:
        guardado.pop(vieja, None)
    valor = calcular()
    guardado[clave] = (ahora, valor)
    return valor

def fecha(marca):
    return datetime.fromtimestamp(float(marca)).astimezone().isoformat(timespec="seconds")

def validar_nodo(nodo):
    if not NODO_RE.match(nodo):
        raise HTTPException(400, "Nombre de nodo invalido")

def selector(sufijos,nodo=None):
    filtro = f', location="{nodo}"' if nodo else ""
    return '{__name__=~"(bme280|dht22)_(%s)"%s}' % ("|".join(sufijos), filtro)


def estado_de_nodos(nodo=None):
    # nodo -> conexion, sensores, senal y lecturas calibradas, todo con una sola consulta
    sufijos = "|".join(sufijo for sufijo, _ in MEDIDAS.values())
    filtro = f', nodo="{nodo}"' if nodo else ""
    resultado = prometheus(
        "query", query='{__name__=~"up|(bme280|dht22)_(sensor_up|wifi_rssi_dbm|%s)"%s}' % (sufijos, filtro))["result"]
    nodos = {}
    for r in resultado:
        if r["metric"]["__name__"] == "up":
            nombre = r["metric"].get("nodo", "?")
            nodos[nombre] = {
                "nodo": nombre,
                "en_linea": r["value"][1] == "1",
                "direccion": r["metric"].get("instance"),
                "momento": fecha(r["value"][0]),
                "sensores": [],
                "rssi": None,
                "lecturas": {},
            }
    offsets = cargar_offsets()
    for r in resultado:
        metrica, ubicacion = r["metric"]["__name__"], r["metric"].get("location")
        if metrica == "up" or ubicacion not in nodos:
            continue
        sensor, _, sufijo = metrica.partition("_")
        valor = float(r["value"][1])
        if sufijo == "sensor_up":
            nodos[ubicacion]["sensores"].append(sensor)
        elif sufijo == "wifi_rssi_dbm":
            nodos[ubicacion]["rssi"] = round(valor)
        else:
            lecturas = nodos[ubicacion]["lecturas"].setdefault(sensor, {})
            lecturas[MEDIDA_DE_SUFIJO[sufijo]] = calibrar(offsets, ubicacion, metrica, valor)
    for estado in nodos.values():
        estado["sensores"].sort()
    return nodos


@app.get("/api/salud")
def salud():
    prometheus("query", query="vector(1)")
    return {"api": "ok","prometheus": "ok"}

@app.get("/api/nodos")
def nodos():
    def listar():
        campos = ("nodo", "en_linea", "direccion", "sensores", "rssi", "lecturas")
        return [{c: n[c] for c in campos} for _, n in sorted(estado_de_nodos().items())]
    return con_cache("nodos", 4, listar)

@app.get("/api/nodos/{nodo}")
def lectura_actual(nodo: str):
    validar_nodo(nodo)
    estado = estado_de_nodos(nodo).get(nodo)
    if estado is None:
        raise HTTPException(404, f"Nodo {nodo} no encontrado")
    # un nodo conocido pero caido responde con en_linea false y sin lecturas, no con 404
    return {c: estado[c] for c in ("nodo", "en_linea", "momento", "lecturas")}

@app.get("/api/lecturas")
def historial(
    medida: Literal["temperatura", "humedad", "presion"],
    desde: Annotated[Optional[datetime], Query(description="Inicio")] = None,
    hasta: Annotated[Optional[datetime], Query(description="Fin")] = None,
    nodo: Annotated[Optional[str], Query(description="Nombre de nodo")] = None,
    paso: Annotated[Optional[int], Query(description="Paso en segundos")] = None,
):
    fin =hasta.timestamp() if hasta else time.time()
    inicio = desde.timestamp() if desde else fin - 24 * 3600
    if inicio >= fin:
        raise HTTPException(400, "Rango de fechas invalido")
    if fin - inicio > DIAS_MAXIMOS * 24 * 3600:
        raise HTTPException(400, f"Rango de fechas demasiado grande (max {DIAS_MAXIMOS} dias)")
    paso = max(paso or int((fin - inicio) /PUNTOS_POR_DEFECTO), PASO_MINIMO)
    if (fin - inicio) / paso > PUNTOS_MAXIMOS:
        raise HTTPException(400, f"Saldrian demasiados puntos (max {PUNTOS_MAXIMOS})")
    if nodo:
        validar_nodo(nodo)
    # con los extremos en multiplos del paso, dos peticiones casi simultaneas son la misma consulta
    inicio, fin = int(inicio) // paso * paso, int(fin) // paso * paso

    def consultar():
        sufijo, unidad = MEDIDAS[medida]
        offsets = cargar_offsets()
        series = prometheus("query_range", query=selector([sufijo], nodo), start=inicio, end=fin, step=paso)["result"]
        return {
            "medida": medida,
            "unidad": unidad,
            "desde": fecha(inicio),
            "hasta": fecha(fin),
            "paso": paso,
            "series": [
                {
                    "nodo": s["metric"].get("location"),
                    "sensor": s["metric"]["__name__"].split("_")[0],
                    "valores": [
                        [fecha(t), calibrar(offsets, s["metric"].get("location"), s["metric"]["__name__"], float(v))]
                        for t, v in s["values"]
                    ],
                }
                for s in series
            ]
        }
    return con_cache(("lecturas", medida, nodo, inicio, fin, paso), min(paso, 30), consultar)

@app.get("/api/sala")
def sala():
    """Geometria de la sala en metros: contorno, elementos interiores y puertas (modelo/sala.json)."""
    try:
        with open(RUTA_SALA, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "No se pudo leer modelo/sala.json") from exc

@app.get("/api/gemelo")
def gemelo():
    """Modelo termico en vivo: lo medido en las ultimas 24 h frente a lo que el modelo previo 2 h antes."""
    try:
        # los datos son promedios de 10 min: no hace falta recalcular en cada visita
        return con_cache("gemelo", 60, modelo_gemelo.calcular)
    except modelo_gemelo.SinModelo as exc:
        raise HTTPException(503, "El modelo termico no esta entrenado: ejecuta modelo/entrenar.py") from exc
    except prom.ERRORES as exc:
        raise HTTPException(503, f"Prometheus no respondio: {exc}") from exc

@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(RUTA_PANEL, media_type="text/html")

@app.get("/api/alertas")
def alertas():
    def listar():
        return [
            {
                "alerta": a["labels"].get("alertname"),
                "nodo": a["labels"].get("nodo") or a["labels"].get("location"),
                "sensor": a["labels"].get("sensor"),
                "severidad": a["labels"].get("severity"),
                "estado": a.get("state"),
                "desde": a.get("activeAt"),
                "resumen": a.get("annotations", {}).get("resumen"),
            }
            for a in prometheus("alerts")["alerts"]
        ]
    return con_cache("alertas", 4, listar)
