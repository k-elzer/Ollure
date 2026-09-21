# syntax=docker/dockerfile:1.7

# Multi-stage Dockerfile
# BUILT LARGELY WITH COPILOT, WITH SOME MANUAL REFINEMENTS

# Builder stage: install deps into a virtual environment.
FROM dhi.io/python:3.13-alpine3.23-dev AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH=/opt/venv

WORKDIR /app

# TODO: remove the "&& rm -rf /var/lib/apt/lists/*" part - this is an artifact from the previous base image I used, and is redundant for alpine!
RUN apk add --no-cache ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv ${VENV_PATH}
ENV PATH="${VENV_PATH}/bin:${PATH}"

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Runtime stage: slim Python image with a named non-root user.
FROM dhi.io/python:3.13-alpine3.23-dev AS runtime

# UID and GID are 20001 because I created a user with these IDs for the docker container to use (e.g., to write to the in-out.log file without permission issues)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_DIR=/app/logs \
    APP_UID=20001 \
    APP_GID=20001 \
    VENV_PATH=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN addgroup -S -g ${APP_GID} app \
    && adduser -S -D -H -u ${APP_UID} -G app app \
    && mkdir -p /app/logs \
    && chown -R ${APP_UID}:${APP_GID} /app

# TODO: Use the PATH env variable instead of the hardcoded path
COPY --from=builder --chown=${APP_UID}:${APP_GID} /opt/venv /opt/venv
COPY --chown=${APP_UID}:${APP_GID} main.py logging_resources.py utils.py .env ./
COPY --chown=${APP_UID}:${APP_GID} classes ./classes
COPY --chown=${APP_UID}:${APP_GID} endpoints ./endpoints
COPY --chown=${APP_UID}:${APP_GID} response_cache ./response_cache

USER app

EXPOSE 11434

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "11434", "--log-level", "critical", "--no-server-header"]