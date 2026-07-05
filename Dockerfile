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

VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["python", "-m", "ner_annotator", "--host", "0.0.0.0", "--no-open"]
CMD ["--input", "/data/input.jsonl", "--output", "/data/output.jsonl", "--types", "PER,LOC,ORG,TIME"]
