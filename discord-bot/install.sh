#!/usr/bin/env bash
# Installe « Syrius sur Discord » sur un petit serveur Debian 12 (ex. Google Cloud e2-micro, gratuit).
# Usage (dans la fenêtre SSH du serveur) :
#   curl -fsSL https://raw.githubusercontent.com/Snow17044/Syrius/main/discord-bot/install.sh | sudo bash
#
# Ce que fait ce script (et rien d'autre) :
#   - installe Node.js 22 (archive officielle, empreinte vérifiée) et la voix française Piper (open source) ;
#   - télécharge le code du bot depuis ton dépôt GitHub, sans exécuter de script d'installation des paquets ;
#   - demande tes deux clés (tapées ici, jamais affichées, gardées dans /etc/syrius-discord.env, lisibles par root) ;
#   - lance le bot et la voix comme services protégés, avec une mise à jour automatique chaque nuit.
set -euo pipefail

REPO="${SYRIUS_REPO:-Snow17044/Syrius}"
NODE_VERSION="v22.23.4"
NODE_SHA256="1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce"
PIPER_VERSION="1.8.0"
VOICE="fr_FR-siwis-medium"
BASE=/opt/syrius
ENV_FILE=/etc/syrius-discord.env

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "Lance ce script avec sudo."; exit 1; }
[ "$(uname -m)" = x86_64 ] || { echo "Serveur 64 bits (x86_64) nécessaire."; exit 1; }

say "Outils du système"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates xz-utils python3-venv >/dev/null

if ! swapon --show | grep -q .; then
  say "Mémoire de secours (1 Go)"
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

say "Node.js $NODE_VERSION (empreinte vérifiée)"
mkdir -p "$BASE"
if [ ! -x "$BASE/node/bin/node" ] || [ "$("$BASE/node/bin/node" --version)" != "$NODE_VERSION" ]; then
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/node.tar.xz" "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz"
  echo "$NODE_SHA256  $tmp/node.tar.xz" | sha256sum -c - >/dev/null || { echo "Empreinte Node.js incorrecte : arrêt."; exit 1; }
  rm -rf "$BASE/node" && mkdir -p "$BASE/node"
  tar -xJf "$tmp/node.tar.xz" -C "$BASE/node" --strip-components=1
  rm -rf "$tmp"
fi

id syrius >/dev/null 2>&1 || useradd --system --home "$BASE" --shell /usr/sbin/nologin syrius

say "Code du bot (dépôt $REPO)"
if [ -d "$BASE/repo/.git" ]; then
  git -C "$BASE/repo" fetch -q --depth 1 origin main && git -C "$BASE/repo" reset -q --hard origin/main
else
  git clone -q --depth 1 "https://github.com/$REPO.git" "$BASE/repo"
fi
cd "$BASE/repo/discord-bot"
PATH="$BASE/node/bin:$PATH" npm ci --omit=dev --ignore-scripts --no-audit --no-fund >/dev/null

say "Voix française (Piper $PIPER_VERSION)"
[ -x "$BASE/piper/bin/python" ] || python3 -m venv "$BASE/piper"
"$BASE/piper/bin/pip" install -q "piper-tts[http]==$PIPER_VERSION"
mkdir -p "$BASE/voices"
[ -f "$BASE/voices/$VOICE.onnx" ] || "$BASE/piper/bin/python" -m piper.download_voices "$VOICE" --data-dir "$BASE/voices" >/dev/null

if [ ! -f "$ENV_FILE" ]; then
  say "Tes clés (rien ne s'affiche quand tu colles : c'est normal)"
  read -r -s -p "Jeton du bot Discord : " DTOKEN </dev/tty; echo
  read -r -s -p "Clé du bot (Réglages de Syrius → Syrius sur Discord) : " BKEY </dev/tty; echo
  read -r -p "Adresse de ton Syrius [https://syriusprojet1.vercel.app] : " SURL </dev/tty
  SURL="${SURL:-https://syriusprojet1.vercel.app}"
  umask 077
  printf 'DISCORD_TOKEN=%s\nSYRIUS_BOT_KEY=%s\nSYRIUS_URL=%s\nPIPER_URL=http://127.0.0.1:5000\n' "$DTOKEN" "$BKEY" "$SURL" > "$ENV_FILE"
  unset DTOKEN BKEY
fi
chmod 600 "$ENV_FILE"
chown -R syrius:syrius "$BASE/voices"

say "Services"
cat > /etc/systemd/system/syrius-voice.service <<EOF
[Unit]
Description=Syrius - voix française (Piper)
After=network-online.target
[Service]
User=syrius
ExecStart=$BASE/piper/bin/python -m piper.http_server -m $VOICE --data-dir $BASE/voices --host 127.0.0.1 --port 5000
Restart=always
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/syrius-discord.service <<EOF
[Unit]
Description=Syrius sur Discord (salon vocal)
After=network-online.target syrius-voice.service
Wants=syrius-voice.service
[Service]
User=syrius
WorkingDirectory=$BASE/repo/discord-bot
EnvironmentFile=$ENV_FILE
ExecStart=$BASE/node/bin/node bot.js
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/syrius-update.service <<EOF
[Unit]
Description=Mise à jour de Syrius sur Discord
[Service]
Type=oneshot
ExecStart=/bin/bash -c 'git -C $BASE/repo fetch -q --depth 1 origin main && git -C $BASE/repo reset -q --hard origin/main && cd $BASE/repo/discord-bot && PATH=$BASE/node/bin:\$PATH npm ci --omit=dev --ignore-scripts --no-audit --no-fund && systemctl restart syrius-discord'
EOF

cat > /etc/systemd/system/syrius-update.timer <<EOF
[Unit]
Description=Mise à jour quotidienne de Syrius sur Discord
[Timer]
OnCalendar=*-*-* 04:20:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now syrius-voice.service syrius-discord.service syrius-update.timer >/dev/null 2>&1
systemctl restart syrius-voice.service syrius-discord.service
sleep 8

say "État"
systemctl --no-pager --lines=8 status syrius-discord.service | sed -n '1,12p' || true
echo
echo "Terminé ! Rejoins un salon vocal sur Discord : Syrius te suit et dit « Syrius est là »."
echo "Journal en direct : sudo journalctl -fu syrius-discord"
echo "Changer les clés : sudo nano $ENV_FILE  puis  sudo systemctl restart syrius-discord"
