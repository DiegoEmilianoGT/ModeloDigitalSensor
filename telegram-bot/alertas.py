import json
import re
import time
from datetime import datetime

from config import ALERT_COOLDOWN_SEC, TITULOS, log
from comun import prometheus as prom
from comun.nombres import acortar, etiqueta, sensor_extra
from modelo import gemelo
from telegram_api import enviar_mensaje
from texto import SANGRIA, esc
from usuarios import avisar_a_admins, avisar_a_todos

SILENCIO_POR_DEFECTO = 2 * 3600
SILENCIO_MAXIMO = 7 * 86400
DURACION_RE = re.compile(r"^(\d+)\s*(m|min|h|d)$")

estado_alertas = {}
ultimo_aviso = {}
silencio_hasta = 0.0
alertas_inicializadas = False
estado_gemelo = None  # (nodo, sensor) -> estado; None hasta la primera revision


def parsear_iso(iso):
    try:
        return datetime.fromisoformat(re.sub(r"\.\d+", "", iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def hora_de(dt):
    local = dt.astimezone()
    # una hora de dias anteriores lleva la fecha: sola pareceria de hoy
    es_de_hoy = local.date() == datetime.now().astimezone().date()
    return local.strftime("%H:%M" if es_de_hoy else "%H:%M del %d/%m")


def hora_local(iso):
    dt = parsear_iso(iso)
    return hora_de(dt) if dt else "?"


def duracion(segundos):
    minutos = max(int(segundos // 60), 1)
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60} h {minutos % 60} min"


def silenciadas():
    return time.time() < silencio_hasta


def clave_alerta(alerta):
    return json.dumps(alerta.get("labels", {}), sort_keys=True)


def info_alerta(alerta):
    labels = alerta.get("labels", {})
    notas = alerta.get("annotations", {})
    inicio = parsear_iso(alerta.get("activeAt"))
    nodo = labels.get("nodo") or labels.get("location") or labels.get("job", "?").upper()
    sensor = labels.get("sensor")
    return {
        "nombre": labels.get("alertname", "?"),
        "nodo": acortar(nodo) + (sensor_extra(nodo, sensor) if sensor else ""),
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
    else:
        if info["resumen"]:
            lineas.append(f"{SANGRIA}{esc(acortar(info['resumen']))}")
        lineas.append(f"{SANGRIA}Desde las {info['desde']}")
    return "\n".join(lineas)


def linea_resuelta(info):
    if info["nombre"] == "NodoCaido":
        titulo, rotulo = f"Nodo recuperado: {info['nodo']}", "Estuvo caido"
    else:
        titulo = f"Resuelto: {TITULOS.get(info['nombre'], info['nombre'])} - {info['nodo']}"
        rotulo = "Duro"
    texto = f"<b>{esc(titulo)}</b>"
    if info["desde_ts"]:
        texto += f"\n{SANGRIA}{rotulo} {duracion(time.time() - info['desde_ts'])}"
    return texto


def estado_silencio():
    if silenciadas():
        return f"Alertas silenciadas hasta las {hora_de(datetime.fromtimestamp(silencio_hasta))}. Usa /activar para reanudarlas."
    return "Las alertas estan activas."


def formatear_alertas():
    try:
        activas = [info_alerta(a) for a in prom.alertas()]
    except prom.ERRORES as exc:
        log.warning("No se pudo consultar las alertas: %s", exc)
        return "No se pudo contactar a Prometheus."
    cuerpo = "\n\n".join(
        linea_alerta(info) + ("" if info["estado"] == "firing" else " (pendiente)")
        for info in sorted(activas, key=lambda i: i["nombre"])
    ) or "Sin alertas activas."
    return f"<b>Alertas</b>\n{cuerpo}\n\n{estado_silencio()}"


def revisar_alertas():
    global alertas_inicializadas, silencio_hasta
    if silencio_hasta and not silenciadas():
        silencio_hasta = 0.0
        avisar_a_todos("Termino el silencio: las alertas vuelven a avisarse.")
    try:
        crudas = prom.alertas()
    except prom.ERRORES as exc:
        log.warning("No se pudo consultar las alertas: %s", exc)
        return  # no responde prometheus

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
    if not silenciadas():
        for clave, info in estado_alertas.items():
            if info["notificada"]:
                continue
            if info["nombre"] != "NodoCaido" and ahora - ultimo_aviso.get(clave, 0.0) < ALERT_COOLDOWN_SEC:
                continue  # las caidas de nodo se avisan siempre; lo demas espera a que pase la pausa
            info["notificada"] = True
            ultimo_aviso[clave] = ahora
            nuevas.append(info)
    else:
        resueltas = []

    if not nuevas and not resueltas:
        return
    partes = [linea_alerta(i) for i in nuevas] + [linea_resuelta(i) for i in resueltas]
    avisar_a_todos("\n\n".join(partes))


def texto_anomalia(serie):
    nombre = etiqueta(serie["nodo"], serie["sensor"])
    ultimo = next((p for p in reversed(serie["historial"]) if p[1] is not None and p[2] is not None), None)
    texto = f"<b>Anomalia termica: {esc(nombre)}</b>"
    if ultimo:
        _, medido, previsto, tolerancia, _ = ultimo
        texto += (f"\n{SANGRIA}Medido {medido:.1f} °C, el modelo esperaba {previsto:.1f} °C (tolerancia ±{tolerancia:.1f})"
                  f"\n{SANGRIA}Revisa puertas, aire acondicionado o el propio sensor. Detalle en /gemelo")
    return texto


def revisar_anomalias():
    """Avisa a los administradores cuando una zona se sale de lo que preve el modelo termico, y cuando vuelve."""
    global estado_gemelo
    try:
        series = gemelo.calcular()["series"]
    except gemelo.SinModelo:
        return
    except prom.ERRORES as exc:
        log.warning("No se pudo revisar el gemelo: %s", exc)
        return
    anterior = estado_gemelo
    estado_gemelo = {(s["nodo"], s["sensor"]): s["estado"] for s in series}
    if anterior is None or silenciadas():
        return  # al arrancar solo se toma nota, como con las alertas
    partes = []
    for s in series:
        antes = anterior.get((s["nodo"], s["sensor"]))
        if s["estado"] == "anomalia" and antes == "normal":
            partes.append(texto_anomalia(s))
        elif s["estado"] == "normal" and antes == "anomalia":
            partes.append(f"<b>{esc('Temperatura de nuevo como se esperaba: ' + etiqueta(s['nodo'], s['sensor']))}</b>")
    if partes:
        avisar_a_admins("\n\n".join(partes))


def comando_silenciar(chat_id, args):
    global silencio_hasta
    segundos = SILENCIO_POR_DEFECTO
    if args:
        coincide = DURACION_RE.match("".join(args).lower())
        if not coincide:
            enviar_mensaje(chat_id, "Uso: /silenciar [30m|2h|1d]. Sin tiempo silencia 2 h.")
            return
        cantidad, unidad = int(coincide.group(1)), coincide.group(2)
        segundos = cantidad * {"m": 60, "min": 60, "h": 3600, "d": 86400}[unidad]
    segundos = min(max(segundos, 60), SILENCIO_MAXIMO)
    silencio_hasta = time.time() + segundos
    log.info("%s silencia las alertas %s", chat_id, duracion(segundos))
    enviar_mensaje(chat_id, f"{estado_silencio()}\nLos comandos siguen funcionando.")


def comando_activar(chat_id):
    global silencio_hasta
    silencio_hasta = 0.0
    enviar_mensaje(chat_id, "Alertas activadas.")
