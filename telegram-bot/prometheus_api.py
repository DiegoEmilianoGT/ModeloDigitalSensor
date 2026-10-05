import requests

from config import PROMETHEUS_URL

ERRORES_PROM = (requests.RequestException, ValueError, KeyError)


def prom_get(ruta, timeout=10, **params):
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/{ruta}", params=params, timeout=timeout)
    try:
        cuerpo = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise
    if cuerpo.get("status") != "success":
        raise ValueError(cuerpo.get("error", f"HTTP {resp.status_code}"))
    return cuerpo["data"]


def prom_query(expr):
    return prom_get("query", query=expr)["result"]


def prom_alertas():
    return prom_get("alerts")["alerts"]
