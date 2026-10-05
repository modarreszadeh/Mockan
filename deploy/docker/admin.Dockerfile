# syntax=docker/dockerfile:1
# Admin API + the built Panel (control plane). Build from the repository root:
#   docker build -f deploy/docker/admin.Dockerfile -t mockan-admin .
# Panel on another path (OQ-03): --build-arg PANEL_BASE_PATH=/_mockan/admin/ and set the same
# value as MOCKAN_PANEL_BASE_PATH at runtime.

FROM node:24-slim AS panel
ARG PANEL_BASE_PATH=/
ENV VITE_PANEL_BASE_PATH=${PANEL_BASE_PATH}
WORKDIR /panel
COPY panel/package.json panel/package-lock.json ./
RUN npm ci
COPY panel/ ./
# `tsc -b` also checks the precedence parity test, which imports the fixture it shares with the
# server tests (panel/src/lib -> ../../../server/tests/matching).
COPY server/tests/matching/precedence_parity.json /server/tests/matching/precedence_parity.json
RUN npm run build

FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY server/pyproject.toml server/uv.lock server/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY server/src ./src
# Alembic: MOCKAN_MIGRATE_ON_STARTUP finds alembic.ini and migrations/ next to src/.
COPY server/alembic.ini ./
COPY server/migrations ./migrations
RUN uv sync --frozen --no-dev
COPY --from=panel /panel/dist ./src/mockan/admin/static

FROM python:3.14-slim
RUN useradd --system --uid 10001 --no-create-home mockan
WORKDIR /app
COPY --from=build --chown=mockan:mockan /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER mockan
EXPOSE 8081
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8081/api/v1/openapi.json', timeout=2)"]
CMD ["uvicorn", "mockan.admin.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8081", "--proxy-headers"]
