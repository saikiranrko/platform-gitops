# --------------------------------------------------------------------------
# Stage 1: build / install deps
# --------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir -e ".[dev]" || true

COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# --------------------------------------------------------------------------
# Stage 2: minimal runtime image (no build tools, smaller attack surface)
# --------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Security: run as non-root
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=builder /app/src ./src

USER appuser

EXPOSE 8000

# Health check — matches Kubernetes liveness probe path
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["uvicorn", "task_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
