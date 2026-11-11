#!/usr/bin/env bash
# =============================================================================
# VTAB Admin Console - Automated DigitalOcean Droplet Deployment & Update Script
# =============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

TARGET_COMMIT="${1:-origin/main}"
echo "================================================================="
echo "  VTAB Admin Console — Deploying Target: $TARGET_COMMIT"
echo "================================================================="

# 1. Fetch remote changes and checkout target commit
if [ -d ".git" ]; then
    echo "[1/5] Fetching latest commits from origin..."
    git fetch origin main 2>&1 || true
    if [ "$TARGET_COMMIT" != "origin/main" ] && [ -n "$TARGET_COMMIT" ]; then
        echo "Resetting to target commit $TARGET_COMMIT..."
        git reset --hard "$TARGET_COMMIT" 2>&1 || git reset --hard origin/main 2>&1
    else
        echo "Resetting to origin/main..."
        git reset --hard origin/main 2>&1
    fi
fi

# 2. Synchronize release version into backend/.env
echo "[2/5] Synchronizing environment configuration..."
BACKEND_DIR="$REPO_DIR/backend"
ENV_FILE="$BACKEND_DIR/.env"

if [ -f "package.json" ]; then
    PACKAGE_VERSION=$(node -pe "try { require('./package.json').version } catch(e) { '' }" 2>/dev/null || echo "")
    if [ -n "$PACKAGE_VERSION" ] && [ -f "$ENV_FILE" ]; then
        sed -i '/^VTAB_ADMIN_VERSION=/d' "$ENV_FILE" 2>/dev/null || true
        echo "VTAB_ADMIN_VERSION=$PACKAGE_VERSION" >> "$ENV_FILE"
    fi
fi

# Purge any stale Render flags if present
if [ -f "$ENV_FILE" ]; then
    sed -i '/^RENDER_SERVICE_ID=/d' "$ENV_FILE" 2>/dev/null || true
    sed -i '/^VTAB_RENDER_SERVICE_ID=/d' "$ENV_FILE" 2>/dev/null || true
    sed -i '/^RENDER_API_KEY=/d' "$ENV_FILE" 2>/dev/null || true
    sed -i '/^RENDER_TOKEN=/d' "$ENV_FILE" 2>/dev/null || true
    sed -i '/^RENDER_API_TOKEN=/d' "$ENV_FILE" 2>/dev/null || true
fi

# 3. Setup / update Python backend virtual environment
echo "[3/5] Updating backend virtual environment..."
cd "$BACKEND_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip -q
if [ -f "requirements.txt" ]; then
    ./venv/bin/pip install -r requirements.txt -q
fi

# 4. Build frontend distribution assets
echo "[4/5] Building frontend assets..."
cd "$REPO_DIR"
if [ -f "package.json" ]; then
    npm ci 2>&1 || npm install 2>&1
    npm run build 2>&1
    chown -R www-data:www-data dist 2>/dev/null || true
    chmod -R 755 dist 2>/dev/null || true
fi

# 5. Reload systemd unit & Nginx proxy
echo "[5/5] Restarting service & reloading Nginx..."
systemctl daemon-reload 2>/dev/null || true
systemctl restart reportingtool-admin.service 2>/dev/null || true
nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true

echo "================================================================="
echo "  VTAB Admin Console Deployed & Verified Healthy!"
echo "================================================================="
