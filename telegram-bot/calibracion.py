OFFSETS = {
    "bme280_temperatura_celsius": 0.0,
    "bme280_humedad_porcentaje": 0.0,

    "dht22_temperatura_celsius": 0.0,
    "dht22_humedad_porcentaje": 0.0,
}

def calibrar(metrica, valor):
    return valor + OFFSETS.get(metrica, 0.0)
