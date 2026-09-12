# ─────────────────────────────────────────────────────────────────────────────
# Backend Dockerfile
# Python 3.12 slim — installs dependencies and runs the FastAPI app with
# uvicorn.  No dev tools, no cache, minimal image size.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS base

# Prevents Python from writing .pyc files and buffers stdout/stderr so log
# lines appear immediately in docker logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── Install dependencies ──────────────────────────────────────────────────────
# Copy requirements first so Docker can cache this layer — the layer is only
# rebuilt when requirements.txt changes, not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Copy application source ───────────────────────────────────────────────────
COPY app/ ./app/

# ── Create the PDF output directory at image build time ──────────────────────
# /app/pdf_reports is the path used when running via Docker Compose
# (PDF_OUTPUT_DIR is overridden to /app/pdf_reports in docker-compose.yml).
# /tmp/stock_reports is the bare-metal default from config.py.
# Both are created so the app starts cleanly in either environment.
RUN mkdir -p /app/pdf_reports /tmp/stock_reports

# ── Expose & run ─────────────────────────────────────────────────────────────
EXPOSE 8000

# --host 0.0.0.0 is required so the port is reachable from outside the
# container.  --forwarded-allow-ips '*' trusts X-Forwarded-* headers from the
# nginx reverse proxy in production.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--forwarded-allow-ips", "*"]
