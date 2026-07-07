# PalestrIX core API / worker image (demo & evaluation stack).
# Build context is the REPOSITORY ROOT so the reference plugin installs too:
#   docker build -f backend/Dockerfile .

# The Docker lab adapter drives the `docker` CLI. The static binary is copied
# from the official CLI image (no package manager needed); it stays inert
# unless PALESTRIX_DOCKER_ENABLED=true and the host daemon socket is mounted
# (docker-compose.labs.yml).
FROM docker:cli AS dockercli

FROM python:3.11-slim
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /srv
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# The entry-point-discovered reference plugin (plugin console demo).
COPY plugins/palestrix-provider-demo plugins/palestrix-provider-demo
RUN pip install --no-cache-dir ./plugins/palestrix-provider-demo

COPY backend/palestrix backend/palestrix

WORKDIR /srv/backend
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=30 CMD \
    python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "palestrix.main:app", "--host", "0.0.0.0", "--port", "8000"]
