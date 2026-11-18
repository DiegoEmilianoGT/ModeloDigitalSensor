#include "red.h"

#include <Arduino.h>
#include <WiFi.h>
#include <time.h>

#include "config.h"
#include "secrets.h"

// la conexion avanza por fases para no detener el loop mientras no hay WiFi
enum class EstadoWiFi : uint8_t { Reposo, Desconectando, Conectando };

static EstadoWiFi estadoWiFi   = EstadoWiFi::Reposo;
static bool redLista           = false;
static unsigned long ultimoAvisoIP = 0;
static unsigned long ultimoIntentoWiFi  = 0;
static unsigned long inicioFaseWiFi     = 0;
static unsigned long inicioDesconexion  = 0;

static void escanearRedes() {
  Serial.println("[WiFi] Redes visibles...");
  int n = WiFi.scanNetworks();
  if (n == WIFI_SCAN_FAILED) {
    Serial.println("[WiFi] El escaneo no pudo iniciar.");
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

static void alConectar() {
  redLista = true;
  inicioDesconexion = 0;
  estadoWiFi = EstadoWiFi::Reposo;

  Serial.println("[WiFi] IP: " + WiFi.localIP().toString());
  Serial.println("[WiFi] MAC: " + WiFi.macAddress());
  Serial.printf("[WiFi] RSSI: %d dBm\n", WiFi.RSSI());
  Serial.println("[Prometheus] Target: " + WiFi.localIP().toString() + ":80/metrics");

  configTime(0, 0, NTP_SERVIDOR_1, NTP_SERVIDOR_2);  // fechar el buffer
}

void iniciarRed() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(NODO_ID);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);

  Serial.println("[WiFi] MAC de este nodo: " + WiFi.macAddress());

  escanearRedes();
}

bool redConectada() {
  return WiFi.status() == WL_CONNECTED;
}

void avisarIPPeriodico() {
  const unsigned long ahora = millis();
  if (ultimoAvisoIP != 0 && ahora - ultimoAvisoIP < AVISO_IP_INTERVALO_MS) return;
  ultimoAvisoIP = ahora;
  Serial.println("[Prometheus] " + String(NODO_ID) + " -> " +
                  WiFi.localIP().toString() + ":80/metrics");
}

bool gestionarWiFi() {
  const unsigned long ahora = millis();

  if (WiFi.status() == WL_CONNECTED) {
    if (redLista) return false;
    alConectar();  // tambien cuando reconecta solo, fuera de un intento
    return true;
  }

  if (redLista) {
    redLista = false;
    Serial.println("[WiFi] Se perdio la conexion");
  }
  if (inicioDesconexion == 0) inicioDesconexion = ahora;

  switch (estadoWiFi) {
    case EstadoWiFi::Reposo:
      if (ultimoIntentoWiFi != 0 && ahora - ultimoIntentoWiFi < WIFI_REINTENTO_MS) return false;
      ultimoIntentoWiFi = ahora;
      Serial.println("[WiFi] Conectando...");
      WiFi.disconnect();
      estadoWiFi = EstadoWiFi::Desconectando;
      inicioFaseWiFi = ahora;
      return false;

    case EstadoWiFi::Desconectando:
      if (ahora - inicioFaseWiFi < WIFI_PAUSA_MS) return false;
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      WiFi.setTxPower(WIFI_POWER_8_5dBm);
      estadoWiFi = EstadoWiFi::Conectando;
      inicioFaseWiFi = ahora;
      return false;

    case EstadoWiFi::Conectando:
      if (ahora - inicioFaseWiFi < WIFI_TIMEOUT_MS) return false;
      estadoWiFi = EstadoWiFi::Reposo;
      Serial.println("[WiFi] Timeout en este intento.");
      if (ahora - inicioDesconexion > WIFI_REINICIO_MS) {
        Serial.println("[WiFi] Demasiado tiempo sin conectar.");
        escanearRedes();
        Serial.println("[WiFi] Reiniciando como ultimo recurso...");
        delay(500);
        ESP.restart();
      }
      return false;
  }
  return false;
}
