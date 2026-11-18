#include <Arduino.h>

#include "buffer_local.h"
#include "config.h"
#include "led_alerta.h"
#include "red.h"
#include "salud.h"
#include "sensores.h"
#include "servidor_http.h"

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.printf("=== Nodo %s ===\n", NODO_ID);

  iniciarLed();
  iniciarBuffer();
  iniciarSensores();
  iniciarRed();
  if (gestionarWiFi()) iniciarServidor();
}

void loop() {
  if (gestionarWiFi()) iniciarServidor();
  guardarEnBuffer();
  actualizarLed();
  vigilarMemoria();
  actualizarSensores();

  if (redConectada()) {
    avisarIPPeriodico();
    atenderClientes();
  }

  delay(2);
}
