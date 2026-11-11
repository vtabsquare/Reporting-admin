#!/usr/bin/env bash
# Forward to root deploy.sh
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$REPO_DIR/deploy.sh" "$@"
