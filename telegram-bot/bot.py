#Punto de entrada del bot: solo el bucle principal.

import time

from alertas import revisar_alertas
from comandos import procesar_update
from config import ADMIN_CHAT_IDS, CHECK_INTERVAL_SEC, log
from graficas import GRAFICAS_OK
from telegram_api import telegram
from usuarios import registrar_comandos, usuarios


def bucle_principal():
    log.info("Bot iniciado. Administradores: %s", ADMIN_CHAT_IDS)
    log.info("Usuarios aprobados: %s", list(usuarios["aprobados"]))
    if not GRAFICAS_OK:
        log.warning("matplotlib no esta instalado: /grafica deshabilitado")
    registrar_comandos()
    offset = 0
    ultima_verificacion = 0.0
    while True:
        if time.time() - ultima_verificacion >= CHECK_INTERVAL_SEC:
            ultima_verificacion = time.time()
            try:
                revisar_alertas()
            except Exception:
                log.exception("Error revisando alertas")

        datos = telegram(
            "getUpdates",
            timeout=25,
            json={"offset": offset, "timeout": 10, "allowed_updates": ["message", "callback_query"]},
        )
        if datos is None:
            time.sleep(5)
            continue

        for update in datos.get("result", []):
            offset = update["update_id"] + 1
            try:
                procesar_update(update)
            except Exception:
                log.exception("Error procesando update %s", update.get("update_id"))


if __name__ == "__main__":
    bucle_principal()
