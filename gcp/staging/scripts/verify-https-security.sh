#!/bin/bash
# Verify HTTPS headers/cert coverage for world-skills staging hosts.

set -euo pipefail

# Space-separated lists; override to test a subset.
FRONTEND_HOSTS="${FRONTEND_HOSTS:-worldskills.jamesyin.com worldskills.ctvet.gov.gh}"
API_HOSTS="${API_HOSTS:-worldskills-api.jamesyin.com worldskills-api.ctvet.gov.gh}"
DASHBOARD_HOST="${DASHBOARD_HOST:-traefik-worldskills-staging.jamesyin.com}"

check_host() {
  local host="$1"
  local path="${2:-/}"
  echo "== ${host}${path} =="
  curl -k -sSI "https://${host}${path}" | awk '
    BEGIN{IGNORECASE=1}
    /HTTP\// || /content-security-policy:/ || /strict-transport-security:/ || /location:/ || /server:/
  '
  echo ""
}

echo "Verifying HTTPS security headers and redirect behavior..."
echo ""

for host in $FRONTEND_HOSTS; do
  check_host "$host" "/"
done
for host in $API_HOSTS; do
  check_host "$host" "/health"
done
check_host "$DASHBOARD_HOST" "/"

echo "== HTTP -> HTTPS redirect checks =="
for host in $FRONTEND_HOSTS $API_HOSTS "$DASHBOARD_HOST"; do
  echo "-- http://${host}/"
  curl -sSI "http://${host}/" | awk 'BEGIN{IGNORECASE=1} /HTTP\// || /location:/'
done
echo ""

first_frontend="${FRONTEND_HOSTS%% *}"
echo "== Certificate subject/issuer (first frontend host: ${first_frontend}) =="
echo | openssl s_client -servername "$first_frontend" -connect "${first_frontend}:443" 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
echo ""

echo "Done. If CSP or HSTS headers are missing, redeploy Traefik and re-run."
