#!/bin/sh
# Create the Umami logical database on the shared Postgres instance if it is missing.
# Official postgres image runs docker-entrypoint-initdb.d only on an empty volume,
# so this job also covers existing deployments.
set -eu

if [ -z "${POSTGRES_USER:-}" ] || [ -z "${POSTGRES_PASSWORD:-}" ]; then
	echo "ensure-umami-db: POSTGRES_USER and POSTGRES_PASSWORD are required" >&2
	exit 1
fi

db_name="${UMAMI_POSTGRES_DB:-umami}"
# Identifiers only: keep CREATE DATABASE safe against unexpected .env values.
case "$db_name" in
*[!a-zA-Z0-9_]*)
	echo "ensure-umami-db: UMAMI_POSTGRES_DB must be alphanumeric or underscore" >&2
	exit 1
	;;
esac

export PGPASSWORD="$POSTGRES_PASSWORD"
export PGHOST="${POSTGRES_HOST:-db}"
export PGUSER="$POSTGRES_USER"
export PGDATABASE="postgres"

exists="$(psql -tAc "SELECT 1 FROM pg_database WHERE datname = '${db_name}'")"
if [ "$exists" = "1" ]; then
	echo "ensure-umami-db: database ${db_name} already exists"
	exit 0
fi

psql -c "CREATE DATABASE ${db_name}"
echo "ensure-umami-db: created database ${db_name}"
