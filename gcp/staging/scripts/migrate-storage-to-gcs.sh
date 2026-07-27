#!/bin/bash
# Upload local world-skills document storage to GCS (run from a machine with gsutil + local files).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

ENV_FILE="${ENV_FILE:-.env.staging.gcp}"
if [ -f "$PROJECT_ROOT/$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_ROOT/$ENV_FILE"
    set +a
fi

GCS_BUCKET="${GCS_BUCKET_NAME:-}"
PREFIX="${GCS_DOCUMENTS_PREFIX:-world-skills}"
PREFIX="${PREFIX#/}"
PREFIX="${PREFIX%/}"
DEST_PREFIX="$PREFIX"

if [ -z "$GCS_BUCKET" ]; then
    echo "Error: GCS_BUCKET_NAME not set. Add it to $ENV_FILE or export it."
    exit 1
fi

if ! command -v gsutil &> /dev/null; then
    echo "Error: gsutil not found. Install Google Cloud SDK."
    exit 1
fi

LOCAL_DIR="${LOCAL_STORAGE_DIR:-$PROJECT_ROOT/backend/storage/documents}"

cd "$PROJECT_ROOT"

echo "Syncing local exam documents to gs://$GCS_BUCKET/$DEST_PREFIX/"
echo "Source: $LOCAL_DIR"
echo ""

if [ ! -d "$LOCAL_DIR" ]; then
    echo "Nothing to migrate: directory missing or empty: $LOCAL_DIR"
    exit 0
fi

if ! gsutil ls -b "gs://$GCS_BUCKET" > /dev/null 2>&1; then
    echo "Bucket not found: gs://$GCS_BUCKET (create it in the console or gsutil mb)"
    exit 1
fi

gsutil -m rsync -r "$LOCAL_DIR" "gs://$GCS_BUCKET/$DEST_PREFIX"

echo ""
echo "Done. Objects are under gs://$GCS_BUCKET/$DEST_PREFIX/"
echo "Ensure STORAGE_BACKEND=gcs and GCS_DOCUMENTS_PREFIX matches ($PREFIX) in $ENV_FILE on the VM."
