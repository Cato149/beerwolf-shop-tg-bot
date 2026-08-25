#!/bin/sh
# Production update on the VPS: sync git, rebuild Compose, reload host Caddy.
# GitHub Actions writes .env from secret APP_ENV before this script.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Branch to fast-forward onto (CI sets main).
BRANCH="${DEPLOY_BRANCH:-main}"

git fetch origin "$BRANCH"
git checkout -B "$BRANCH" "origin/$BRANCH"

if [ ! -f "$ROOT/.env" ]; then
	echo "deploy: $ROOT/.env is missing; GitHub Actions should write secret APP_ENV first" >&2
	exit 1
fi

docker compose up --build -d --remove-orphans
docker image prune -f

# Caddy lives on the host; keep /etc/caddy in sync with the repo and reload.
if [ -d /etc/caddy ]; then
	sudo cp "$ROOT/Caddyfile" /etc/caddy/Caddyfile
	sudo systemctl reload caddy
fi
