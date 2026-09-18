#include "DHT22Sensor.h"
#include "config.h"
#include <Arduino.h>

DHT22Sensor::DHT22Sensor(uint8_t pin) : dht_(pin, DHT22) {}

void DHT22Sensor::begin() {
  dht_.begin();
  lastReadMs_ = millis() - DHT22_INTERVALO_MS;  // fuerza la primera lectura
}

void DHT22Sensor::update() {
  const unsigned long ahora = millis();

  // DHT22 necesita >=2s entre lecturas
  if (ahora - lastReadMs_ < DHT22_INTERVALO_MS) return;
  lastReadMs_ = ahora;

  const float humedad     = dht_.readHumidity();
  const float temperatura = dht_.readTemperature();

  if (isnan(humedad) || isnan(temperatura)) {
    valid_ = false;
    errorCount_++;
    Serial.println("[DHT22] Lectura invalida");
    return;
  }

  temperature_ = temperatura;
  humidity_    = humedad;
  valid_       = true;

  Serial.printf("[DHT22] T=%.2f C  H=%.2f %%\n", temperature_, humidity_);
}
