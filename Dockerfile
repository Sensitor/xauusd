# GoldMind AI — API / analysis service image.
# The MT5 execution node is NOT this image (MetaTrader5 is Windows-only); it runs
# separately on a Windows/Wine host. This image carries the analysis core + API.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# System deps kept minimal (numpy/pandas/psycopg ship wheels).
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# App source.
COPY pyproject.toml ./
COPY src ./src

# Non-root runtime user.
RUN useradd --create-home --uid 10001 goldmind && chown -R goldmind:goldmind /app
USER goldmind

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "goldmind.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
