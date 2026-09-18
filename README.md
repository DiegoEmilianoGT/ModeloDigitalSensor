# Monitor ambiental BME280 + DHT22 + ESP32-C3 SuperMini

Proyecto para Visual Studio Code con PlatformIO. Dos ESP32-C3 SuperMini, uno
con un BME280 (I2C) y otro con un DHT22, cada uno se conecta a tu red Wi-Fi
de 2.4 GHz y publica una página web con su lectura.

> Grafana no se está usando por ahora. Prometheus sí: ver la sección
> **Prometheus** más abajo.

## Conexiones

| BME280 | ESP32-C3 SuperMini |
| --- | --- |
| VCC/VIN | 3.3 V |
| GND | GND |
| SDA | GPIO 8 |
| SCL | GPIO 9 |

| DHT22 | ESP32-C3 SuperMini |
| --- | --- |
| VCC | 3.3 V |
| GND | GND |
| DATA | GPIO 4 |

El DHT22 pelado (sin PCB) necesita una resistencia externa de 4.7k–10kΩ entre
DATA y VCC; sin ella la lectura siempre falla. El BME280 no necesita nada
extra: el programa prueba solo las direcciones I2C `0x76` y `0x77`.

> **Si la placa no arranca o `Upload` falla con el BME280 conectado:** GPIO 8 y
> GPIO 9 también son pines de arranque del ESP32-C3. Cambia `PIN_I2C_SDA` a 5 y
> `PIN_I2C_SCL` a 6 en `include/config.h`, y recablea SDA/SCL a esos pines.

## Dos placas, un firmware

Cada sensor vive en su propio ESP32-C3, así que `platformio.ini` define un
entorno de compilación por placa; cada uno solo incluye el código de su
sensor y le da un `NODO_ID` distinto (mismo nombre en ambos rompe la red: los
dos pelearían por el mismo hostname/SSID).

```bash
pio run -e esp32-c3-bme280 --target upload   # placa con el BME280
pio run -e esp32-c3-dht22  --target upload   # placa con el DHT22
pio device monitor -e esp32-c3-bme280        # monitor serial de esa placa
```

En VS Code: selecciona el entorno correcto abajo, en la barra de PlatformIO
(donde dice el nombre del entorno), antes de darle a **Build**/**Upload**.

Si alguna vez quieres los dos sensores en una sola placa, usa el entorno
`esp32-c3-supermini` (conecta ambos sensores a esa placa como en la tabla de
arriba).

> Si al abrir el proyecto ves los `#include` subrayados en rojo, es normal la
> primera vez: PlatformIO aún no descargó las librerías. Corre **Build** una
> vez y el subrayado desaparece.

## Estructura del código

- `src/main.cpp` — Wi-Fi, servidor HTTP y `setup()`/`loop()`.
- `src/sensors/BME280Sensor.{h,cpp}` — lectura y validación del BME280.
- `src/sensors/DHT22Sensor.{h,cpp}` — lectura y validación del DHT22.
- `include/config.h` — pines, identidad del nodo, intervalos y umbrales.
  `SENSOR_BME280`/`SENSOR_DHT22` y `NODO_ID` llegan desde `platformio.ini`.
- `include/secrets.h` — credenciales Wi-Fi (no se sube a Git, es la misma
  para las dos placas).

## Puesta en marcha

1. Instala Visual Studio Code y la extensión `PlatformIO IDE` (`Ctrl+Shift+X`).
2. Abre esta carpeta con **Archivo > Abrir carpeta** (la carpeta completa).
3. Edita `include/secrets.h`: nombre y contraseña de tu Wi-Fi de 2.4 GHz.
4. Conecta el ESP32-C3 que quieras grabar por USB.
5. Elige su entorno (`esp32-c3-bme280` o `esp32-c3-dht22`) en la barra de
   PlatformIO y pulsa **Build** y después **Upload**.
6. Abre **Serial Monitor** a 115200 baudios para ver la IP asignada.
7. Repite del paso 4 al 6 con la otra placa y el otro entorno.

## Wi-Fi

El nodo se conecta a tu router y queda disponible en la IP que le asigne la
red. La conexión es bloqueante a propósito: si se cae o no logra conectar en
`WIFI_TIMEOUT_MS` (`include/config.h`, 20s por defecto), el nodo se reinicia
de inmediato en vez de seguir reintentando en la misma sesión — un reinicio
completo reinicializa todo el radio WiFi desde cero, cosa que llamar
`WiFi.begin()` repetidas veces sin reiniciar no logra igual de bien.

> **Defecto de fábrica conocido en el primer lote de placas "ESP32-C3
> SuperMini"**: el oscilador de 40MHz quedó demasiado cerca de la antena en
> el diseño de PCB. A la potencia de transmisión por defecto (la que usa
> `WiFi.begin()` si no se toca nada), eso genera reflexiones que impiden
> completar la conexión — aunque **escanear redes sí funciona** (usa mucha
> menos potencia), lo que hace muy confuso el diagnóstico: la placa ve la
> red perfecto pero nunca logra asociarse, con cualquier red, sin importar
> la señal o la contraseña. El workaround (no todas las placas lo necesitan
> igual de agresivo, depende de qué tan mal les tocó el lote) es bajar la
> potencia **justo después** de `WiFi.begin()`, nunca antes:
> ```cpp
> WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
> WiFi.setTxPower(WIFI_POWER_8_5dBm);  // ya esta en conectarWiFi()
> ```
> Si con `WIFI_POWER_8_5dBm` una placa específica sigue sin conectar, prueba
> valores más bajos todavía (`WIFI_POWER_7dBm`, `WIFI_POWER_5dBm`,
> `WIFI_POWER_2dBm`) — el grado del defecto varía de placa a placa. Subir la
> potencia por encima de este valor (o al máximo, `WIFI_POWER_19_5dBm`)
> reintroduce el problema, y además puede causar *brownouts* por el
> regulador de voltaje justo que traen estas placas.

Tanto el Serial Monitor como la página web (`http://IP_DEL_ESP32/`) muestran
el RSSI (intensidad de la señal Wi-Fi, en dBm) además de la IP; valores más
cercanos a 0 son mejor señal (p. ej. -50 dBm es buena, -80 dBm es débil).

## Direcciones disponibles

- `http://IP_DEL_ESP32/` — lectura del sensor de esa placa y estado (para verla
  en el navegador).
- `http://IP_DEL_ESP32/data` — la misma lectura en JSON, para el dashboard.
- `http://IP_DEL_ESP32/metrics` — la misma lectura en formato Prometheus, para
  que Prometheus la scrapee (ver sección **Prometheus**).

## IP y dashboard

Cada placa obtiene su IP por DHCP del router (no hay IP fija configurada). Al
conectarse, el nodo consulta `WiFi.localIP()` y la imprime por el Serial
Monitor y en la propia página web (`http://IP_DEL_ESP32/`), así que revisa ahí
qué IP le asignó la red cada vez que arranque.

Si necesitas que la IP no cambie entre reinicios, resérvala desde el propio
router (DHCP reservation / IP estática por MAC) en vez de configurarla en el
firmware.

`dashboard/index.html` es una página local (no un sitio en internet) que junta
las lecturas de las dos placas en una sola vista, consultando `/data` de cada
una cada 3 segundos. Para usarla:

1. Abre `dashboard/index.html` haciendo doble clic (se abre en tu navegador).
2. Si tus IPs no son las de por defecto, despliega **Configurar direcciones
   IP**, escríbelas y dale a **Guardar** (queda guardado en ese navegador).

Si el navegador bloquea las peticiones por CORS al abrir el archivo así,
sírvelo con un servidor local en vez de abrirlo directo, por ejemplo desde esa
carpeta: `python -m http.server 8000` y entra a `http://localhost:8000/`.

## Prometheus

Cada placa expone sus lecturas en formato Prometheus en `/metrics` (además de
la página web y `/data`). La configuración vive en `prometheus/`:

- `prometheus/prometheus.yml` — a qué targets scrapear y cada cuánto.
- `prometheus/alertas_bme280.yml` — reglas de alerta (nodo caído, sensor sin
  lectura, valores fuera de umbral, señal Wi-Fi débil).

Los intervalos de lectura en firmware (`include/config.h`) son BME280 cada
2 s y DHT22 cada 3 s. Se probó con el mínimo técnico (500 ms / 2 s) y con
señal Wi-Fi débil eso le quitaba tiempo de CPU/loop a la pila WiFi justo
cuando más lo necesitaba (más I2C, más `Serial.printf`, más JSON armado por
segundo); 2 s / 3 s sigue siendo más que suficiente para un monitor
ambiental y deja más aire para la conexión.

El `scrape_interval`/`scrape_timeout` de Prometheus, en cambio, usa el
global de 5 s / 4 s (`prometheus.yml`) y no el mínimo posible — se probó con
1 s / 900 ms y, con la señal Wi-Fi débil que tienen estas placas (~-80 dBm),
un timeout tan ajustado marcaba el nodo como `DOWN` por cualquier
micro-corte aunque siguiera vivo. 5 s da margen real sin dejar de ser
razonablemente rápido (`grafana_dashboard.json` refresca a 5 s a juego). Si
más adelante mejoras la señal (acercando la placa al router, por ejemplo),
ahí sí tiene sentido volver a bajarlo.

### Sin IP fija: descubrimiento automático por escaneo

Como las placas no tienen IP fija (DHCP normal) y Prometheus corre en una red
distinta a la de las placas (esta "red aislada" las separa por routing, y el
descubrimiento por multicast tipo mDNS no cruza esa frontera),
`prometheus.yml` **no tiene IPs escritas a mano**:
usa `file_sd_configs` apuntando a `prometheus/targets/bme280.json` y
`prometheus/targets/dht22.json`. Esos archivos los mantiene actualizados
`prometheus/descubrir_nodos.sh`, que escanea la subred de las placas por
HTTP (eso sí cruza el router, a diferencia del multicast) y identifica cada
una por el `node_id` que reporta en `/data`.

Pasos:

1. Sube el firmware a las dos placas.
2. Corre el script una vez para probarlo (desde `prometheus/`):
   ```bash
   ./descubrir_nodos.sh
   ```
   Debería imprimir algo como `bme280_esp32c3_01 (bme280) -> 10.203.58.170`.
   Si dice "no encontrado", revisa `SUBRED` al inicio del script (el
   prefijo /24 donde están las placas) y que estén conectadas.
3. Déjalo corriendo en bucle en una terminal aparte (o una pestaña de
   `tmux`/`screen`) mientras tengas Prometheus activo:
   ```bash
   ./descubrir_nodos.sh --loop 30
   ```
   Actualiza los targets cada 30s; si a una placa le cambia la IP por DHCP,
   en menos de un minuto Prometheus ya está apuntando a la nueva.
4. Descarga Prometheus (prometheus.io/download) y corre, desde la carpeta
   `prometheus/`:
   ```bash
   prometheus --config.file=prometheus.yml
   ```
5. Abre `http://localhost:9090` → **Status > Targets** y confirma que los
   dos nodos aparecen en `UP`. En `http://localhost:9090/graph` puedes
   consultar métricas como `bme280_temperatura_celsius` o
   `dht22_wifi_rssi_dbm`.

El script no tiene dependencias más allá de `bash`, `curl` y `xargs`
(ya instalados en casi cualquier Linux). Variables de entorno opcionales:
`SUBRED` (default `10.203.58`), `PUERTO` (default `80`), `TIMEOUT` (segundos
por IP, default `0.4`), `PARALELISMO` (IPs en paralelo, default `64`).

Si prefieres no tener que dejar una terminal abierta, puedes en vez de
`--loop` agregarlo a una tarea de cron que corra cada minuto
(`crontab -e`: `* * * * * /ruta/a/descubrir_nodos.sh >> /tmp/descubrir.log 2>&1`).

Métricas que expone cada nodo (todas con la etiqueta `location="NODO_ID"`):

| Placa | Métricas |
| --- | --- |
| BME280 | `bme280_sensor_up`, `bme280_temperatura_celsius`, `bme280_humedad_porcentaje`, `bme280_presion_hpa`, `bme280_alert_active`, `bme280_wifi_rssi_dbm`, `bme280_errores_total` |
| DHT22 | `dht22_sensor_up`, `dht22_temperatura_celsius`, `dht22_humedad_porcentaje`, `dht22_wifi_rssi_dbm`, `dht22_errores_total` |

`*_errores_total` cuenta lecturas inválidas acumuladas desde que arrancó el
nodo (se reinicia a 0 en cada reinicio) — útil para alertar con
`rate(bme280_errores_total[10m]) > 0` si un sensor empieza a fallar seguido,
sin esperar a que deje de reportar por completo.

## Robustez del firmware

Además de la lógica de sensores y WiFi ya descrita:

- **I2C con timeout** (`Wire.setTimeOut(1000)` en `BME280Sensor::begin()`):
  sin esto, un bus I2C colgado (cable flojo, ruido) podía bloquear el
  `loop()` completo indefinidamente — con el timeout, esa lectura
  simplemente falla y el resto del firmware (WiFi, servidor HTTP) sigue
  funcionando.
- **Vigilancia de memoria** (`vigilarMemoria()` en `src/main.cpp`): cada 30s
  registra el heap libre por Serial, y si cae por debajo de
  `HEAP_MINIMO_BYTES` (`include/config.h`, 20000 bytes por defecto), el nodo
  se reinicia solo antes de arriesgarse a un crash impredecible por falta de
  memoria — pensado para un nodo que corre semanas sin supervisión.

## Problemas frecuentes

- **`Failed to connect`**: mantén presionado `BOOT`, pulsa `Upload` y suelta
  `BOOT` cuando empiece la conexión.
- **Monitor serial vacío**: pulsa `RESET` después de abrirlo y verifica que el
  cable USB transmita datos, no solo carga.
- **`[BME280] No se encontro en 0x76 ni en 0x77`**: revisa que VCC esté en
  3.3 V (no 5 V) y que SDA/SCL no estén invertidos.
- **DHT22 sin lectura valida**: revisa la resistencia pull-up entre DATA y
  VCC, que DATA este en GPIO4 (o el pin que hayas puesto en `PIN_DHT22`) y
  que VCC este en 3.3 V.
- **Una placa deja de responder cuando prendes/reflasheas la otra**: revisa
  que cada una se haya compilado con su propio entorno (`esp32-c3-bme280` /
  `esp32-c3-dht22`); si ambas comparten `NODO_ID` chocan en la red.
- **Nunca se conecta y se reinicia en bucle**: casi siempre es que el router
  está en 5 GHz o que el SSID lleva algún carácter distinto al escrito en
  `secrets.h`.
- **Se reinicia solo**: alimentación insuficiente. La Wi-Fi del ESP32-C3 tiene
  picos de corriente; usa una fuente de al menos 500 mA.
- **Target en `DOWN` en Prometheus**: confirma que `descubrir_nodos.sh
  --loop` sigue corriendo (si se cerró la terminal, los archivos en
  `prometheus/targets/` se quedan con la última IP conocida). Corre
  `./descubrir_nodos.sh` una vez a mano para ver si encuentra la placa; si
  dice "no encontrado", el problema es la placa/Wi-Fi, no Prometheus (ver
  sección **Prometheus**).
