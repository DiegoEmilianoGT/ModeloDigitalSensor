#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include "config.h"
#include "secrets.h"
#if defined(SENSOR_BME280)
#include "sensors/BME280Sensor.h"
BME280Sensor bme;
#endif
#if defined(SENSOR_DHT22)
#include "sensors/DHT22Sensor.h"
DHT22Sensor dht22(PIN_DHT22);
#endif

WebServer server(80);

bool servidorActivo     = false;
#if defined(SENSOR_BME280)
bool estadoAlerta       = true;
#endif
bool redLista           = false;
unsigned long ultimoAvisoIP = 0;

#define AVISO_IP_INTERVALO_MS 30000UL

void iniciarServidor();

void agregarMetrica(String& out, const char* nombre, const char* ayuda, float valor) {
  out += F("# HELP ");
  out += nombre;
  out += ' ';
  out += ayuda;
  out += F("\n# TYPE ");
  out += nombre;
  out += F(" gauge\n");
  out += nombre;
  out += F("{location=\"");
  out += NODO_ID;
  out += F("\"} ");
  out += String(valor, 2);
  out += '\n';
}

#if defined(SENSOR_BME280)
void verificarAlertas() {
  if (!bme.isValid()) {
    estadoAlerta = true;
    return;
  }
  estadoAlerta =
    bme.temperature() > ALERTA_TEMP_MAX || bme.temperature() < ALERTA_TEMP_MIN ||
    bme.humidity()    > ALERTA_HUM_MAX  || bme.humidity()    < ALERTA_HUM_MIN  ||
    bme.pressureHpa() > ALERTA_PRESION_MAX || bme.pressureHpa() < ALERTA_PRESION_MIN;
}
#endif

void handleRoot() {
  String html;
  html.reserve(1800);
  html += F("<!doctype html><html><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='refresh' content='5'>"
            "<title>");
  html += NODO_ID;
  html += F("</title></head><body style='font-family:Arial;text-align:center;"
            "max-width:620px;margin:30px auto'>"
            "<h2>ESP32-C3 SuperMini</h2><p>Nodo: <b>");
  html += NODO_ID;
  html += F("</b></p>");

#if defined(SENSOR_BME280)
  if (bme.isValid()) {
    html += F("<p style='font-size:1.3em'>BME280 &mdash; Temp: <b>");
    html += String(bme.temperature(), 2);
    html += F(" &deg;C</b> | Hum: <b>");
    html += String(bme.humidity(), 2);
    html += F(" %</b> | Presion: <b>");
    html += String(bme.pressureHpa(), 2);
    html += F(" hPa</b></p>");
  } else {
    html += F("<p>BME280 sin lectura valida.</p>");
  }
#endif

#if defined(SENSOR_DHT22)
  if (dht22.isValid()) {
    html += F("<p style='font-size:1.3em'>DHT22 &mdash; Temp: <b>");
    html += String(dht22.temperature(), 2);
    html += F(" &deg;C</b> | Hum: <b>");
    html += String(dht22.humidity(), 2);
    html += F(" %</b></p>");
  } else {
    html += F("<p>DHT22 sin lectura valida.</p>");
  }
#endif


  html += F("<p>IP: ");
  html += WiFi.localIP().toString();
  html += F(" | RSSI: ");
  html += String(WiFi.RSSI());
  html += F(" dBm</p>");

#if defined(SENSOR_BME280)
  html += F("<p style='font-size:1.2em;background:");
  html += estadoAlerta ? "#e74c3c" : "#27ae60";
  html += F(";color:white;padding:10px;border-radius:6px'><b>");
  html += !bme.isValid() ? "SENSOR SIN LECTURA" : (estadoAlerta ? "ALERTA" : "Normal");
  html += F("</b></p>");
#endif

  html += F("<p><a href='/metrics'>Metricas Prometheus</a></p>");

  html += F("</body></html>");

  server.send(200, "text/html; charset=utf-8", html);
}

void handleData() {
  server.sendHeader("Access-Control-Allow-Origin", "*");

  String json = "{\"node_id\":\"" + String(NODO_ID) + "\"";
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


  json += "}";
  server.send(200, "application/json", json);
}

void handleMetrics() {
  String out;
  out.reserve(1200);

#if defined(SENSOR_BME280)
  agregarMetrica(out, "bme280_sensor_up",
    "Si el BME280 entrega lecturas validas (1) o no (0).", bme.isValid() ? 1 : 0);
  if (bme.isValid()) {
    agregarMetrica(out, "bme280_temperatura_celsius", "Temperatura medida por el BME280.", bme.temperature());
    agregarMetrica(out, "bme280_humedad_porcentaje", "Humedad relativa medida por el BME280.", bme.humidity());
    agregarMetrica(out, "bme280_presion_hpa", "Presion atmosferica medida por el BME280.", bme.pressureHpa());
  }
  agregarMetrica(out, "bme280_alert_active",
    "Si alguna lectura del BME280 esta fuera de los umbrales configurados.", estadoAlerta ? 1 : 0);
  agregarMetrica(out, "bme280_wifi_rssi_dbm", "Intensidad de la senal WiFi del nodo.", WiFi.RSSI());
  agregarMetrica(out, "bme280_errores_total",
    "Lecturas invalidas del BME280 acumuladas desde que arranco el nodo.", bme.errorCount());
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
    "Lecturas invalidas del DHT22 acumuladas desde que arranco el nodo.", dht22.errorCount());
#endif


  server.send(200, "text/plain; version=0.0.4; charset=utf-8", out);
}

void iniciarServidor() {
  server.stop();
  server.on("/", handleRoot);
  server.on("/data", handleData);
  server.on("/metrics", handleMetrics);
  server.onNotFound([]() {
    server.send(404, "text/plain", "Ruta no encontrada\n");
  });
  server.begin();
  servidorActivo = true;
  Serial.println("[HTTP] Pagina: http://" + WiFi.localIP().toString() + "/");
  Serial.println("[HTTP] Metricas: http://" + WiFi.localIP().toString() + "/metrics");
}

void alConectar() {
  redLista = true;

  Serial.println("[WiFi] IP: " + WiFi.localIP().toString());
  Serial.println("[WiFi] MAC: " + WiFi.macAddress());
  Serial.printf("[WiFi] RSSI: %d dBm\n", WiFi.RSSI());
  Serial.println("[Prometheus] Target: " + WiFi.localIP().toString() + ":80/metrics");
  iniciarServidor();
}

void avisarIPPeriodico() {
  const unsigned long ahora = millis();
  if (ultimoAvisoIP != 0 && ahora - ultimoAvisoIP < AVISO_IP_INTERVALO_MS) return;
  ultimoAvisoIP = ahora;
  Serial.println("[Prometheus] " + String(NODO_ID) + " -> " +
                  WiFi.localIP().toString() + ":80/metrics");
}

// Reinicia el nodo si el heap libre cae demasiado, antes de arriesgar un crash.
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

// Diagnostico: lista las redes 2.4GHz visibles y si WIFI_SSID esta entre ellas.
void escanearRedes() {
  Serial.println("[WiFi] Escaneando redes visibles...");
  int n = WiFi.scanNetworks();
  if (n == WIFI_SCAN_FAILED) {
    Serial.println("[WiFi] El escaneo no pudo iniciar (radio ocupado).");
  } else if (n <= 0) {
    Serial.println("[WiFi] No se detecto ninguna red 2.4GHz cerca.");
  } else {
    for (int i = 0; i < n; i++) {
      const bool esLaNuestra = WiFi.SSID(i) == WIFI_SSID;
      Serial.printf("  %2d) %-32s RSSI=%4d dBm canal=%2d%s\n",
                    i + 1, WiFi.SSID(i).c_str(), WiFi.RSSI(i), WiFi.channel(i),
                    esLaNuestra ? "  <-- esta es la nuestra" : "");
    }
  }
  WiFi.scanDelete();
}

// Bloqueante a proposito: si no conecta en WIFI_TIMEOUT_MS, reinicia el nodo.
void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  redLista = false;
  Serial.println("[WiFi] Conectando...");
  WiFi.disconnect();
  delay(1000);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  // Debe ir despues de begin(), no antes -- ver README (defecto de antena SuperMini).
  WiFi.setTxPower(WIFI_POWER_8_5dBm);

  const unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - inicio > WIFI_TIMEOUT_MS) {
      Serial.println("[WiFi] Timeout.");
      escanearRedes();
      Serial.println("[WiFi] Reiniciando...");
      delay(500);
      ESP.restart();
    }
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  alConectar();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.printf("=== Nodo %s ===\n", NODO_ID);

#if defined(SENSOR_BME280)
  bme.begin();
#endif
#if defined(SENSOR_DHT22)
  dht22.begin();
#endif

  WiFi.mode(WIFI_STA);
  WiFi.setHostname(NODO_ID);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);

  Serial.println("[WiFi] MAC de este nodo: " + WiFi.macAddress());

  escanearRedes();

  conectarWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    return;
  }

  avisarIPPeriodico();
  vigilarMemoria();

  if (!servidorActivo) iniciarServidor();
  server.handleClient();

#if defined(SENSOR_BME280)
  bme.update();
  verificarAlertas();
#endif
#if defined(SENSOR_DHT22)
  dht22.update();
#endif

  delay(2);
}
