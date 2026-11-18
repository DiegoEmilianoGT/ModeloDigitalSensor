import os
import sys
import time
import requests

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from comun import prometheus
from comun.nodos import nodos_conocidos

INTERVALO = 30
# el nodo parpadea si pasan 5 min sin ordenes: la misma orden se repite antes de eso,
# y un cambio se manda en la siguiente vuelta
REPETIR_CADA = 120
ALERTAS_CON_LED = {"TemperaturaAlta", "TemperaturaBaja", "HumedadAlta", "HumedadBaja"}


def nodos_en_alerta():
    return {
        a["labels"].get("nodo") or a["labels"].get("location")
        for a in prometheus.alertas()
        if a.get("state") == "firing" and a["labels"].get("alertname") in ALERTAS_CON_LED
    }


def mandar_orden(host, encendido):
    resp = requests.post(f"http://{host}/led", data={"estado": "1" if encendido else "0"}, timeout=(2, 3))
    resp.raise_for_status()


def revisar(ordenes, avisos):
    """ordenes: nodo -> (encendido, momento) de la ultima orden recibida; avisos: lo ultimo que se imprimio."""
    try:
        en_alerta = nodos_en_alerta()
    except prometheus.ERRORES as exc:
        # Sin Prometheus no se sabe si hay alertas: no se manda nada y, a los 5 min, los LED parpadean
        if avisos.get("prometheus") != "error":
            print(f"No se pudieron leer las alertas de Prometheus: {exc}")
        avisos["prometheus"] = "error"
        return
    avisos["prometheus"] = "ok"

    ahora = time.time()
    for nodo, host in nodos_conocidos().items():
        encendido = nodo in en_alerta
        orden = ordenes.get(nodo)
        if orden and orden[0] == encendido and ahora - orden[1] < REPETIR_CADA:
            continue
        try:
            mandar_orden(host, encendido)
            ordenes[nodo] = (encendido, ahora)
            estado = "encendido" if encendido else "apagado"
        except requests.RequestException:
            ordenes.pop(nodo, None)  # se reintenta en la siguiente vuelta
            estado = "sin respuesta"
        if avisos.get(nodo) != estado:
            print(f"{nodo} ({host}): LED {estado}")
            avisos[nodo] = estado


if __name__ == "__main__":
    ordenes, avisos = {}, {}
    while True:
        revisar(ordenes, avisos)
        time.sleep(INTERVALO)
