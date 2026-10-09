OFFSETS = {
    "bme280_temperatura_celsius": 0.0,
    "bme280_humedad_porcentaje": 0.0,

    "dht22_temperatura_celsius": 0.0,
    "dht22_humedad_porcentaje": 0.0,
}

def calibrar_sensores(df, offsets):
    df = df.copy()
    for columna in df.columns:
        _, _, metrica = columna.partition(" -_")
        if metrica in offsets:
            df[columna] += offsets[metrica]
    return df

