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

dc() {
    docker compose --env-file "$ENV_FILE" "$@"
}

echo "Stopping existing services..."
dc down || true

echo "Building Docker images..."
dc build

echo "Pulling latest images (non-fatal if none)..."
dc pull || true

echo "Starting services..."
dc up -d

echo "Waiting for backend to become healthy..."
sleep 15

echo "Checking service status..."
dc ps

echo "Verifying backend health..."
MAX_RETRIES=30
RETRY_COUNT=0
API_DOMAIN="${STAGING_API_DOMAIN:-worldskills-api.jamesyin.com}"
FRONTEND_DOMAIN="${STAGING_FRONTEND_DOMAIN:-worldskills.jamesyin.com}"

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -fsS "https://${API_DOMAIN}/health" > /dev/null 2>&1; then
        echo "Backend is healthy!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for backend... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Warning: Backend health check failed after $MAX_RETRIES retries"
    echo "Check logs with: dc logs world-skills-backend"
fi

echo "Verifying frontend..."
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -fsS "https://${FRONTEND_DOMAIN}/" > /dev/null 2>&1; then
        echo "Frontend is reachable!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Waiting for frontend... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "Warning: Frontend check failed after $MAX_RETRIES retries"
    echo "Check logs with: dc logs world-skills-frontend"
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
