# syntax=docker/dockerfile:1

# ── Frontend build ────────────────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Backend runtime ───────────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./backend/
COPY backend/ner_annotator ./backend/ner_annotator
RUN pip install --no-cache-dir ./backend

COPY --from=frontend /app/frontend/dist ./frontend/dist

# Run as a non-root user; /data is a mounted volume it must be able to write.
RUN useradd --uid 10001 --create-home app \
    && mkdir -p /data \
    && chown -R app:app /data
USER app

# Multi-user server: each annotator identifies by name and uploads their own
# file into a per-user workspace under $DATA_DIR. Configure via env / k8s.
ENV DATA_DIR=/data \
    DEFAULT_TYPES=PER,LOC,ORG,TIME \
    PORT=8000

VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["python", "-m", "ner_annotator", "--host", "0.0.0.0", "--no-open"]
