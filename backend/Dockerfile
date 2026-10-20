# ─────────────────────────────────────────────────────────────────────────────
# Backend Dockerfile
# Python 3.12 slim — installs dependencies and runs the FastAPI app with
# uvicorn.  No dev tools, no cache, minimal image size.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Prevents Python from writing .pyc files and buffers stdout/stderr so log
# lines appear immediately in docker logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── System packages ───────────────────────────────────────────────────────────
# gosu: privilege-drop helper used by docker-entrypoint.sh to switch from the
# temporary root context (needed to chown volume mounts) to appuser before
# exec-ing uvicorn.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu \
 && rm -rf /var/lib/apt/lists/*

# ── Create a non-root user ────────────────────────────────────────────────────
# Running as root inside a container is a security risk.  The entrypoint
# script chowns the named volumes then drops to this user via gosu.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# ── Install dependencies ──────────────────────────────────────────────────────
# Copy requirements first so Docker can cache this layer — the layer is only
# rebuilt when requirements.txt changes, not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore --upgrade pip \
 && pip install --no-cache-dir --root-user-action=ignore -r requirements.txt

# ── Copy application source ───────────────────────────────────────────────────
COPY app/ ./app/

# ── Copy & register the entrypoint script ────────────────────────────────────
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# ── Pre-create writable directories (ownership fixed at runtime by entrypoint) ─
RUN mkdir -p /app/pdf_reports /app/data \
 && chown -R appuser:appgroup /app

# ── Expose ────────────────────────────────────────────────────────────────────
EXPOSE 8000

# The entrypoint runs as root just long enough to chown the named-volume mount
# points, then execs the CMD as appuser via gosu.
ENTRYPOINT ["docker-entrypoint.sh"]

# --host 0.0.0.0  — required so the port is reachable from outside the container.
# --proxy-headers — parse X-Forwarded-For / X-Forwarded-Proto from the nginx
#                   reverse proxy in front of the container.
# --forwarded-allow-ips '172.16.0.0/12' — trust proxy headers only from the
#                   Docker-internal network (RFC 1918 172.16/12 range covers
#                   all default Docker bridge subnets).  Override via
#                   UVICORN_FORWARDED_ALLOW_IPS env var if your network differs.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "172.16.0.0/12"]
