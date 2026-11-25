import threading

import requests

from config import BOT_TOKEN, GRAFICAS, RANGOS, log
from modelo import gemelo
from texto import sin_token

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
SESION = requests.Session()


def telegram(metodo, timeout=15, **kwargs):
    try:
        resp = SESION.post(f"{API_BASE}/{metodo}", timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        log.warning("Telegram %s: %s", metodo, sin_token(exc))
        return None
    if not resp.ok:
        log.warning("Telegram %s fallo: %s %s", metodo, resp.status_code, resp.text[:200])
        return None
    try:
        return resp.json()
    except ValueError:
        log.warning("Telegram %s devolvio algo que no es JSON", metodo)
        return None


def sin_esperar(*llamadas):
    def hacer():
        for metodo, cuerpo in llamadas:
            telegram(metodo, json=cuerpo)
    threading.Thread(target=hacer, daemon=True).start()


def avisar_accion(chat_id, accion):
    sin_esperar(("sendChatAction", {"chat_id": chat_id, "action": accion}))


def enviar_mensaje(chat_id, texto, teclado=None):
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if teclado:
        payload["reply_markup"] = teclado
    telegram("sendMessage", json=payload)


def subir(chat_id, metodo, campo, nombre, contenido, tipo, pie):
    return telegram(
        metodo,
        timeout=60,
        data={"chat_id": chat_id, "caption": pie, "parse_mode": "HTML"},
        files={campo: (nombre, contenido, tipo)},
    )


def enviar_archivo(chat_id, metodo, campo, nombre, contenido, tipo, pie):
    if subir(chat_id, metodo, campo, nombre, contenido, tipo, pie) is None:
        enviar_mensaje(chat_id, "No se pudo enviar el archivo, intenta de nuevo.")


def reenviar_foto(chat_id, file_id, pie):
    # una foto que Telegram ya tiene se manda por su identificador
    return telegram("sendPhoto", json={"chat_id": chat_id, "photo": file_id, "caption": pie, "parse_mode": "HTML"})


def boton(texto, data):
    return {"text": texto, "callback_data": data}


FILAS_GRAFICAS = [
    [boton(f"{nombre} {rango}", f"graf:{clave}:{rango}") for rango in RANGOS]
    for clave, (nombre, _, _) in GRAFICAS.items()
]
TECLADO_GRAFICAS = {"inline_keyboard": FILAS_GRAFICAS}
TECLADO_MENU = {"inline_keyboard": [
    [boton("Estado", "cmd:estado"), boton("Alertas", "cmd:alertas")],
    [boton("Temperatura", "cmd:temp"), boton("Humedad", "cmd:humedad")],
    [boton("Presion", "cmd:presion"), boton("Senal WiFi", "cmd:rssi")],
    [boton("Graficas", "cmd:grafica")] + ([boton("Gemelo", "cmd:gemelo")] if gemelo.ACTIVO else []),
    [boton("Silenciar alertas", "cmd:silenciar"), boton("Activar alertas", "cmd:activar")],
]}
