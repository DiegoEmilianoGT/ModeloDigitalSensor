#include "servidor_http.h"

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <time.h>

#include "buffer_local.h"
#include "config.h"
#include "led_alerta.h"
#include "pagina.h"
#include "salud.h"
#include "sensores.h"

static WebServer server(80);

static void agregarMetrica(String& out, const char* nombre, const char* ayuda, float valor, const char* tipo = "gauge") {
  out += F("# HELP ");
  out += nombre;
  out += ' ';
  out += ayuda;
  out += F("\n# TYPE ");
  out += nombre;
  out += ' ';
  out += tipo;
  out += '\n';
  out += nombre;
  out += F("{location=\"");
  out += NODO_ID;
  out += F("\"} ");
  out += String(valor, 2);
  out += '\n';
}

static void handleRoot() {
  server.send_P(200, "text/html; charset=utf-8", PAGINA_HTML);
}

static void handleData() {
  server.sendHeader("Access-Control-Allow-Origin", "*");

  // descubrir_nodos.sh busca "node_id":"..." tal cual, sin espacios
  String json = "{\"node_id\":\"" + String(NODO_ID) + "\"";
  json.reserve(512);
  json += ",\"rssi\":" + String(WiFi.RSSI());

#if defined(SENSOR_BME280)
  json += ",\"bme280\":{\"valido\":";
  json += bme.isValid() ? "true" : "false";
  if (bme.isValid()) {
    json += ",\"temperatura\":" + String(bme.temperature(), 2);
    json += ",\"humedad\":" + String(bme.humidity(), 2);
    json += ",\"presion\":" + String(bme.pressureHpa(), 2);
  }
  json += "}";
#endif

#if defined(SENSOR_DHT22)
  json += ",\"dht22\":{\"valido\":";
  json += dht22.isValid() ? "true" : "false";
  if (dht22.isValid()) {
    json += ",\"temperatura\":" + String(dht22.temperature(), 2);
    json += ",\"humedad\":" + String(dht22.humidity(), 2);
  }
  json += "}";
#endif

  json += ",\"ip\":\"" + WiFi.localIP().toString() + "\"";
  json += ",\"uptime_s\":" + String(segundosEncendido());
  json += ",\"heap_libre\":" + String(ESP.getFreeHeap());
  json += ",\"hora\":" + String(horaValida() ? (unsigned long)time(nullptr) : 0UL);
  json += ",\"reinicio\":\"" + String(motivoReinicio()) + "\"";
  json += ",\"led\":" + jsonLed();
  json += ",\"buffer\":{\"usado\":" + String((unsigned long)bufferUsado());
  json += ",\"total\":" + String((unsigned long)bufferTotal()) + "}";

  json += "}";
  server.send(200, "application/json", json);
}

static void handleMetrics() {
  String out;
  out.reserve(1600);

  agregarMetrica(out, "nodo_uptime_segundos",
    "Segundos desde el ultimo arranque del nodo.", segundosEncendido());
  agregarMetrica(out, "nodo_heap_libre_bytes", "Memoria heap libre del nodo.", ESP.getFreeHeap());

#if defined(SENSOR_BME280)
  agregarMetrica(out, "bme280_sensor_up",
    "Si el BME280 entrega lecturas validas (1) o no (0).", bme.isValid() ? 1 : 0);
  if (bme.isValid()) {
    agregarMetrica(out, "bme280_temperatura_celsius", "Temperatura medida por el BME280.", bme.temperature());
    agregarMetrica(out, "bme280_humedad_porcentaje", "Humedad relativa medida por el BME280.", bme.humidity());
    agregarMetrica(out, "bme280_presion_hpa", "Presion atmosferica medida por el BME280.", bme.pressureHpa());
  }
  agregarMetrica(out, "bme280_wifi_rssi_dbm", "Intensidad de la senal WiFi del nodo.", WiFi.RSSI());
  agregarMetrica(out, "bme280_errores_total",
    "Lecturas invalidas del BME280 acumuladas desde que arranco el nodo.", bme.errorCount(), "counter");
#endif

#if defined(SENSOR_DHT22)
  agregarMetrica(out, "dht22_sensor_up",
    "Si el DHT22 entrega lecturas validas (1) o no (0).", dht22.isValid() ? 1 : 0);
  if (dht22.isValid()) {
    agregarMetrica(out, "dht22_temperatura_celsius", "Temperatura medida por el DHT22.", dht22.temperature());
    agregarMetrica(out, "dht22_humedad_porcentaje", "Humedad relativa medida por el DHT22.", dht22.humidity());
  }
  agregarMetrica(out, "dht22_wifi_rssi_dbm", "Intensidad de la senal WiFi del nodo.", WiFi.RSSI());
  agregarMetrica(out, "dht22_errores_total",
    "Lecturas invalidas del DHT22 acumuladas desde que arranco el nodo.", dht22.errorCount(), "counter");
#endif

  server.send(200, "text/plain; version=0.0.4; charset=utf-8", out);
}

static void handleBuffer(){
  server.sendHeader("Access-Control-Allow-Origin", "*");
  const unsigned long desde = strtoul(server.arg("desde").c_str(), nullptr, 10);

  server.setContentLength(CONTENT_LENGTH_UNKNOWN);
  server.send(200, "text/csv", "");
  recorrerBufferDesde(desde, [](const String& bloque) { server.sendContent(bloque); });
  server.sendContent("");
}

static void handleLedEstado(){
  server.send(200, "application/json", jsonLed());
}

static void handleLedCambiar(){
  if (!ordenarLed(server.arg("estado"))){
    server.send(400, "text/plain", "Parametro 'estado' invalido");
    return;
  }
  handleLedEstado();
}

void iniciarServidor() {
  static bool rutasRegistradas = false;
  if (!rutasRegistradas) {  // cada on() reserva memoria: repetirlo en cada reconexion la va agotando
    rutasRegistradas = true;
    server.on("/", handleRoot);
    server.on("/data", handleData);
    server.on("/metrics", handleMetrics);
    server.on("/buffer", handleBuffer);
    server.on("/led", HTTP_GET, handleLedEstado);
    server.on("/led", HTTP_POST, handleLedCambiar);
    server.onNotFound([]() {
      server.send(404, "text/plain", "Ruta no encontrada\n");
    });
  }
  server.stop();
  server.begin();
  Serial.println("[HTTP] Pagina: http://" + WiFi.localIP().toString() + "/");
  Serial.println("[HTTP] Metricas: http://" + WiFi.localIP().toString() + "/metrics");
}

void atenderClientes() {
  server.handleClient();
}
