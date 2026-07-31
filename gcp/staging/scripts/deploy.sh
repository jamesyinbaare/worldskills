#!/bin/bash
# Deployment script for world-skills staging on GCP (dedicated VM + Docker Compose + Traefik)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ENV_FILE="${ENV_FILE:-.env.staging.gcp}"

cd "$PROJECT_ROOT"

echo "Starting deployment for world-skills staging..."
echo "Project root: $PROJECT_ROOT"
echo "Environment file: $ENV_FILE"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: Environment file $ENV_FILE not found"
    echo "Please copy .env.staging.gcp.example to $ENV_FILE and configure it"
    exit 1
fi

echo "Loading environment variables from $ENV_FILE..."
set -a
source "$ENV_FILE"
set +a

export COMPOSE_FILE="${COMPOSE_FILE:-compose.staging.gcp.yaml}"
echo "Compose file: $COMPOSE_FILE"

# BuildKit enables cache mounts (npm/uv) and faster layer reuse on the VM
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

dc() {
    docker compose --env-file "$ENV_FILE" "$@"
}

echo "Building Docker images (while old stack stays up)..."
dc build --parallel

echo "Pulling latest images (non-fatal if none)..."
dc pull || true

echo "Stopping existing services..."
dc down || true

echo "Starting services..."
dc up -d

echo "Waiting for backend container healthcheck..."
MAX_RETRIES=36
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if dc ps world-skills-backend 2>/dev/null | grep -qiE '\(healthy\)'; then
        echo "Backend container is healthy."
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for backend container... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Warning: Backend container did not become healthy in time"
    echo "Check logs with: docker compose --env-file $ENV_FILE -f $COMPOSE_FILE logs world-skills-backend"
fi

echo "Checking service status..."
dc ps

API_DOMAIN="${STAGING_API_DOMAIN:-worldskills-api.jamesyin.com}"
FRONTEND_DOMAIN="${STAGING_FRONTEND_DOMAIN:-worldskills.jamesyin.com}"

echo "Verifying backend /health inside the container..."
if dc exec -T world-skills-backend curl -fsS "http://127.0.0.1:80/health" > /dev/null; then
    echo "Backend /health OK (in-container)."
else
    echo "Warning: in-container /health failed"
    dc logs --tail 80 world-skills-backend || true
fi

echo "Verifying backend via Traefik on localhost (Host header; avoids VM hairpin to public IP)..."
if curl -fsS -o /dev/null \
    --connect-timeout 5 \
    -H "Host: ${API_DOMAIN}" \
    "http://127.0.0.1/health"; then
    echo "Backend reachable via Traefik HTTP on :80."
elif curl -fkSs -o /dev/null \
    --connect-timeout 5 \
    -H "Host: ${API_DOMAIN}" \
    "https://127.0.0.1/health"; then
    echo "Backend reachable via Traefik HTTPS on :443."
else
    echo "Warning: Traefik local Host-header check failed (routing/TLS may still be warming up)."
    echo "  Try: curl -v -H 'Host: ${API_DOMAIN}' http://127.0.0.1/health"
fi

echo "Verifying public HTTPS (best-effort; may fail from the VM due to hairpin NAT)..."
MAX_RETRIES=6
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -fsS --connect-timeout 5 "https://${API_DOMAIN}/health" > /dev/null 2>&1; then
        echo "Backend is reachable at https://${API_DOMAIN}/health"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for public backend HTTPS... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Warning: public https://${API_DOMAIN}/health failed from this host."
    echo "  Containers may still be fine — check from your laptop or: curl -v https://${API_DOMAIN}/health"
fi

echo "Verifying frontend via Traefik on localhost..."
if curl -fsS -o /dev/null --connect-timeout 5 -H "Host: ${FRONTEND_DOMAIN}" "http://127.0.0.1/" \
    || curl -fkSs -o /dev/null --connect-timeout 5 -H "Host: ${FRONTEND_DOMAIN}" "https://127.0.0.1/"; then
    echo "Frontend reachable via Traefik on localhost."
else
    echo "Warning: Traefik local frontend check failed"
fi

echo "Verifying public frontend HTTPS (best-effort)..."
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -fsS --connect-timeout 5 "https://${FRONTEND_DOMAIN}/" > /dev/null 2>&1; then
        echo "Frontend is reachable at https://${FRONTEND_DOMAIN}/"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for public frontend HTTPS... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Warning: public https://${FRONTEND_DOMAIN}/ failed from this host (often hairpin NAT)."
fi

echo ""
echo "Deployment complete!"
echo ""
echo "Services:"
echo "  - Frontend: https://${FRONTEND_DOMAIN}"
echo "  - Backend API: https://${API_DOMAIN}"
echo "  - Traefik dashboard (if configured): port 8080 on this host (restrict via firewall)"
echo ""
echo "View logs:"
echo "  docker compose --env-file $ENV_FILE -f $COMPOSE_FILE logs -f"
