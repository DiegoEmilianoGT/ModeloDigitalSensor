#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>

#define SDA_PIN 8
#define SCL_PIN 9

Adafruit_BME280 bme;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Wire.begin(SDA_PIN, SCL_PIN);
  if (!bme.begin(0x76)) {

    // Si no responde, intenta en 0x77
    if (!bme.begin(0x77)) {
      Serial.println("ERROR");
      Serial.println("VIN -> 3.3V");
      Serial.println("GND -> GND");
      Serial.println("SDA -> GPIO8");
      Serial.println("SCL -> GPIO9");
      while (true) {
        delay(1000);
      }
    }
  }
}

void loop() {

  float temperatura = bme.readTemperature();
  float humedad = bme.readHumidity();
  float presion = bme.readPressure() / 100.0F;


  Serial.print("Temperatura: ");
  Serial.print(temperatura, 2);
  Serial.println(" °C");

  Serial.print("Humedad: ");
  Serial.print(humedad, 2);
  Serial.println(" %");

  Serial.print("Presion: ");
  Serial.print(presion, 2);
  Serial.println(" hPa");


  delay(5000);
}


