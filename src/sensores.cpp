#include "sensores.h"

#if defined(SENSOR_BME280)
BME280Sensor bme;
#endif
#if defined(SENSOR_DHT22)
DHT22Sensor dht22(PIN_DHT22);
#endif

void iniciarSensores() {
#if defined(SENSOR_BME280)
  bme.begin();
#endif
#if defined(SENSOR_DHT22)
  dht22.begin();
#endif
}

void actualizarSensores() {
#if defined(SENSOR_BME280)
  bme.update();
#endif
#if defined(SENSOR_DHT22)
  dht22.update();
#endif
}
