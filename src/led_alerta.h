#pragma once

#include <Arduino.h>

void iniciarLed();
void actualizarLed();
// estado: "1" enciende, "0" apaga; devuelve false si no es ninguno de los dos
bool ordenarLed(const String& estado);
String jsonLed();
