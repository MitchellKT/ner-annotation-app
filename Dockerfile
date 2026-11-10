# syntax=docker/dockerfile:1
#
# App image: starts from the prebuilt base image (see Dockerfile.base), copies
# the repo, builds the frontend and runs the app. Needs no network access, so
# it builds quickly inside an on-prem / air-gapped environment.
#
#   docker build --build-arg BASE_IMAGE=<registry>/ner-annotator-base:<tag> -t ner-annotator .

ARG BASE_IMAGE=ner-annotator-base:latest
FROM ${BASE_IMAGE}

WORKDIR /app
COPY . .

# Backend: run straight from source; its dependencies are in the base image.
ENV PYTHONPATH=/app/backend

# Frontend: node_modules come from the base image.
RUN cd frontend && npm run build

VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["python", "-m", "ner_annotator", "--host", "0.0.0.0", "--no-open", "--static", "/app/frontend/dist"]
CMD ["--input", "/data/input.jsonl", "--output", "/data/output.jsonl", "--types", "PER,LOC,ORG,TIME"]
