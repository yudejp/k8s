#!/bin/sh
set -e

CURRENT_VERSION="${MEILI_VERSION:-$(/bin/meilisearch --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo unknown)}"
VERSION_FILE="/meili-data/.meilisearch-version"

STORED_VERSION=""
if [ -f "$VERSION_FILE" ]; then
  STORED_VERSION=$(cat "$VERSION_FILE")
fi

if [ "$STORED_VERSION" != "$CURRENT_VERSION" ]; then
  echo "[migration] Meilisearch version changed: ${STORED_VERSION:-<none>} -> ${CURRENT_VERSION}"
  echo "[migration] In-place migration enabled via MEILI_EXPERIMENTAL_DUMPLESS_UPGRADE"
  echo "$CURRENT_VERSION" > "$VERSION_FILE"
fi

exec /bin/meilisearch "$@"
