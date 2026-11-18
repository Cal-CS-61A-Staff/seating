# syntax=docker/dockerfile:1

# Image for deploying the seating app to Google Cloud Run.

# ---------------------------------------------------------------------------
# Build stage
#
# Installs the Python dependencies into a venv that is copied into the
# runtime stage, so pip and its build cache stay out of the shipped image.
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copied on its own so the dependency layer is only rebuilt when the pins change.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.14-slim

RUN useradd --create-home --uid 1000 app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app
COPY --chown=app:app . .

# Flask-Caching stores Cal1Card photos here (CACHE_DIR in server/cache.py), so
# it has to exist and be writable by the unprivileged user.
RUN mkdir -p /app/.cache && chown app:app /app/.cache

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:" + os.environ.get("PORT", "8080") + "/health/")'

# With RUN_MIGRATIONS=true (to set on staging and production, never on PR previews,
# which share the staging database), apply database migrations before starting.
# `exec` keeps gunicorn as PID 1 so it gets SIGTERM directly on redeploy.
# Cloud Run's default instance is 1 vCPU, so one worker process with threads
# (Google's recommended pattern) handles concurrent I/O-bound requests without
# duplicating the app in memory. Override WEB_CONCURRENCY / GUNICORN_THREADS
# to tune; GUNICORN_TIMEOUT if a slower Canvas import needs longer than 120s.
CMD ["sh", "-c", "if [ \"$RUN_MIGRATIONS\" = true ]; then flask --app server.main db upgrade || exit 1; fi; exec gunicorn -b 0.0.0.0:${PORT:-8080} server.main:app --workers ${WEB_CONCURRENCY:-1} --threads ${GUNICORN_THREADS:-8} --timeout ${GUNICORN_TIMEOUT:-120} --access-logfile -"]
