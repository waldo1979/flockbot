FROM python:3.11-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY . .

RUN useradd --create-home appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app/data
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, signal; pid=int(open('/proc/1/stat').read().split()[0]); os.kill(pid, 0)" || exit 1

CMD ["uv", "run", "python", "bot.py"]
