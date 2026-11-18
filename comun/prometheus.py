"""Consultas a la API HTTP de Prometheus."""
import os

import requests

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
ERRORES = (requests.RequestException, ValueError, KeyError)


def consultar(ruta, timeout=10, **params):
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/{ruta}", params=params, timeout=timeout)
    try:
        cuerpo = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise
    if cuerpo.get("status") != "success":
        raise ValueError(cuerpo.get("error", f"HTTP {resp.status_code}"))
    return cuerpo["data"]


def instantanea(expr, timeout=10):
    return consultar("query", timeout, query=expr)["result"]


def rango(expr, inicio, fin, paso, timeout=20):
    return consultar("query_range", timeout, query=expr, start=inicio, end=fin, step=paso)["result"]


def alertas():
    return consultar("alerts")["alerts"]


def recargar():
    requests.post(f"{PROMETHEUS_URL}/-/reload", timeout=10).raise_for_status()
