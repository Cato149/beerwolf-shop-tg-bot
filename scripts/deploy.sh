#!/bin/sh
# Production update on the VPS: sync git, write .env, rebuild Compose, reload host Caddy.
# GitHub Actions passes APP_ENV and GH_CLONE_TOKEN (HTTPS, no github.com SSH on the VPS).
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Branch to fast-forward onto (CI sets main).
BRANCH="${DEPLOY_BRANCH:-main}"

if [ -n "${GH_CLONE_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
	git remote set-url origin "https://github.com/${GITHUB_REPOSITORY}.git"
	# Token only in the git process env, not stored in .git/config.
	git -c "http.extraheader=AUTHORIZATION: bearer ${GH_CLONE_TOKEN}" fetch origin "$BRANCH"
else
	git fetch origin "$BRANCH"
fi
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
