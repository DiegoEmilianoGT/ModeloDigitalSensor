#include "led_alerta.h"

#include "config.h"

static bool alertaLed = false;
static unsigned long ultimaOrdenLed = 0;

static bool ledSinNoticias(){
  return millis() - ultimaOrdenLed > LED_SIN_NOTICIAS_MS;
}

void iniciarLed(){
  pinMode(PIN_LED_ALERTA,OUTPUT);
  digitalWrite(PIN_LED_ALERTA,LOW);
  ultimaOrdenLed = millis();
}

void actualizarLed(){
  bool encendido = alertaLed;

  if (ledSinNoticias()) {
    encendido = (millis() / LED_PARPADEO_MS) % 2 == 0;
  }

  digitalWrite(PIN_LED_ALERTA, encendido ? HIGH : LOW);
}

bool ordenarLed(const String& estado){
  if (estado != "0" && estado != "1") return false;
  alertaLed = estado == "1";
  ultimaOrdenLed = millis();
  return true;
}

String jsonLed(){
  String json = "{\"alerta\":";
  json += alertaLed ? "true" : "false";
  json += ",\"sin_noticias\":";
  json += ledSinNoticias() ? "true" : "false";
  json += "}";
  return json;
}
