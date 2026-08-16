FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/
WORKDIR /workspace
COPY apps/api/pyproject.toml apps/api/uv.lock* ./apps/api/
RUN uv sync --project apps/api --frozen --no-dev

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH="/workspace/apps/api" \
    PATH="/workspace/apps/api/.venv/bin:$PATH"
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser
WORKDIR /workspace
COPY --from=builder /workspace/apps/api/.venv ./apps/api/.venv
COPY apps/api ./apps/api
USER appuser
CMD ["sh", "-c", "uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port ${PORT:-8000}"]
