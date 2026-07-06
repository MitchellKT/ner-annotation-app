# Kubernetes deployment

Multi-user NER annotator: annotators identify by name, upload their own
`.jsonl`, and annotate concurrently. State is per-user files on a persistent
volume; the server keeps one in-memory `Store` per active user.

## Architecture at a glance

- **Deployment** — single replica, `Recreate` strategy. State is in-memory +
  local files on a `ReadWriteOnce` volume, so exactly one pod owns the data.
  This suits an internal tool with a handful of concurrent annotators. To scale
  out, migrate persistence to Postgres (the per-user API isolation is already in
  place) — that is the only piece that assumes a single writer.
- **PVC** (`/data`) — holds `users/<slug>/{input,output,...}.jsonl` per user.
- **Secret** — `SESSION_SECRET` signs the session cookie (identity survives
  restarts; can't be forged).
- **ConfigMap** — data dir, default entity types, HTTPS cookie flag.
- **Service + Ingress** — ClusterIP fronted by an optional TLS Ingress.

## Deploy

```bash
# 1) Build and push the image
docker build -t <registry>/ner-annotator:0.2.0 .
docker push <registry>/ner-annotator:0.2.0
# then set it in k8s/kustomization.yaml (images:) or edit deployment.yaml

# 2) Create the signing secret (do NOT use the placeholder in secret.yaml)
kubectl create secret generic ner-annotator-secrets \
  --from-literal=SESSION_SECRET="$(openssl rand -base64 48)"

# 3) Apply the rest (kustomization references secret.yaml; skip it once the
#    secret above exists, or let apply update it — your choice)
kubectl apply -k k8s/

# 4) Reach it
kubectl port-forward svc/ner-annotator 8000:80   # http://localhost:8000
# ...or configure the Ingress host in ingress.yaml and browse to it over TLS
```

## Notes

- **Uploads**: capped at 25 MB in the app; the Ingress `proxy-body-size` is set
  to 32 MB to stay above it. Raise both together if you need larger files.
- **Backups**: everything lives under the PVC — snapshot it to back up all
  annotations. Each user's result is also downloadable in-app ("⭳ output").
- **Cookie security**: `SESSION_COOKIE_SECURE=1` in the ConfigMap marks the
  cookie Secure; keep it on when serving over HTTPS, turn it off for plain-HTTP
  port-forward testing.
