#!/usr/bin/env bash
# VPS bootstrap for the Ohabai WhatsApp connector.
# Tested on Ubuntu 24.04 LTS. Run as root.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo $0"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Installing Docker Compose plugin..."
  apt-get update -qq
  apt-get install -y -qq docker-compose-plugin
fi

systemctl enable docker
systemctl start docker

if ! id -u ohabai >/dev/null 2>&1; then
  echo "Creating ohabai user..."
  useradd -m -s /bin/bash ohabai
  usermod -aG docker ohabai
fi

echo
echo "Bootstrap done. Next steps:"
echo "  su - ohabai"
echo "  git clone https://github.com/taxiproduction2002-sys/ohabai-pipeline.git"
echo "  cd ohabai-pipeline/connectors/whatsapp-baileys"
echo "  cp .env.production.example .env.production"
echo "  # edit .env.production with COMPANY_ID, CHANNEL_ACCOUNT_ID, CONNECTOR_SECRET"
echo "  docker compose up -d"
echo "  docker compose logs -f   # watch for QR on first run"
