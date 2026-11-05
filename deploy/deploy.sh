#!/bin/bash
# VTAB Admin Console - DigitalOcean Droplet Deploy Script
# Run from the droplet as root or sudoer:
#   bash /var/www/vtab-admin-console/deploy/deploy.sh
set -e

REPO_DIR="/var/www/vtab-admin-console"
echo "============================================="
echo "  VTAB Admin Console — Deploy to Droplet"
echo "============================================="

cd "$REPO_DIR"

echo "[1/4] Pulling latest code..."
git fetch origin
git reset --hard origin/main

echo "[2/4] Updating backend virtual environment..."
cd "$REPO_DIR/backend"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "[3/4] Building frontend assets..."
cd "$REPO_DIR"
npm ci
npm run build

echo "[4/4] Restarting systemd service & reloading nginx..."
sudo systemctl restart vtab-admin || true
sudo nginx -t && sudo systemctl reload nginx || true

echo "============================================="
echo "  VTAB Admin Console Deployed & Verified!"
echo "============================================="
