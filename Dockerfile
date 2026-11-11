FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SYRIUS_DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
# --require-hashes : chaque paquet est vérifié par son empreinte (anti-piratage)
# --only-binary    : aucun script d'installation n'est exécuté
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r requirements.txt

COPY server ./server
COPY web ./web

# Utilisateur sans privilèges
RUN useradd --create-home --uid 10001 syrius && mkdir -p /data && chown syrius:syrius /data
USER syrius

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# Le port 8000 n'est jamais exposé à Internet : seul Caddy (HTTPS) y accède.
CMD ["uvicorn", "server.app:main", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
