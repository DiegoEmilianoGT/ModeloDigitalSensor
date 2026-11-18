#pragma once

#include "config.h"

#if defined(SENSOR_BME280)
#include "sensors/BME280Sensor.h"
extern BME280Sensor bme;
#endif
#if defined(SENSOR_DHT22)
#include "sensors/DHT22Sensor.h"
extern DHT22Sensor dht22;
#endif

void iniciarSensores();
void actualizarSensores();
