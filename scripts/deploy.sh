#!/bin/sh
# Production update on the VPS: sync git over SSH, write .env, rebuild Compose, reload host Caddy.
# GitHub Actions passes APP_ENV. Clone/fetch use git@github.com and a Deploy key on this host.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Pin github.com host keys; use ~/.ssh/bot-bw-deploy when that file exists.
# shellcheck disable=SC1091
. "$ROOT/scripts/github-ssh.sh"

# Branch to fast-forward onto (CI sets main).
BRANCH="${DEPLOY_BRANCH:-main}"

if [ -n "${GITHUB_REPOSITORY:-}" ]; then
	git remote set-url origin "git@github.com:${GITHUB_REPOSITORY}.git"
fi

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
