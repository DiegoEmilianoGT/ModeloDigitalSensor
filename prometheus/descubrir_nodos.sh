set -uo pipefail

for cmd in curl xargs mktemp grep sed sort; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: falta el comando '$cmd', instalalo antes de correr esto." >&2
    exit 1
  }
done

SUBRED="${SUBRED:-10.203.58}"
PUERTO="${PUERTO:-80}"
TIMEOUT="${TIMEOUT:-0.4}"
PARALELISMO="${PARALELISMO:-64}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/targets"
mkdir -p "$DIR" || {
  echo "ERROR: no se pudo crear el directorio $DIR (revisa permisos)." >&2
  exit 1
}

declare -A NODOS=(  # node_id -> job de Prometheus
  ["bme280_esp32c3_01"]="bme280"
  ["bme280_esp32c3_02"]="bme280"
  ["bme280_esp32c3_03"]="bme280"
  ["bme280_esp32c3_04"]="bme280"
  ["bme280_esp32c3_05"]="bme280"
  ["bme280_esp32c3_06"]="bme280"
  ["dht22_esp32c3_01"]="dht22"
  ["supermini_esp32c3_01"]="bme280"  # BME280 y DHT22
)

ahora() { date +%Y-%m-%d\ %H:%M:%S; }
destinos_anteriores() {
  cat "$DIR"/*.json 2>/dev/null \
    | grep -oE '"targets": ?\["[^"]+"\], ?"labels": ?\{"nodo": ?"[^"]+"' \
    | sed -E 's/.*\["([^"]+)"\].*"nodo": ?"([^"]+)"$/\2 \1/'
}

escanear_una_vez() {
  local tmp
  if ! tmp="$(mktemp)"; then
    echo "ERROR: no se pudo crear un archivo temporal." >&2
    return 1
  fi
  seq 1 254 | xargs -P "$PARALELISMO" -I{} bash -c '
    ip="'$SUBRED'.{}"
    resp=$(curl -s -m "'$TIMEOUT'" "http://$ip:'$PUERTO'/data" 2>/dev/null)
    [ -n "$resp" ] && printf "%s|%s\n" "$ip" "$resp"
  ' >"$tmp"

  local -A anterior=() encontrado=() usados=() entradas_por_job=()
  local node_id destino linea job entrada
  while read -r node_id destino; do
    anterior[$node_id]="$destino"
  done < <(destinos_anteriores)

  for node_id in "${!NODOS[@]}"; do
    linea="$(grep -F "\"node_id\":\"$node_id\"" "$tmp" | head -n 1)"
    if [ -n "$linea" ]; then
      encontrado[$node_id]="${linea%%|*}:$PUERTO"
      usados[${encontrado[$node_id]}]=1
    fi
  done

  for node_id in $(printf '%s\n' "${!NODOS[@]}" | sort); do
    job="${NODOS[$node_id]}"
    if [ -n "${encontrado[$node_id]:-}" ]; then
      destino="${encontrado[$node_id]}"
      echo "[$(ahora)] NODO: '$node_id' IP: ${destino%:*}"
    elif [ -n "${anterior[$node_id]:-}" ]; then
      destino="${anterior[$node_id]}"
      if [ -n "${usados[$destino]:-}" ]; then
        echo "[$(ahora)] ERROR: '$node_id' no responde y su ultima IP (${destino%:*}) ya es de otro nodo" >&2
        continue
      fi
      usados[$destino]=1
      echo "[$(ahora)] ERROR: '$node_id' no responde, se conserva su ultima IP ${destino%:*}" >&2
    else
      echo "[$(ahora)] ERROR: no se encontró el nodo '$node_id'" >&2
      continue
    fi
    entrada="{\"targets\": [\"$destino\"], \"labels\": {\"nodo\": \"$node_id\"}}"
    if [ -z "${entradas_por_job[$job]:-}" ]; then
      entradas_por_job[$job]="$entrada"
    else
      entradas_por_job[$job]="${entradas_por_job[$job]}, $entrada"
    fi
  done


  #reescribe los archivos de destino para cada job
  for job in $(printf '%s\n' "${NODOS[@]}" | sort -u); do
    printf '[%s]\n' "${entradas_por_job[$job]:-}" >"$DIR/$job.json.nuevo"
    mv "$DIR/$job.json.nuevo" "$DIR/$job.json"
  done

  rm -f "$tmp"
  return 0
}

if [ "${1:-}" = "--loop" ]; then
  intervalo="${2:-30}"
  echo "Escaneando $SUBRED.0/24 cada ${intervalo}s (Ctrl+C para salir)..."
  while true; do
    escanear_una_vez
    sleep "$intervalo"
  done
else
  escanear_una_vez
fi
