#Lecturas de los sensores

from config import ETIQUETAS, MEDIDAS, log
from prometheus_api import ERRORES_PROM, prom_query
from texto import acortar, bloque


def leer_todo():
    lecturas, jobs_up = {}, {}
    try:
        for r in prom_query('{__name__=~"(bme280|dht22)_.+"}'):
            metrica = r["metric"].get("__name__")
            if metrica in ETIQUETAS:
                location = r["metric"].get("location", "desconocido")
                lecturas.setdefault(location, {})[metrica] = float(r["value"][1])
    except ERRORES_PROM as exc:
        log.warning("No se pudieron consultar las metricas: %s", exc)
    try:
        for r in prom_query('up{job=~"bme280|dht22"}'):
            jobs_up[r["metric"].get("job", "?")] = float(r["value"][1])
    except ERRORES_PROM as exc:
        log.warning("No se pudo consultar up: %s", exc)
    return lecturas, jobs_up


def formatear_estado():
    lecturas, jobs_up = leer_todo()
    if not lecturas and not jobs_up:
        return "No se pudo contactar a Prometheus. Revisa que el servicio este activo."

    partes = []
    if jobs_up:
        partes.append(bloque("Conexion", [
            (job.upper(), "en linea" if valor == 1 else "SIN RESPUESTA")
            for job, valor in sorted(jobs_up.items())
        ]))

    for location in sorted(lecturas):
        filas = []
        for metrica, (nombre, unidad) in ETIQUETAS.items():
            if metrica not in lecturas[location]:
                continue
            valor = lecturas[location][metrica]
            if metrica.endswith("_up"):
                texto = "En linea" if valor == 1 else "SIN RESPUESTA"
            elif metrica.endswith("_total"):
                texto = f"{valor:.0f}"
            else:
                texto = f"{valor:.2f} {unidad}"
            filas.append((nombre, texto))
        partes.append(bloque(acortar(location), filas))
    return "\n".join(partes)


def formatear_metrica(clave):
    sufijo, nombre, unidad = MEDIDAS[clave]
    lecturas, _ = leer_todo()
    filas = [
        (acortar(location), f"{valor:.2f} {unidad}")
        for location, valores in sorted(lecturas.items())
        for metrica, valor in valores.items()
        if metrica.endswith(sufijo)
    ]
    if not filas:
        return f"Sin datos de {nombre.lower()} por ahora."
    return bloque(nombre, filas)
