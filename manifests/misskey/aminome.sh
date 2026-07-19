#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORK_DIR="${SCRIPT_DIR}/.aminome"
CONFIG="${WORK_DIR}/config.yml"
PID_FILE="${WORK_DIR}/port-forward-pids"

MISSKEY_NS=misskey-y2e-org
MEILI_SVC=meilisearch
DB_LOCAL_PORT=15432
MEILI_LOCAL_PORT=7700

cleanup() {
  echo "Cleaning up..."
  if [ -f "$PID_FILE" ]; then
    while read -r pid; do
      kill "$pid" 2>/dev/null || true
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  fi
  deactivate 2>/dev/null || true
}
trap cleanup EXIT INT TERM

mkdir -p "$WORK_DIR"

echo "=== Fetching secrets from Kubernetes ==="
DB_PASS=$(kubectl get secret -n "$MISSKEY_NS" misskey-db-pass \
  -o jsonpath='{.data.db-pass\.secret}' | base64 -d)
MEILI_API_KEY=$(kubectl get secret -n "$MISSKEY_NS" misskey-meilisearch-api-key \
  -o jsonpath='{.data.meilisearch-api-key\.secret}' | base64 -d)

echo "=== Creating config.yml ==="
cat > "$CONFIG" <<ENDCONFIG
db:
  host: localhost
  port: ${DB_LOCAL_PORT}
  db: misskey-y2e-org
  user: postgres
  pass: ${DB_PASS}

meilisearch:
  host: localhost
  port: ${MEILI_LOCAL_PORT}
  apiKey: '${MEILI_API_KEY}'
  index: 'misskey-y2e-org'
  scope: local
  ssl: false
ENDCONFIG

echo "=== Finding database pod ==="
DB_POD=$(kubectl get pod -n default -l cluster-name=za-pg-16,spilo-role=master \
  -o jsonpath='{.items[0].metadata.name}')

echo "=== Starting port-forwards ==="
kubectl port-forward -n default "pod/${DB_POD}" "${DB_LOCAL_PORT}:5432" > /dev/null &
echo $! >> "$PID_FILE"

kubectl port-forward -n default "service/${MEILI_SVC}" "${MEILI_LOCAL_PORT}:7700" > /dev/null &
echo $! >> "$PID_FILE"

sleep 3

echo "=== Setting up Python venv ==="
python3 -m venv "${WORK_DIR}/venv"
source "${WORK_DIR}/venv/bin/activate"
pip install -q -r "${SCRIPT_DIR}/aminome-requirements.txt"

echo "=== Fetching aminome.py ==="
AMINOME_PY="${WORK_DIR}/aminome.py"
if [ ! -f "$AMINOME_PY" ]; then
  curl -fsSL -o "$AMINOME_PY" \
    https://raw.githubusercontent.com/nakkaa/aminome/master/aminome.py
fi

echo "=== Running aminome ==="
python3 "$AMINOME_PY" -c "$CONFIG"

echo "=== Done ==="
