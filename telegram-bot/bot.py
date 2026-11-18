import time

from config import ADMIN_CHAT_IDS, ANOMALIAS_INTERVAL_SEC, CHECK_INTERVAL_SEC, log
from alertas import revisar_alertas, revisar_anomalias
from calibracion import AVISO_DESFASE, reglas_al_dia
from comandos import procesar_update
from graficas import GRAFICAS_OK, WEBP_OK
from telegram_api import telegram
from usuarios import avisar_a_admins, registrar_comandos, usuarios


def cada(segundos, tarea, ultima):
    """Corre la tarea si ya paso el intervalo; devuelve el momento de la ultima corrida."""
    if time.time() - ultima < segundos:
        return ultima
    try:
        tarea()
    except Exception:
        log.exception("Error en %s", tarea.__name__)
    return time.time()


def bucle_principal():
    log.info("Bot iniciado. Administradores: %s", ADMIN_CHAT_IDS)
    log.info("Usuarios aprobados: %s", list(usuarios["aprobados"]))
    if not GRAFICAS_OK:
        log.warning("matplotlib no esta instalado: /grafica deshabilitado")
    elif not WEBP_OK:
        log.warning("Pillow sin WebP: las graficas se envian en PNG")
    registrar_comandos()
    if not reglas_al_dia():
        log.warning("calibracion.json no coincide con las reglas de Prometheus")
        avisar_a_admins(AVISO_DESFASE)
    offset = 0
    ultima_alerta = ultima_anomalia = 0.0
    while True:
        ultima_alerta = cada(CHECK_INTERVAL_SEC, revisar_alertas, ultima_alerta)
        ultima_anomalia = cada(ANOMALIAS_INTERVAL_SEC, revisar_anomalias, ultima_anomalia)

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
