#include "salud.h"

#include <Arduino.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <time.h>

#include "config.h"

bool horaValida() {
  return time(nullptr) > 1700000000;
}

unsigned long segundosEncendido() {
  return (unsigned long)(esp_timer_get_time() / 1000000LL);  // millis() se desborda a los 49 dias
}

const char* motivoReinicio() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:  return "encendido";
    case ESP_RST_SW:       return "software";
    case ESP_RST_PANIC:    return "fallo";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT:      return "watchdog";
    case ESP_RST_BROWNOUT: return "bajo voltaje";
    default:               return "otro";
  }
}

// reinicia el nodo si el heap libre cae demasiado
void vigilarMemoria() {
  static unsigned long ultimoAviso = 0;
  const unsigned long ahora = millis();
  const uint32_t heapLibre = ESP.getFreeHeap();

  if (heapLibre < HEAP_MINIMO_BYTES) {
    Serial.printf("[Memoria] Heap muy bajo (%u bytes). Reiniciando...\n", heapLibre);
    delay(200);
    ESP.restart();
  }

  if (ultimoAviso != 0 && ahora - ultimoAviso < AVISO_IP_INTERVALO_MS) return;
  ultimoAviso = ahora;
  Serial.printf("[Memoria] Heap libre: %u bytes\n", heapLibre);
}
