#!/bin/bash
# Create secrets in GCP Secret Manager for exam-tools staging (interactive prompts)

set -e

PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"

echo "Creating secrets in GCP Secret Manager for project: $PROJECT_ID"
echo "You will be prompted for each value."

create_secret() {
    local secret_name=$1
    local description=$2

    if gcloud secrets describe "$secret_name" --project="$PROJECT_ID" > /dev/null 2>&1; then
        echo "Secret $secret_name already exists. Updating..."
        echo -n "Enter new value for $secret_name (or press Enter to skip): "
        read -s secret_value
        echo
        if [ -n "$secret_value" ]; then
            echo -n "$secret_value" | gcloud secrets versions add "$secret_name" --project="$PROJECT_ID" --data-file=-
            echo "Secret $secret_name updated"
        else
            echo "Skipped updating $secret_name"
        fi
    else
        echo "Creating secret: $secret_name ($description)"
        echo -n "Enter value for $secret_name: "
        read -s secret_value
        echo
        if [ -n "$secret_value" ]; then
            echo -n "$secret_value" | gcloud secrets create "$secret_name" --project="$PROJECT_ID" --data-file=- --replication-policy="automatic"
            echo "Secret $secret_name created"
        else
            echo "Warning: Empty value for $secret_name, skipping"
        fi
    fi
}

echo ""
echo "Database..."
create_secret "exam-tools-db-password" "PostgreSQL password for exam-tools"
create_secret "exam-tools-db-user" "PostgreSQL user for exam-tools"

echo ""
echo "Application..."
create_secret "exam-tools-secret-key" "JWT signing secret (SECRET_KEY)"

echo ""
echo "Super admin bootstrap (optional; can use plain env instead)..."
create_secret "exam-tools-super-admin-password" "Initial SUPER_ADMIN password"

echo ""
echo "Cloud SQL..."
create_secret "exam-tools-cloud-sql-connection-name" "Instance connection name project:region:instance"

echo ""
echo "Storage (optional if bucket name is only in .env)..."
create_secret "exam-tools-gcs-bucket-name" "GCS bucket for exam documents"

echo ""
echo "Done. Grant your VM service account roles/secretmanager.secretAccessor on these secrets, then fill .env.staging.gcp."
