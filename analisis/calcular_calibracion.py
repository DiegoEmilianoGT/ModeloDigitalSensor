import csv
import os
import statistics
import sys
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from comun import prometheus

VENTANA = 120  
PASO = 15
CONSULTA = '{__name__=~"(bme280|dht22)_(temperatura_celsius|humedad_porcentaje)"}'
MEDIDAS = ("temperatura", "humedad")
DISPERSION_MAXIMA = {"temperatura": 0.3, "humedad": 2.0}


def leer_referencia(ruta):
    lecturas = []
    with open(ruta, newline="", encoding="utf-8-sig") as archivo:
        for fila in csv.DictReader(archivo):
            texto = fila["Times"].strip()
            formato = "%Y-%m-%d %H:%M:%S" if texto.count(":") == 2 else "%Y-%m-%d %H:%M"
            marca = int(datetime.strptime(texto, formato).timestamp())
            valores = {m: float(fila[m]) for m in MEDIDAS if (fila.get(m) or "").strip()}
            lecturas.append((marca, valores))
    return lecturas


def promedios_nodos(marca):
    
    promedios = {}
    for serie in prometheus.rango(CONSULTA, marca - VENTANA, marca + VENTANA, PASO, timeout=30):
        clave = (serie["metric"].get("location", "?"), serie["metric"]["__name__"])
        promedios[clave] = statistics.mean(float(v) for _, v in serie["values"])
    return promedios


def medida_de(metrica):
    return "temperatura" if "temperatura" in metrica else "humedad"


def comando_bot(nodo, metrica, offset):
    sensor = metrica.split("_")[0]
    extra = "" if nodo.startswith(sensor) else f" {sensor}"
    medida = "temp" if medida_de(metrica) == "temperatura" else "humedad"
    return f"/calibrar {nodo}{extra} {medida} {offset:.2f}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python3 calcular_calibracion.py referencia.csv  (columnas: Times, temperatura, humedad)")

    diferencias = {}
    for marca, referencia in leer_referencia(sys.argv[1]):
        for (nodo, metrica), valor in promedios_nodos(marca).items():
            if medida_de(metrica) in referencia:
                diferencias.setdefault((nodo, metrica), []).append(referencia[medida_de(metrica)] - valor)

    if not diferencias:
        print("Los nodos no tienen datos en Prometheus a la hora de esas lecturas.")
        sys.exit(1)

    print(f"{'nodo':<22} {'metrica':<28} {'lecturas':>8} {'offset':>8} {'dispersion':>11}")
    confiables = []
    for (nodo, metrica), difs in sorted(diferencias.items()):
        offset = statistics.median(difs)
        dispersion = statistics.stdev(difs) if len(difs) > 1 else float("nan")
        aviso = ""
        if len(difs) < 3:
            aviso = "  <- pocas lecturas"
        elif dispersion > DISPERSION_MAXIMA[medida_de(metrica)]:
            aviso = "  <- varia mucho, no lo apliques"
        else:
            confiables.append(comando_bot(nodo, metrica, offset))
        print(f"{nodo:<22} {metrica:<28} {len(difs):>8} {offset:>+8.2f} {dispersion:>11.2f}{aviso}")

    if confiables:
        print("\nComandos para el bot:")
        print("\n".join(confiables))
