# Syrius sur Discord dans un conteneur (Hugging Face Space, offre gratuite « CPU basic »).
# Le Space n'a besoin QUE de ce fichier : il récupère le code du bot depuis le dépôt GitHub de Syrius.
FROM node:22.23.4-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates python3-venv wget \
    && rm -rf /var/lib/apt/lists/*

# Voix française Piper (open source), servie uniquement à l'intérieur du conteneur
RUN python3 -m venv /opt/piper && /opt/piper/bin/pip install --no-cache-dir "piper-tts[http]==1.8.0" \
    && mkdir -p /opt/voices && /opt/piper/bin/python -m piper.download_voices fr_FR-siwis-medium --data-dir /opt/voices

# Code du bot (dépendances figées, aucun script d'installation exécuté)
ARG SYRIUS_REPO=Snow17044/Syrius
ARG SYRIUS_REF=main
RUN git clone --depth 1 --branch "$SYRIUS_REF" "https://github.com/${SYRIUS_REPO}.git" /opt/syrius \
    && cd /opt/syrius/discord-bot && npm ci --omit=dev --ignore-scripts --no-audit --no-fund

WORKDIR /opt/syrius/discord-bot
ENV PORT=7860 PIPER_URL=http://127.0.0.1:5000 SYRIUS_URL=https://syriusprojet1.vercel.app
USER node
EXPOSE 7860
CMD ["./start.sh"]
