FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv pip install --system .

COPY src/ src/

ENTRYPOINT ["blotter"]
