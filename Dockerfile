# syntax=docker/dockerfile:1.7
#
# Minimal image for the Episodic Pivot system. Suitable for CI smoke checks
# today and for headless deployment to a Linux VM later (Phase 7).
#
# Build:  docker build -t episodic-pivot .
# Test:   docker run --rm episodic-pivot                   # runs `pytest`
# Shell:  docker run --rm -it --entrypoint bash episodic-pivot
# Run with secrets later: docker run --rm --env-file .env episodic-pivot ...

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY tests/ ./tests/
COPY config.yaml ./

RUN pip install --no-cache-dir ".[dev]"

RUN useradd --create-home --shell /bin/bash ep && chown -R ep:ep /app
USER ep

CMD ["pytest"]
