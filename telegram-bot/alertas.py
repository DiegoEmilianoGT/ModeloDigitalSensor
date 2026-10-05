# Vigilancia de alertas: las lee de Prometheus

import json
import re
import time
from datetime import datetime

from config import ALERT_COOLDOWN_SEC, TITULOS, log
from prometheus_api import ERRORES_PROM, prom_alertas
from telegram_api import enviar_mensaje
from texto import SANGRIA, acortar, esc
from usuarios import avisar_a_todos

estado_alertas = {}
ultimo_aviso = {}
alertas_silenciadas = False
alertas_inicializadas = False


def parsear_iso(iso):
    try:
        return datetime.fromisoformat(re.sub(r"\.\d+", "", iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def hora_local(iso):
    dt = parsear_iso(iso)
    return dt.astimezone().strftime("%H:%M") if dt else "?"


def duracion(segundos):
    minutos = max(int(segundos // 60), 1)
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60} h {minutos % 60} min"


def clave_alerta(alerta):
    return json.dumps(alerta.get("labels", {}), sort_keys=True)


def info_alerta(alerta):
    labels = alerta.get("labels", {})
    notas = alerta.get("annotations", {})
    inicio = parsear_iso(alerta.get("activeAt"))
    return {
        "nombre": labels.get("alertname", "?"),
        "nodo": acortar(labels.get("nodo") or labels.get("location") or labels.get("job", "?").upper()),
        "ip": labels.get("instance", "").split(":")[0],
        "resumen": notas.get("resumen") or notas.get("summary") or "",
        "desde": hora_local(alerta.get("activeAt")),
        "desde_ts": inicio.timestamp() if inicio else None,
        "estado": alerta.get("state", "?"),
        "notificada": False,
    }


def linea_alerta(info):
    lineas = [f"<b>{esc(TITULOS.get(info['nombre'], info['nombre']))}: {esc(info['nodo'])}</b>"]
    if info["nombre"] == "NodoCaido":
        lineas.append(f"{SANGRIA}Sin respuesta desde las {info['desde']}")
        if info["ip"]:
            lineas.append(f"{SANGRIA}IP {esc(info['ip'])}")
    else:
        if info["resumen"]:
            lineas.append(f"{SANGRIA}{esc(acortar(info['resumen']))}")
        lineas.append(f"{SANGRIA}Desde las {info['desde']}")
    return "\n".join(lineas)


def linea_resuelta(info):
    if info["nombre"] == "NodoCaido":
        titulo, etiqueta = f"Nodo recuperado: {info['nodo']}", "Estuvo caido"
    else:
        titulo = f"Resuelto: {TITULOS.get(info['nombre'], info['nombre'])} - {info['nodo']}"
        etiqueta = "Duro"
    texto = f"<b>{esc(titulo)}</b>"
    if info["desde_ts"]:
        texto += f"\n{SANGRIA}{etiqueta} {duracion(time.time() - info['desde_ts'])}"
    return texto


def estado_silencio():
    if alertas_silenciadas:
        return "Alertas silenciadas. Usa /activar para reanudarlas."
    return "Las alertas estan activas."


def formatear_alertas():
    try:
        activas = [info_alerta(a) for a in prom_alertas()]
    except ERRORES_PROM as exc:
        log.warning("No se pudo consultar las alertas: %s", exc)
        return "No se pudo contactar a Prometheus."
    cuerpo = "\n\n".join(
        linea_alerta(info) + ("" if info["estado"] == "firing" else " (pendiente)")
        for info in sorted(activas, key=lambda i: i["nombre"])
    ) or "Sin alertas activas."
    return f"<b>Alertas</b>\n{cuerpo}\n\n{estado_silencio()}"


def revisar_alertas():
    global alertas_inicializadas
    try:
        crudas = prom_alertas()
    except ERRORES_PROM as exc:
        log.warning("No se pudo consultar las alertas: %s", exc)
        return  # Prometheus no respondio

    firing = {clave_alerta(a): info_alerta(a) for a in crudas if a.get("state") == "firing"}
    ahora = time.time()

    resueltas = []
    for clave in list(estado_alertas):
        if clave not in firing:
            info = estado_alertas.pop(clave)
            if info["notificada"]:
                resueltas.append(info)

    for clave, info in firing.items():
        if clave not in estado_alertas:
            info["notificada"] = not alertas_inicializadas
            estado_alertas[clave] = info
    alertas_inicializadas = True

    nuevas = []
    if not alertas_silenciadas:
        for clave, info in estado_alertas.items():
            if info["notificada"]:
                continue
            if info["nombre"] != "NodoCaido" and ahora - ultimo_aviso.get(clave, 0.0) < ALERT_COOLDOWN_SEC:
                continue  # caidas de nodo: siempre se avisan
            info["notificada"] = True
            ultimo_aviso[clave] = ahora
            nuevas.append(info)
    else:
        resueltas = []

    if not nuevas and not resueltas:
        return
    partes = [linea_alerta(i) for i in nuevas] + [linea_resuelta(i) for i in resueltas]
    avisar_a_todos("\n\n".join(partes))


def comando_silenciar(chat_id):
    global alertas_silenciadas
    alertas_silenciadas = True
    enviar_mensaje(chat_id, "Alertas silenciadas. Los comandos siguen funcionando; usa /activar para reanudarlas.")


def comando_activar(chat_id):
    global alertas_silenciadas
    alertas_silenciadas = False
    enviar_mensaje(chat_id, "Alertas activadas.")
