import requests
import re
import time
from typing import Annotated, Optional, Literal
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

PROMETHEUS_URL = "http://localhost:9090"
NODO_RE = re.compile(r"^[a-z0-9_]+$")
MEDIDAS ={
    "temperatura": ("temperatura_celsius_calibrada", "°C"),
    "humedad": ("humedad_porcentaje_calibrada", "%"),
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
dd
def prometheus(ruta, **params):
    try:
        resp= requests.get(f"{PROMETHEUS_URL}/api/v1/{ruta}", params=params, timeout=20)
        cuerpo=resp.json()
    except (requests.RequestException, ValueError) as exc:
            raise HTTPException(503, f"Prometheus no respondio: {exc}") from exc
    if cuerpo.get("status") != "success":
        raise HTTPException(502, f"Prometheus error: {cuerpo}")
    return cuerpo["data"]

def fecha(marca):
    return datetime.fromtimestamp(float(marca)).astimezone().isoformat(timespec="seconds")

def validar_nodo(nodo):
    if not NODO_RE.match(nodo):
        raise HTTPException(400, f"Nombre de nodo invalido")

def selector(sufijos,nodo=None):
    filtro = f', location="{nodo}"' if nodo else ""
    return '{__name__=~"(bme280|dht22)_(%s)"%s}' % ("|".join(sufijos), filtro)


@app.get("/api/salud")
def salud():
    prometheus("query", query="vector(1)")
    return {"api": "ok","prometheus": "ok"}

@app.get("/api/nodos")
def nodos():
    resultado = {}
    for r in prometheus("query", query='up{job=~"bme280|dht22"}')["result"]:
        nodo = r["metric"].get("nodo", "?")
        resultado[nodo] = {
            "nodo": nodo,
            "en_linea": r["value"][1] == "1",
            "direccion": r["metric"].get("instance"),
            "sensores": [],
        }
    for r in prometheus("query", query='{__name__=~"(bme280|dht22)_sensor_up"}')["result"]:
        nodo = r["metric"].get("location")
        if nodo in resultado:
            resultado[nodo]["sensores"].append(r["metric"]["__name__"].split("_")[0])
    return sorted(resultado.values(), key=lambda n: n["nodo"])

@app.get("/api/nodos/{nodo}")
def lectura_actual(nodo: str):
    validar_nodo(nodo)
    sufijos = [sufijo for sufijo, _ in MEDIDAS.values()]
    resultados = prometheus("query", query=selector(sufijos, nodo))["result"]
    if not resultados:
        raise HTTPException(404, f"Nodo {nodo} no encontrado")

    lecturas = {}
    for r in resultados:
        sensor, _, sufijo = r["metric"]["__name__"].partition("_")
        lecturas.setdefault(sensor, {})[MEDIDA_DE_SUFIJO[sufijo]] = round(float(r["value"][1]), 2)
    arriba = prometheus("query", query=f'up{{nodo="{nodo}"}}')["result"]
    return {
        "nodo": nodo,
        "en_linea": any(r["value"][1] == "1" for r in arriba),
        "momento": fecha(resultados[0]["value"][0]),
        "lecturas": lecturas,
    }

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

    sufijo, unidad = MEDIDAS[medida]
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
                "valores": [[fecha(t), round(float(v), 2)] for t, v in s["values"]],
            }
            for s in series
        ]
    }

@app.get("/", include_in_schema=False)
def inicio():
    return RedirectResponse("/docs")

@app.get("/api/alertas")
def alertas():
    return [
        {
            "alerta": a["labels"].get("alertname"),
            "nodo": a["labels"].get("nodo") or a["labels"].get("location"),
            "sensor": a["labels"].get("sensor"),
            "estado": a.get("state"),
            "desde": a.get("activeAt"),
            "resumen": a.get("annotations", {}).get("resumen"),
        } 
        for a in prometheus("alerts")["alerts"]
    ]