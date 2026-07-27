#!/bin/bash
# Run on a new Ubuntu 22.04 GCE VM: Docker, Compose plugin, optional gcloud CLI

set -e

echo "Setting up GCE VM for world-skills staging..."

echo "Updating packages..."
sudo apt-get update
sudo apt-get upgrade -y

echo "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker "$USER"
    rm get-docker.sh
else
    echo "Docker already installed"
fi

echo "Installing Docker Compose plugin..."
if ! docker compose version &> /dev/null; then
    sudo apt-get install -y docker-compose-plugin
else
    echo "Docker Compose already installed"
fi

echo "Optional: gcloud CLI (skip if not needed on the VM)..."
if ! command -v gcloud &> /dev/null; then
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
    sudo apt-get update && sudo apt-get install -y google-cloud-cli
else
    echo "gcloud already installed"
fi

echo "Done. Re-login or newgrp docker if you were added to the docker group."
echo "Next: clone the repo, copy .env.staging.gcp.example to .env.staging.gcp, run gcp/staging/scripts/deploy.sh"
