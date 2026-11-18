#include "buffer_local.h"

#include <LittleFS.h>
#include <time.h>
#include <vector>
#include <algorithm>

#include "config.h"
#include "salud.h"
#include "sensores.h"

static size_t usado = 0;
static size_t total = 0;

static void medirBuffer() {
  usado = LittleFS.usedBytes();
  total = LittleFS.totalBytes();
}

size_t bufferUsado() { return usado; }
size_t bufferTotal() { return total; }

static String nombreDelDia(time_t t) {
  struct tm fecha;
  gmtime_r(&t, &fecha);
  char nombre[16];
  strftime(nombre, sizeof(nombre), "%Y%m%d.csv", &fecha);
  return String(nombre);
}

static String rutaDe (const String& nombre){
  return String (BUFFER_DIR) + "/" + nombre;
}

static std::vector<String> archivosDelBuffer(){
  std::vector<String> nombres;
  File dir = LittleFS.open(BUFFER_DIR);
  if (!dir || !dir.isDirectory()) return nombres;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()){
    String nombre = f.name();
    nombres.push_back(nombre.substring(nombre.lastIndexOf('/') + 1));
    f.close();
  }
  std::sort(nombres.begin(), nombres.end());
  return nombres;
}

// Si a la placa le cambian el NODO_ID, lo guardado era de otro nodo: se descarta
// para que el servidor no se lo atribuya al nuevo.
static void reclamarBuffer(){
  String dueno;
  if (LittleFS.exists(BUFFER_DUENO)) {
    File f = LittleFS.open(BUFFER_DUENO, "r");
    if (f) {
      dueno = f.readString();
      f.close();
    }
    dueno.trim();
  }
  if (dueno == NODO_ID) return;

  if (!dueno.isEmpty()) {
    for (const String& nombre : archivosDelBuffer()) LittleFS.remove(rutaDe(nombre));
    Serial.println("[Buffer] Lo guardado era de " + dueno + ": se descarto");
  }
  File f = LittleFS.open(BUFFER_DUENO, "w");
  if (f) {
    f.print(NODO_ID);
    f.close();
  }
}

static void limpiarBuffer(){
  const String limite = nombreDelDia(time(nullptr) - (time_t)BUFFER_DIAS * 86400);
  std::vector<String> nombres = archivosDelBuffer();
  size_t i = 0;
  while(i < nombres.size() && nombres[i] < limite) {
    LittleFS.remove(rutaDe(nombres[i]));
    Serial.println("[Buffer] Borrado por antiguedad: " + nombres[i]);
    i++;
  }
  while (i + 1 < nombres.size() && LittleFS.usedBytes() > LittleFS.totalBytes() * BUFFER_USO_MAXIMO) {
    LittleFS.remove(rutaDe(nombres[i]));
    Serial.println("[Buffer] Memoria casi llena, borrado: " + nombres[i]);
    i++;
  }
}

void iniciarBuffer(){
  if (!LittleFS.begin(true)) {
    Serial.println("[Buffer] No se pudo montar LittleFS");
  }
  if (!LittleFS.exists(BUFFER_DIR)) LittleFS.mkdir(BUFFER_DIR);
  reclamarBuffer();
  medirBuffer();
  Serial.printf("[Buffer] Dias guardados: %u\n", (unsigned)archivosDelBuffer().size());
}

void guardarEnBuffer(){
  static unsigned long ultimoGuardado = 0;
  static String diaActual;
  const unsigned long ahora = millis();
  if (ultimoGuardado != 0 && ahora - ultimoGuardado < BUFFER_INTERVALO_MS) return;
  ultimoGuardado = ahora;

  if(!horaValida()){
    Serial.println("[Buffer] Hora no sincronizada todavia");
    return;
  }

  bool hayDatoValido = false;
  const time_t marca = time(nullptr);
  String linea = String((unsigned long)marca);

  #if defined(SENSOR_BME280)
    if (bme.isValid()){
      linea += "," + String(bme.temperature(), 2) + "," + String(bme.humidity(), 2) + "," + String(bme.pressureHpa(), 2);
      hayDatoValido = true;
    }else {
      linea += ",,,";
    }
  #endif
  #if defined(SENSOR_DHT22)
    if (dht22.isValid()) {
      linea += "," + String(dht22.temperature(), 2) + "," + String(dht22.humidity(), 2);
      hayDatoValido = true;
    } else {
      linea += ",,";
    }
  #endif

    if (!hayDatoValido) return;

    const String nombre = nombreDelDia(marca);
    if (nombre != diaActual) {  // primera lectura del dia: buen momento para limpiar
      diaActual = nombre;
      limpiarBuffer();
    }

    File f = LittleFS.open(rutaDe(nombre), "a");
    if (!f){
      Serial.println("[Buffer] No se pudo abrir el archivo");
      return;
    }
    f.println(linea);
    f.close();
    medirBuffer();
    Serial.println("[Buffer] Lectura guardada en " + nombre);
}

void recorrerBufferDesde(unsigned long desde, const std::function<void(const String&)>& enviar){
  const String primerDia = nombreDelDia((time_t)desde);
  String bloque;
  bloque.reserve(1100);
  for(const String& nombre : archivosDelBuffer()){
    if (nombre < primerDia) continue;
    File f = LittleFS.open(rutaDe(nombre), "r");
    while (f && f.available()){
      String linea = f.readStringUntil('\n');
      linea.trim();
      if (linea.isEmpty() || strtoul(linea.c_str(), nullptr, 10) <= desde) continue;
      bloque += linea;
      bloque += '\n';
      if(bloque.length() >= 1024){
        enviar(bloque);
        bloque = "";
      }
    }
    f.close();
  }
  if (bloque.length() > 0) enviar(bloque);
}
