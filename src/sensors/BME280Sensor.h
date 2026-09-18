#pragma once

#include <Adafruit_BME280.h>
#include <cstdint>

class BME280Sensor {
public:
  bool begin();
  void update();

  bool isValid() const { return valid_; }
  bool isAvailable() const { return available_; }
  uint8_t address() const { return address_; }
  uint32_t errorCount() const { return errorCount_; }

  float temperature() const { return temperature_; }
  float humidity() const { return humidity_; }
  float pressureHpa() const { return pressureHpa_; }

private:
  Adafruit_BME280 bme_;

  bool available_ = false;
  bool valid_ = false;
  uint8_t address_ = 0;
  uint8_t consecutiveErrors_ = 0;
  uint32_t errorCount_ = 0;

  float temperature_ = NAN;
  float humidity_ = NAN;
  float pressureHpa_ = NAN;

  unsigned long lastReadMs_ = 0;
  unsigned long lastRetryMs_ = 0;
};
