# syntax=docker/dockerfile:1
# Gateway (data plane). Build from the repository root:
#   docker build -f deploy/docker/gateway.Dockerfile -t mockan-gateway .
FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first: this layer is cached until pyproject.toml or uv.lock change.
COPY server/pyproject.toml server/uv.lock server/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY server/src ./src
RUN uv sync --frozen --no-dev

FROM python:3.14-slim
RUN useradd --system --uid 10001 --no-create-home mockan
WORKDIR /app
COPY --from=build --chown=mockan:mockan /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    # Uvicorn reads this itself: set it to the ingress CIDRs (arch §12.3).
    FORWARDED_ALLOW_IPS=127.0.0.1
USER mockan
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/_mockan/health/live', timeout=2)"]
CMD ["uvicorn", "mockan.gateway.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
