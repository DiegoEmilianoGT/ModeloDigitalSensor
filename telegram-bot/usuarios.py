import json
import os
from datetime import datetime

from config import ADMIN_CHAT_IDS, COMANDOS_ADMIN, COMANDOS_BOT, COMANDOS_PUBLICOS, USUARIOS_PATH, log
from telegram_api import boton, enviar_mensaje, telegram
from texto import SANGRIA, bloque, esc


def cargar_usuarios():
    try:
        with open(USUARIOS_PATH, encoding="utf-8") as f:
            datos = json.load(f)
    except FileNotFoundError:
        return {"aprobados": {}, "pendientes": {}}
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("No se pudo leer %s: %s", USUARIOS_PATH, exc)
        return {"aprobados": {}, "pendientes": {}}
    datos.setdefault("aprobados", {})
    datos.setdefault("pendientes", {})
    return datos


def guardar_usuarios(datos):
    tmp = USUARIOS_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, USUARIOS_PATH)
    except OSError as exc:
        log.warning("No se pudo guardar %s: %s", USUARIOS_PATH, exc)


usuarios = cargar_usuarios()


def usuarios_autorizados():
    return ADMIN_CHAT_IDS | set(usuarios["aprobados"])


def tiene_acceso(chat_id):
    return chat_id in usuarios_autorizados()


def es_admin(chat_id):
    return chat_id in ADMIN_CHAT_IDS


def avisar_a_todos(texto, teclado=None):
    for chat_id in usuarios_autorizados():
        enviar_mensaje(chat_id, texto, teclado)


def avisar_a_admins(texto, teclado=None):
    for chat_id in ADMIN_CHAT_IDS:
        enviar_mensaje(chat_id, texto, teclado)


def nombre_de(persona):
    nombre = " ".join(p for p in [persona.get("first_name"), persona.get("last_name")] if p)
    usuario = f"@{persona['username']}" if persona.get("username") else ""
    return " ".join(p for p in [nombre, usuario] if p) or "sin nombre"


def comando_solicitar(chat_id, persona):
    if tiene_acceso(chat_id):
        enviar_mensaje(chat_id, "Ya tienes acceso. Escribe /menu para empezar.")
        return
    if chat_id in usuarios["pendientes"]:
        enviar_mensaje(chat_id, "Tu solicitud ya esta pendiente de revision.")
        return
    usuarios["pendientes"][chat_id] = {
        "nombre": nombre_de(persona),
        "fecha": datetime.now().astimezone().isoformat(),
    }
    guardar_usuarios(usuarios)
    enviar_mensaje(chat_id, "Solicitud enviada. Te aviso en cuanto la revisen.")
    teclado = {"inline_keyboard": [[
        boton("Aprobar", f"acc:aprobar:{chat_id}"),
        boton("Rechazar", f"acc:rechazar:{chat_id}"),
    ]]}
    avisar_a_admins(
        f"<b>Solicitud de acceso</b>\n{SANGRIA}{esc(usuarios['pendientes'][chat_id]['nombre'])}\n{SANGRIA}ID {esc(chat_id)}",
        teclado,
    )


def resolver_solicitud(admin_id, chat_id, aprobar):
    if not es_admin(admin_id):
        return "No tienes permiso para hacer esto."
    pendiente = usuarios["pendientes"].pop(chat_id, None)
    if pendiente is None:
        return "Esa solicitud ya fue resuelta."
    if aprobar:
        usuarios["aprobados"][chat_id] = {
            "nombre": pendiente["nombre"],
            "aprobado_por": admin_id,
            "fecha": datetime.now().astimezone().isoformat(),
        }
        guardar_usuarios(usuarios)
        actualizar_comandos_de(chat_id)
        enviar_mensaje(chat_id, "Tu acceso fue aprobado. Escribe /menu para empezar.")
        return f"Aprobado: {pendiente['nombre']}"
    guardar_usuarios(usuarios)
    enviar_mensaje(chat_id, "Tu solicitud de acceso fue rechazada.")
    return f"Rechazado: {pendiente['nombre']}"


def comando_usuarios(chat_id):
    if not es_admin(chat_id):
        enviar_mensaje(chat_id, "No tienes permiso para ver esto.")
        return
    filas = [(info["nombre"], f"ID {cid}") for cid, info in usuarios["aprobados"].items()]
    filas += [(info["nombre"], f"ID {cid} (pendiente)") for cid, info in usuarios["pendientes"].items()]
    if not filas:
        enviar_mensaje(chat_id, "No hay usuarios aprobados ni solicitudes pendientes.")
        return
    enviar_mensaje(chat_id, bloque("Usuarios", filas))


def comando_revocar(chat_id, args):
    if not es_admin(chat_id):
        enviar_mensaje(chat_id, "No tienes permiso para hacer esto.")
        return
    if not args:
        enviar_mensaje(chat_id, "Uso: /revocar <ID> (mira los ID con /usuarios)")
        return
    objetivo = args[0]
    if usuarios["aprobados"].pop(objetivo, None) is None:
        enviar_mensaje(chat_id, f"El ID {objetivo} no estaba aprobado.")
        return
    guardar_usuarios(usuarios)
    actualizar_comandos_de(objetivo)
    enviar_mensaje(chat_id, f"Acceso revocado para el ID {objetivo}.")
    enviar_mensaje(objetivo, "Tu acceso a este bot fue revocado.")


def comandos_para(chat_id):
    if es_admin(chat_id):
        return COMANDOS_BOT + COMANDOS_ADMIN
    if chat_id in usuarios["aprobados"]:
        return COMANDOS_BOT
    return COMANDOS_PUBLICOS


def actualizar_comandos_de(chat_id):
    telegram("setMyCommands", json={
        "commands": [{"command": c, "description": d} for c, d in comandos_para(chat_id)],
        "scope": {"type": "chat", "chat_id": chat_id},
    })


def registrar_comandos():
    telegram("setMyCommands", json={
        "commands": [{"command": c, "description": d} for c, d in COMANDOS_PUBLICOS]})
    for chat_id in usuarios_autorizados():
        actualizar_comandos_de(chat_id)