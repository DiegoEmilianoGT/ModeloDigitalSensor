#include "BME280Sensor.h"
#include "config.h"

#include <Arduino.h>
#include <Wire.h>

bool BME280Sensor::begin() {
  if (!Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL)) {
    Serial.println("[BME280] Wire.begin() fallo (pines I2C invalidos)");
    available_ = false;
    valid_ = false;
    return false;
  }
  Wire.setClock(I2C_FRECUENCIA_HZ);
  Wire.setTimeOut(1000);  // evita que un I2C colgado bloquee el loop()

  if (bme_.begin(0x76, &Wire)) {
    address_ = 0x76;
  } else if (bme_.begin(0x77, &Wire)) {
    address_ = 0x77;
  } else {
    available_ = false;
    valid_ = false;
    address_ = 0;
    Serial.println("[BME280] No se encontro en 0x76 ni en 0x77");
    return false;
  }

  bme_.setSampling(
    Adafruit_BME280::MODE_NORMAL,
    Adafruit_BME280::SAMPLING_X2,
    Adafruit_BME280::SAMPLING_X16,
    Adafruit_BME280::SAMPLING_X1,
    Adafruit_BME280::FILTER_X16,
    Adafruit_BME280::STANDBY_MS_500
  );

  available_ = true;
  consecutiveErrors_ = 0;
  lastReadMs_ = millis() - LECTURA_INTERVALO_MS;  // fuerza la primera lectura
  Serial.printf("[BME280] Detectado en 0x%02X\n", address_);
  return true;
}

void BME280Sensor::update() {
  const unsigned long ahora = millis();

  if (!available_) {
    if (ahora - lastRetryMs_ >= REINTENTO_BME_MS) {
      lastRetryMs_ = ahora;
      begin();
    }
    return;
  }

  if (ahora - lastReadMs_ < LECTURA_INTERVALO_MS) return;
  lastReadMs_ = ahora;

  const float temperatura = bme_.readTemperature();
  const float humedad     = bme_.readHumidity();
  const float presionHpa  = bme_.readPressure() / 100.0f;

  const bool datosCoherentes =
    !isnan(temperatura) && !isnan(humedad) && !isnan(presionHpa) &&
    temperatura >= BME_TEMP_MIN    && temperatura <= BME_TEMP_MAX &&
    humedad     >= 0.0f            && humedad     <= 100.0f &&
    presionHpa  >= BME_PRESION_MIN && presionHpa  <= BME_PRESION_MAX;

  if (!datosCoherentes) {
    valid_ = false;
    errorCount_++;
    Serial.println("[BME280] Lectura invalida");

    if (++consecutiveErrors_ >= ERRORES_PARA_REINICIAR_BME) {
      Serial.println("[BME280] Demasiados errores, reiniciando el sensor");
      available_   = false;
      lastRetryMs_ = ahora;
    }
    return;
  }

  consecutiveErrors_ = 0;
  temperature_        = temperatura;
  humidity_            = humedad;
  pressureHpa_         = presionHpa;
  valid_               = true;

  Serial.printf("[BME280] T=%.2f C  H=%.2f %%  P=%.2f hPa\n",
                temperature_, humidity_, pressureHpa_);
}
