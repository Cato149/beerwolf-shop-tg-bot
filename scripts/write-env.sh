#!/bin/sh
# Write production .env from APP_ENV (full dotenv text, GitHub Actions secret).
# Does not print the file contents.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

if [ -z "${APP_ENV:-}" ]; then
	echo "write-env: APP_ENV is empty (GitHub secret with the full .env body)" >&2
	exit 1
fi

tmp="$(mktemp "${ENV_FILE}.XXXXXX")"
trap 'rm -f "$tmp"' EXIT INT HUP TERM

printf '%s' "$APP_ENV" >"$tmp"
# Ensure the file ends with a newline so dotenv parsers see the last key.
[ -n "$(tail -c 1 "$tmp")" ] && printf '\n' >>"$tmp"

if ! grep -q '^BOT_TOKEN=' "$tmp" || ! grep -q '^DATABASE_URL=' "$tmp"; then
	echo "write-env: APP_ENV does not look like a valid .env (need BOT_TOKEN and DATABASE_URL)" >&2
	exit 1
fi

chmod 600 "$tmp"
mv "$tmp" "$ENV_FILE"
trap - EXIT INT HUP TERM

echo "write-env: wrote $ENV_FILE" >&2
