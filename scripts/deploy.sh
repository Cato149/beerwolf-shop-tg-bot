#!/bin/sh
# Production update on the VPS: sync git, write .env, rebuild Compose, reload host Caddy.
# GitHub Actions passes APP_ENV (full dotenv text). Local runs can reuse an existing .env.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Branch to fast-forward onto (CI sets main).
BRANCH="${DEPLOY_BRANCH:-main}"

git fetch origin "$BRANCH"
git checkout -B "$BRANCH" "origin/$BRANCH"

if [ -n "${APP_ENV:-}" ]; then
	ENV_FILE="$ROOT/.env" APP_ENV="$APP_ENV" "$ROOT/scripts/write-env.sh"
	chmod 600 "$ROOT/.env"
elif [ ! -f "$ROOT/.env" ]; then
	echo "deploy: $ROOT/.env is missing and APP_ENV is empty" >&2
	exit 1
fi

docker compose up --build -d --remove-orphans
docker image prune -f

# Caddy lives on the host; keep /etc/caddy in sync with the repo and reload.
if [ -d /etc/caddy ]; then
	sudo cp "$ROOT/Caddyfile" /etc/caddy/Caddyfile
	sudo systemctl reload caddy
fi
