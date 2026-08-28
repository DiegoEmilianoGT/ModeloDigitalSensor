//
// RED AISLADA PARA SENSOR ESP32-C3 super mini + BME280
//    NO INTER / NO ROUTER / NO GUARDA
//

#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>

//PINES DE BME280
#define PIN_SDA 8
#define PIN_SCL 9


//LEER EL SENSOR CADA 5 SEGUNDOS
#define INTERVALO_LECTURA 5000UL

//NOMBRE DE LA RED QUE SE CREARA
const char* NOMBRE_RED = "RED_BME280_AISLADA";
const char* CLAVE_RED = "SUPERBME280";

IPAddress ipLocal(192,168,4,1);
IPAddress gateway(192,168,4,1);
IPAddress mascara(255,255,255,255);

Adafruit_BME280 bme280;
WebServer servidor(80);



//VARIABLES DE LAS MEDICIONES 
float temperatura = NAN;
float humedad = NAN;
float presion = NAN;

bool sensorEncontrado = false;
bool lecturaValida = false;

uint8_t direccionSensor = 0;
unsigned long ultimaLectura = 0;
unsigned long lecturasCorrectas = 0;
unsigned long lecturasFallidas = 0;



//BME_280
bool iniciarBME280(){

  Wire.begin(PIN_SDA,PIN_SCL);

  Serial.println("[BME_280]Buscando sensor....");
  if (bme280.begin(0x76, &Wire)) {
    direccionSensor = 0x76;
    return true;
  }

  return false;

}



// Leer temperatura, humedad y presión
void leerBME280(bool forzarLectura = false) {

  unsigned long tiempoActual = millis();

  if (
    !forzarLectura &&
    tiempoActual - ultimaLectura < INTERVALO_LECTURA
  ) {
    return;
  }

  ultimaLectura = tiempoActual;

  if (!sensorEncontrado) {
    lecturaValida = false;
    return;
  }

  float nuevaTemperatura = bme280.readTemperature();
  float nuevaHumedad = bme280.readHumidity();
  float nuevaPresion = bme280.readPressure() / 100.0F;

  if (
    isnan(nuevaTemperatura) ||
    isnan(nuevaHumedad) ||
    isnan(nuevaPresion)
  ) {
    lecturaValida = false;
    lecturasFallidas++;

    Serial.println("[BME280] Error de lectura");
    return;
  }

  temperatura = nuevaTemperatura;
  humedad = nuevaHumedad;
  presion = nuevaPresion;

  lecturaValida = true;
  lecturasCorrectas++;

  Serial.println("----------------------------------");
  Serial.printf("Temperatura: %.2f C\n", temperatura);
  Serial.printf("Humedad: %.2f %%\n", humedad);
  Serial.printf("Presion: %.2f hPa\n", presion);
  Serial.printf(
    "Dispositivos conectados: %d\n",
    WiFi.softAPgetStationNum()
  );
}


// ------------------------------------------------------------
// Página web principal
// ------------------------------------------------------------

void mostrarPaginaPrincipal() {

  leerBME280();

  String pagina = R"rawliteral(
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
  >

  <meta http-equiv="refresh" content="3">

  <title>Prueba local BME280</title>

  <style>
    body {
      margin: 0;
      background: #0d1726;
      color: #ffffff;
      font-family: Arial, sans-serif;
    }

    main {
      max-width: 850px;
      margin: 40px auto;
      padding: 20px;
    }

    h1 {
      margin-bottom: 5px;
    }

    .subtitulo {
      color: #a9bbd1;
    }

    .contenedor {
      display: grid;
      grid-template-columns:
        repeat(auto-fit, minmax(200px, 1fr));
      gap: 18px;
      margin-top: 30px;
    }

    .tarjeta {
      background: #182940;
      border: 1px solid #294361;
      border-radius: 14px;
      padding: 25px;
    }

    .nombre {
      display: block;
      color: #a9bbd1;
      margin-bottom: 12px;
    }

    .valor {
      font-size: 1.8rem;
    }

    .correcto {
      margin-top: 25px;
      padding: 14px;
      background: #176446;
      border-radius: 10px;
    }

    .error {
      margin-top: 25px;
      padding: 14px;
      background: #7c2930;
      border-radius: 10px;
    }

    footer {
      margin-top: 30px;
      color: #a9bbd1;
    }
  </style>
</head>

<body>
  <main>
    <h1>Prueba local del BME280</h1>

    <p class="subtitulo">
      Red completamente aislada y sin Internet
    </p>
)rawliteral";

  if (lecturaValida) {

    pagina += "<div class='contenedor'>";

    pagina += "<div class='tarjeta'>";
    pagina += "<span class='nombre'>Temperatura</span>";
    pagina += "<strong class='valor'>";
    pagina += String(temperatura, 2);
    pagina += " &deg;C</strong>";
    pagina += "</div>";

    pagina += "<div class='tarjeta'>";
    pagina += "<span class='nombre'>Humedad</span>";
    pagina += "<strong class='valor'>";
    pagina += String(humedad, 2);
    pagina += " %</strong>";
    pagina += "</div>";

    pagina += "<div class='tarjeta'>";
    pagina += "<span class='nombre'>Presi&oacute;n</span>";
    pagina += "<strong class='valor'>";
    pagina += String(presion, 2);
    pagina += " hPa</strong>";
    pagina += "</div>";

    pagina += "</div>";

    pagina +=
      "<p class='correcto'>"
      "Sensor funcionando correctamente."
      "</p>";

  } else {

    pagina +=
      "<p class='error'>"
      "No se pudo obtener una lectura. "
      "Revisa la conexión del BME280."
      "</p>";
  }

  pagina += "<footer>";
  pagina += "Direcci&oacute;n local: 192.168.4.1";
  pagina += "<br>";
  pagina += "Lecturas correctas: ";
  pagina += String(lecturasCorrectas);
  pagina += "<br>";
  pagina += "Lecturas fallidas: ";
  pagina += String(lecturasFallidas);
  pagina += "<br>";
  pagina += "Dispositivos conectados: ";
  pagina += String(WiFi.softAPgetStationNum());
  pagina += "</footer>";

  pagina += "</main></body></html>";

  servidor.send(
    200,
    "text/html; charset=utf-8",
    pagina
  );
}

// ------------------------------------------------------------
// Página de diagnóstico
// ------------------------------------------------------------

void mostrarDiagnostico() {

  String respuesta = "{";

  respuesta += "\"sensor_encontrado\":";
  respuesta += sensorEncontrado ? "true" : "false";

  respuesta += ",\"lectura_valida\":";
  respuesta += lecturaValida ? "true" : "false";

  respuesta += ",\"direccion_i2c\":\"0x";

  if (direccionSensor < 16) {
    respuesta += "0";
  }

  respuesta += String(direccionSensor, HEX);
  respuesta += "\"";

  respuesta += ",\"lecturas_correctas\":";
  respuesta += String(lecturasCorrectas);

  respuesta += ",\"lecturas_fallidas\":";
  respuesta += String(lecturasFallidas);

  respuesta += "}";

  servidor.send(
    sensorEncontrado ? 200 : 503,
    "application/json; charset=utf-8",
    respuesta
  );
}

// ------------------------------------------------------------
// Crear la red Wi-Fi aislada
// ------------------------------------------------------------

void crearRedAislada() {

  // Solo modo Access Point.
  // El ESP32 nunca intenta conectarse a otra red.
  WiFi.mode(WIFI_AP);

  // Configurar dirección IP local
  bool ipConfigurada = WiFi.softAPConfig(
    ipLocal,
    gateway,
    mascara
  );

  if (!ipConfigurada) {
    Serial.println(
      "[WiFi] No se pudo configurar la IP"
    );
  }

  /*
   * Parámetros:
   * 1. Nombre de red
   * 2. Contraseña
   * 3. Canal Wi-Fi
   * 4. Red oculta
   * 5. Máximo de dispositivos conectados
   */
  bool redCreada = WiFi.softAP(
    NOMBRE_RED,
    CLAVE_RED,
    6,
    false,
    3
  );

  if (!redCreada) {
    Serial.println(
      "[WiFi] No se pudo crear la red"
    );

    delay(2000);
    ESP.restart();
  }

  Serial.println();
  Serial.println("==================================");
  Serial.println("RED LOCAL CREADA");
  Serial.println("==================================");

  Serial.print("Nombre: ");
  Serial.println(NOMBRE_RED);

  Serial.print("IP local: ");
  Serial.println(WiFi.softAPIP());

  Serial.println("Internet: NO");
  Serial.println("Almacenamiento: NO");
}

// ------------------------------------------------------------
// Configurar servidor web local
// ------------------------------------------------------------

void configurarServidor() {

  servidor.on(
    "/",
    HTTP_GET,
    mostrarPaginaPrincipal
  );

  servidor.on(
    "/diagnostico",
    HTTP_GET,
    mostrarDiagnostico
  );

  servidor.onNotFound([]() {
    servidor.send(
      404,
      "text/plain",
      "Ruta no encontrada"
    );
  });

  servidor.begin();

  Serial.println(
    "[HTTP] Página disponible en:"
  );

  Serial.println(
    "http://192.168.4.1"
  );
}

// ------------------------------------------------------------
// Configuración inicial
// ------------------------------------------------------------

void setup() {

  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("INICIANDO PRUEBA DEL BME280");

  sensorEncontrado = iniciarBME280();

  if (sensorEncontrado) {

    Serial.printf(
      "[BME280] Sensor encontrado en 0x%02X\n",
      direccionSensor
    );

    leerBME280(true);

  } else {

    Serial.println(
      "[BME280] Sensor no encontrado"
    );

    Serial.println(
      "[BME280] Se probaron 0x76 y 0x77"
    );
  }

  crearRedAislada();
  configurarServidor();
}

// ------------------------------------------------------------
// Ciclo principal
// ------------------------------------------------------------

void loop() {

  leerBME280();

  servidor.handleClient();

  delay(2);
}









