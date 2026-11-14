#!/bin/sh
# Démarrage dans un conteneur (Hugging Face Space) : la voix française en local, puis le bot.
set -e
/opt/piper/bin/python -m piper.http_server -m fr_FR-siwis-medium --data-dir /opt/voices --host 127.0.0.1 --port 5000 &
for i in $(seq 1 30); do
  if wget -q -O /dev/null --post-data='{"text":"ok"}' --header='Content-Type: application/json' http://127.0.0.1:5000/synthesize; then break; fi
  sleep 2
done
exec node bot.js
