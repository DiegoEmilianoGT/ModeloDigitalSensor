from config import AYUDA, MEDIDAS, SIN_ACCESO, log
from csv_export import exportar_csv
from alertas import comando_activar, comando_silenciar, formatear_alertas
from consultas import formatear_estado, formatear_metrica
from graficas import MENSAJE_GRAFICAS, enviar_grafica
from telegram_api import TECLADO_GRAFICAS, TECLADO_MENU, enviar_mensaje, telegram
from usuarios import (
    comando_revocar,
    comando_solicitar,
    comando_usuarios,
    resolver_solicitud,
    tiene_acceso,
)


def ejecutar(chat_id, accion, args):
    if accion == "estado":
        enviar_mensaje(chat_id, formatear_estado())
    elif accion == "alertas":
        enviar_mensaje(chat_id, formatear_alertas())
    elif accion in MEDIDAS:
        enviar_mensaje(chat_id, formatear_metrica(accion))
    elif accion in ("grafica", "graficas"):
        if len(args) >= 2:
            enviar_grafica(chat_id, args[0].lower(), args[1].lower())
        else:
            enviar_mensaje(chat_id, MENSAJE_GRAFICAS, TECLADO_GRAFICAS)
    elif accion == "csv":
        exportar_csv(chat_id)
    elif accion == "silenciar":
        comando_silenciar(chat_id)
    elif accion == "activar":
        comando_activar(chat_id)
    elif accion == "usuarios":
        comando_usuarios(chat_id)
    elif accion == "revocar":
        comando_revocar(chat_id, args)
    else:
        enviar_mensaje(chat_id, AYUDA, TECLADO_MENU)


def parsear_comando(texto):
    partes = texto.strip().split()
    if not partes or not partes[0].startswith("/"):
        return "menu", []
    return partes[0][1:].split("@")[0].lower(), partes[1:]


def accion_de_callback(data):
    partes = data.split(":")
    if partes[0] == "cmd":
        return partes[1], []
    if partes[0] == "graf":
        return "grafica", partes[1:]
    return "menu", []


def procesar_update(update):
    cb = update.get("callback_query")
    if cb:
        chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
        data = cb.get("data", "")

        if data.startswith("acc:"):
            _, decision, objetivo = data.split(":", 2)
            log.info("%s resuelve solicitud de %s: %s", chat_id, objetivo, decision)
            texto = resolver_solicitud(chat_id, objetivo, decision == "aprobar")
            telegram("answerCallbackQuery", json={"callback_query_id": cb["id"], "text": texto})
            return

        telegram("answerCallbackQuery", json={"callback_query_id": cb["id"]})
        if not tiene_acceso(chat_id):
            log.info("Chat no autorizado: %s", chat_id)
            return
        accion, args = accion_de_callback(data)
        log.info("Boton de %s: %s %s", chat_id, accion, args)
        ejecutar(chat_id, accion, args)
        return

    mensaje = update.get("message")
    if not mensaje or "text" not in mensaje:
        return
    chat_id = str(mensaje["chat"]["id"])
    accion, args = parsear_comando(mensaje["text"])

    if not tiene_acceso(chat_id):
        if accion == "solicitar":
            comando_solicitar(chat_id, mensaje.get("from", {}))
        else:
            log.info("Chat no autorizado: %s", chat_id)
            enviar_mensaje(chat_id, SIN_ACCESO)
        return

    log.info("Comando de %s: %s %s", chat_id, accion, args)
    ejecutar(chat_id, accion, args)
