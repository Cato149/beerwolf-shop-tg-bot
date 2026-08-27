#!/bin/sh
# Map UMAMI_* vars from the shared .env onto the names the Umami image expects.
# The bot already uses DATABASE_URL with the SQLAlchemy +asyncpg prefix.
set -eu

if [ -z "${UMAMI_DATABASE_URL:-}" ]; then
	echo "umami-start: UMAMI_DATABASE_URL is empty" >&2
	exit 1
fi
if [ -z "${UMAMI_APP_SECRET:-}" ]; then
	echo "umami-start: UMAMI_APP_SECRET is empty" >&2
	exit 1
fi

export DATABASE_URL="$UMAMI_DATABASE_URL"
export APP_SECRET="$UMAMI_APP_SECRET"

if [ -n "${UMAMI_TWO_FACTOR_ENCRYPTION_KEY:-}" ]; then
	export TWO_FACTOR_ENCRYPTION_KEY="$UMAMI_TWO_FACTOR_ENCRYPTION_KEY"
fi
if [ -n "${UMAMI_CLIENT_IP_HEADER:-}" ]; then
	export CLIENT_IP_HEADER="$UMAMI_CLIENT_IP_HEADER"
fi
if [ -n "${UMAMI_DISABLE_TELEMETRY:-}" ]; then
	export DISABLE_TELEMETRY="$UMAMI_DISABLE_TELEMETRY"
fi

# Bot uses ru/en; Umami's DEFAULT_LOCALE is a different (mostly build-time) flag.
unset DEFAULT_LOCALE

exec sh scripts/start-docker.sh
