import os
import time
import glob
import json
import requests

PROMETHEUS_URL = "http://localhost:9090"
INTERVALO = 30
ALERTAS_CON_LED = {"TemperaturaAlta", "TemperaturaBaja", "HumedadAlta", "HumedadBaja"}
CARPETA_TARGETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "targets")

def nodos_conocidos():
    nodos = {}
    for ruta in glob.glob(os.path.join(CARPETA_TARGETS, "*.json")):
        try:
            with open(ruta, encoding="utf-8") as f:
                for entrada in json.load(f):
                    nodos[entrada["labels"]["nodo"]] = entrada["targets"][0]
        except (OSError, ValueError, KeyError, IndexError) as exc:
            print(f"No se pudo leer {ruta}: {exc}")
    return nodos

def nodos_en_alerta():
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/alerts", timeout=10)
    resp.raise_for_status()
    return {
        a["labels"].get("nodo") or a["labels"].get("location")
        for a in resp.json()["data"]["alerts"]
        if a.get("state") == "firing" and a["labels"].get("alertname") in ALERTAS_CON_LED
    }


def mandar_orden(host, encendido):
    resp = requests.post(f"http://{host}/led", data={"estado": "1" if encendido else "0"}, timeout=(2, 3))
    resp.raise_for_status()


def revisar(ultimo):
    try:
        en_alerta = nodos_en_alerta()
    except (requests.RequestException, ValueError, KeyError) as exc:
        # Sin Prometheus no se sabe si hay alertas: no se manda nada y, a los 5 min, los LED parpadean
        if ultimo.get("prometheus") != "error":
            print(f"No se pudieron leer las alertas de Prometheus: {exc}")
        ultimo["prometheus"] = "error"
        return
    ultimo["prometheus"] = "ok"

    for nodo, host in nodos_conocidos().items():
        encendido = nodo in en_alerta
        try:
            mandar_orden(host, encendido)
            estado = "encendido" if encendido else "apagado"
        except requests.RequestException:
            estado = "sin respuesta"
        if ultimo.get(nodo) != estado:
            print(f"{nodo} ({host}): LED {estado}")
            ultimo[nodo] = estado


if __name__ == "__main__":
    ultimo = {}
    while True:
        revisar(ultimo)
        time.sleep(INTERVALO)