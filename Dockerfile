FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY locales ./locales
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts

# Lockfile is copied when present so Docker builds stay reproducible in CI.
COPY uv.lock ./

RUN uv sync --frozen --no-dev

RUN chmod +x /app/scripts/start.sh

EXPOSE 8000

CMD ["/app/scripts/start.sh"]
