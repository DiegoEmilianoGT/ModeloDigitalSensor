#pragma once


#if !defined(SENSOR_BME280) && !defined(SENSOR_DHT22)
#define SENSOR_BME280
#define SENSOR_DHT22
#endif

#ifndef NODO_ID
#define NODO_ID "bme280_esp32c3_01"
#endif

#define PIN_I2C_SDA        8
#define PIN_I2C_SCL        9
#define I2C_FRECUENCIA_HZ  100000UL

#define PIN_DHT22 4
#define WIFI_TIMEOUT_MS       20000UL       
#define WIFI_REINTENTO_MS     30000UL       
#define WIFI_REINICIO_MS  (2UL*3600000UL)
#define LECTURA_INTERVALO_MS   2000UL
#define REINTENTO_BME_MS      10000UL
#define ERRORES_PARA_REINICIAR_BME 5

#define DHT22_INTERVALO_MS 3000UL

#define HEAP_MINIMO_BYTES 20000UL
#define BUFFER_ARCHIVO        "/buffer.csv"
#define BUFFER_INTERVALO_MS   (60UL*1000UL)
#define BUFFER_MAX_LECTURAS    28800UL  // 20 dias a 1 lectura/min


#define BME_TEMP_MIN     -40.0f
#define BME_TEMP_MAX      85.0f
#define BME_PRESION_MIN  300.0f
#define BME_PRESION_MAX 1100.0f
