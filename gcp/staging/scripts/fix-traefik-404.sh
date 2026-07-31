#!/bin/bash
# Diagnose and fix Traefik host-router 404s for worldskills domains on staging VM.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ENV_FILE="${ENV_FILE:-.env.staging.gcp}"
COMPOSE_FILE="${COMPOSE_FILE:-compose.staging.gcp.yaml}"
TRAEFIK_CONTAINER="${TRAEFIK_CONTAINER:-world-skills-traefik-staging}"
FRONTEND_HOST="${FRONTEND_HOST:-worldskills.jamesyin.com}"
API_HOST="${API_HOST:-worldskills-api.jamesyin.com}"
FRONTEND_HOST_ALT="${FRONTEND_HOST_ALT:-worldskills.ctvet.gov.gh}"
API_HOST_ALT="${API_HOST_ALT:-worldskills-api.ctvet.gov.gh}"

cd "$PROJECT_ROOT"

dc() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

echo "== 1) Identify listener on 80/443/8080 =="
ss -ltnp | awk 'NR==1 || /:80 |:443 |:8080 /'

echo ""
echo "== 2) Active Traefik-like containers =="
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}' | awk 'NR==1 || /traefik/i'

echo ""
echo "== 3) Ensure world-skills stack is up =="
dc up -d

echo ""
echo "== 4) Check Traefik container is running =="
if ! docker ps --format '{{.Names}}' | awk -v target="$TRAEFIK_CONTAINER" '$0==target{found=1} END{exit(found?0:1)}'; then
  echo "ERROR: Expected Traefik container '$TRAEFIK_CONTAINER' is not running."
  exit 1
fi

echo ""
echo "== 5) Validate mounted Traefik config inside container =="
docker exec "$TRAEFIK_CONTAINER" sh -c "ls -l /etc/traefik/traefik.staging.yml /etc/traefik/dynamic.staging.yml"
docker exec "$TRAEFIK_CONTAINER" sh -c "grep -nE 'jamesyin\\.com|ctvet\\.gov\\.gh' /etc/traefik/dynamic.staging.yml || true"

echo ""
echo "== 6) Verify live routers from Traefik API =="
if ! curl -fsS "http://127.0.0.1:8080/api/http/routers" | grep -q "worldskills-frontend-jamesyin"; then
  echo "WARNING: worldskills frontend jamesyin router not present in live Traefik API output."
fi
if ! curl -fsS "http://127.0.0.1:8080/api/http/routers" | grep -q "worldskills-backend-jamesyin"; then
  echo "WARNING: worldskills backend jamesyin router not present in live Traefik API output."
fi

echo ""
echo "== 7) Local host-header tests against loopback HTTPS =="
curl -k -I -H "Host: ${FRONTEND_HOST}" https://127.0.0.1 || true
curl -k -I -H "Host: ${FRONTEND_HOST_ALT}" https://127.0.0.1 || true
curl -k -I -H "Host: ${API_HOST}" https://127.0.0.1/health || true
curl -k -I -H "Host: ${API_HOST_ALT}" https://127.0.0.1/health || true

echo ""
echo "== 8) Public URL tests =="
curl -k -I "https://${FRONTEND_HOST}" || true
curl -k -I "https://${FRONTEND_HOST_ALT}" || true
curl -k -I "https://${API_HOST}/health" || true
curl -k -I "https://${API_HOST_ALT}/health" || true

echo ""
echo "Done. If 404 persists:"
echo "- Confirm no other stack owns :80/:443 on this VM."
echo "- Confirm Traefik API at :8080 shows worldskills routers."
echo "- If another traefik container owns :80/:443, stop that stack and rerun this script."
