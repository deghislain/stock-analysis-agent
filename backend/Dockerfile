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

# ── Create a non-root user ────────────────────────────────────────────────────
# Running as root inside a container is a security risk.  All subsequent
# commands and the final process run as this dedicated user.
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

# ── Create the PDF output directory and hand ownership to appuser ─────────────
# /app/pdf_reports is the default path used by Docker Compose
# (PDF_OUTPUT_DIR is overridden to /app/pdf_reports in docker-compose.yml).
# main.py also calls os.makedirs at startup so the directory is always present;
# we create it here so the volume mount inherits the correct ownership.
RUN mkdir -p /app/pdf_reports /app/data \
 && chown -R appuser:appgroup /app

USER appuser

# ── Expose & run ─────────────────────────────────────────────────────────────
EXPOSE 8000

# --host 0.0.0.0  — required so the port is reachable from outside the container.
# --proxy-headers — parse X-Forwarded-For / X-Forwarded-Proto from the nginx
#                   reverse proxy in front of the container.
# --forwarded-allow-ips '*' — trust those headers from any upstream address
#                             (safe because only the Docker-internal nginx can
#                             reach this container).
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
