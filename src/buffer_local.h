#pragma once

#include <Arduino.h>
#include <functional>

// Lecturas guardadas en LittleFS, un CSV por dia, para recuperar lo que Prometheus no alcanzo a leer
void iniciarBuffer();
void guardarEnBuffer();
// entrega en bloques de ~1 KB las lineas con marca posterior a desde
void recorrerBufferDesde(unsigned long desde, const std::function<void(const String&)>& enviar);
size_t bufferUsado();
size_t bufferTotal();
