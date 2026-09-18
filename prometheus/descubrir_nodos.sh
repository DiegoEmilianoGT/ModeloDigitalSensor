#!/usr/bin/env bash
# Escanea la subred de los ESP32 y genera targets/*.json (file_sd_configs)
# con su IP actual. Uso: ./descubrir_nodos.sh [--loop [segundos]]
set -uo pipefail  # sin -e a proposito: el grep de mas abajo puede fallar sin abortar

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

declare -A NODOS=(  # node_id (segun /data de cada placa) -> job de Prometheus
  ["bme280_esp32c3_01"]="bme280"
  ["dht22_esp32c3_01"]="dht22"
)

escanear_una_vez() {
  local tmp
  if ! tmp="$(mktemp)"; then
    echo "ERROR: no se pudo crear un archivo temporal, se salta este escaneo." >&2
    return 1
  fi

  seq 1 254 | xargs -P "$PARALELISMO" -I{} bash -c '
    ip="'"$SUBRED"'.{}"
    resp=$(curl -s -m '"$TIMEOUT"' "http://$ip:'"$PUERTO"'/data" 2>/dev/null)
    [ -n "$resp" ] && printf "%s|%s\n" "$ip" "$resp"
  ' > "$tmp"

  local encontrados=0
  for node_id in "${!NODOS[@]}"; do
    local job="${NODOS[$node_id]}"
    local linea ip
    linea=$(grep -F "\"node_id\":\"$node_id\"" "$tmp" | head -1)
    if [ -z "$linea" ]; then
      echo "[$(date '+%H:%M:%S')] $node_id ($job): no encontrado en $SUBRED.0/24"
      continue
    fi
    ip="${linea%%|*}"
    printf '[{"targets":["%s:%s"],"labels":{"nodo":"%s"}}]\n' "$ip" "$PUERTO" "$node_id" \
      > "$DIR/$job.json.nuevo"
    mv "$DIR/$job.json.nuevo" "$DIR/$job.json"
    echo "[$(date '+%H:%M:%S')] $node_id ($job) -> $ip"
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
