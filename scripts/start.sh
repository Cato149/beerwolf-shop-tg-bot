#!/bin/sh
set -eu
uv run --no-dev alembic upgrade head
exec uv run --no-dev uvicorn beerwolf_shop.main:app --host 0.0.0.0 --port 8000
