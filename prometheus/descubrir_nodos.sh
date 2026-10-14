set -uo pipefail

for cmd in curl xargs mktemp grep; do
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

declare -A NODOS=(  # node_id
  ["bme280_esp32c3_01"]="bme280"
  ["bme280_esp32c3_02"]="bme280"
  ["bme280_esp32c3_03"]="bme280"
  ["dht22_esp32c3_01"]="dht22"
)

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
  local -A entradas_por_job=()

  for node_id in "${!NODOS[@]}"; do
    local job="${NODOS[$node_id]}"
    local linea ip entrada
    linea="$(grep -F "\"node_id\":\"$node_id\"" "$tmp" | head -n 1)"
    if [ -z "$linea" ]; then
      echo "[$(date +%Y-%m-%d\ %H:%M:%S)] ERROR: no se encontró el nodo '$node_id'" >&2
      continue
    fi
    ip="${linea%%|*}"
    entrada="{\"targets\": [\"$ip:$PUERTO\"], \"labels\": {\"nodo\": \"$node_id\"}}"
    if [ -z "${entradas_por_job[$job]:-}" ]; then
      entradas_por_job[$job]="$entrada"
    else
      entradas_por_job[$job]="${entradas_por_job[$job]}, $entrada"
    fi
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] NODO: '$node_id' IP: $ip"
  done

  local encontrados=0
  for job in "${!entradas_por_job[@]}"; do
    printf '[%s]\n' "${entradas_por_job[$job]}" >"$DIR/$job.json.nuevo"
    mv "$DIR/$job.json.nuevo" "$DIR/$job.json"
    encontrados=$((encontrados + 1))
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
