# Override PYTHON_IMAGE to use a reachable mirror without a second Dockerfile.
ARG PYTHON_IMAGE=python:3.12-slim
ARG NODE_IMAGE=node:22-alpine
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.19
FROM ${UV_IMAGE} AS uv

FROM ${NODE_IMAGE} AS frontend
WORKDIR /frontend
ENV PNPM_CONFIG_STORE_DIR=/pnpm/store
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack enable && corepack install
RUN --mount=type=cache,target=/pnpm/store pnpm install --frozen-lockfile --store-dir=/pnpm/store
COPY vite.config.ts tsconfig.json ./
COPY scripts ./scripts
COPY frontend ./frontend
RUN pnpm run build

FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

FROM ${PYTHON_IMAGE}
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OPPLE_CONFIG=/config/config.yaml OPPLE_DATA=/data PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
RUN groupadd --gid 10001 light && useradd --uid 10001 --gid 10001 --no-create-home light && mkdir /data /config && chown light:light /data
COPY app ./app
COPY --from=frontend /frontend/frontend/dist ./frontend/dist
COPY config/config.yaml /config/config.yaml
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=2)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]
