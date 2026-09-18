#pragma once

#include <DHT.h>
#include <cstdint>

class DHT22Sensor {
public:
  explicit DHT22Sensor(uint8_t pin);

  void begin();
  void update();

  bool isValid() const { return valid_; }
  uint32_t errorCount() const { return errorCount_; }

  float temperature() const { return temperature_; }
  float humidity() const { return humidity_; }

private:
  DHT dht_;

  bool valid_ = false;
  uint32_t errorCount_ = 0;

  float temperature_ = NAN;
  float humidity_ = NAN;

  unsigned long lastReadMs_ = 0;
};
