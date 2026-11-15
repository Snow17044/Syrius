#!/data/data/com.termux/files/usr/bin/bash
# Installe « Syrius sur Discord » sur ton téléphone Android, dans Termux (gratuit, sans serveur).
# Usage (dans Termux) :
#   curl -fsSL https://raw.githubusercontent.com/Snow17044/Syrius/main/discord-bot/install-termux.sh | bash
#
# Ce que fait ce script (et rien d'autre) :
#   - installe Node.js, git et la voix eSpeak depuis les paquets officiels de Termux ;
#   - télécharge le code du bot depuis ton dépôt GitHub (aucun script d'installation de paquet exécuté) ;
#   - demande tes deux clés (jamais affichées, gardées dans ~/.syrius-discord.env, lisible par toi seul) ;
#   - crée la commande « syrius-discord » qui lance le bot (et le relance s'il s'arrête).
set -euo pipefail

REPO="${SYRIUS_REPO:-Snow17044/Syrius}"
DIR="$HOME/syrius"
ENV_FILE="$HOME/.syrius-discord.env"
say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

[ -n "${PREFIX:-}" ] && [ -d "$PREFIX" ] || { echo "Ce script est prévu pour l'application Termux."; exit 1; }

say "Outils (Node.js, git, voix eSpeak)"
yes | pkg update >/dev/null 2>&1 || true
pkg install -y nodejs git espeak >/dev/null
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if (a<22||(a===22&&b<12)) { console.error("Node.js 22.12 ou plus est nécessaire"); process.exit(1) }'

say "Code du bot (dépôt $REPO)"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q --depth 1 origin main && git -C "$DIR" reset -q --hard origin/main
else
  git clone -q --depth 1 "https://github.com/$REPO.git" "$DIR"
fi
(cd "$DIR/discord-bot" && npm ci --omit=dev --ignore-scripts --no-audit --no-fund >/dev/null)

if [ ! -f "$ENV_FILE" ]; then
  say "Tes clés (rien ne s'affiche quand tu colles : c'est normal)"
  read -r -s -p "Jeton du bot Discord : " DTOKEN </dev/tty; echo
  read -r -s -p "Clé du bot (Réglages de Syrius → Syrius sur Discord) : " BKEY </dev/tty; echo
  read -r -p "Adresse de ton Syrius [https://syriusprojet1.vercel.app] : " SURL </dev/tty
  SURL="${SURL:-https://syriusprojet1.vercel.app}"
  umask 077
  printf 'DISCORD_TOKEN=%s\nSYRIUS_BOT_KEY=%s\nSYRIUS_URL=%s\nTTS=espeak\n' "$DTOKEN" "$BKEY" "$SURL" > "$ENV_FILE"
  unset DTOKEN BKEY
fi
chmod 600 "$ENV_FILE"

say "Commande « syrius-discord »"
cat > "$PREFIX/bin/syrius-discord" <<EOF
#!$PREFIX/bin/bash
# Lance Syrius sur Discord (mise à jour d'abord), et le relance s'il s'arrête. Ctrl+C pour arrêter.
termux-wake-lock 2>/dev/null || true
git -C "$DIR" fetch -q --depth 1 origin main 2>/dev/null && git -C "$DIR" reset -q --hard origin/main \\
  && (cd "$DIR/discord-bot" && npm ci --omit=dev --ignore-scripts --no-audit --no-fund >/dev/null 2>&1) || true
cd "$DIR/discord-bot"
while true; do
  set -a; . "$ENV_FILE"; set +a
  node bot.js || true
  echo "Syrius s'est arrêté : redémarrage dans 10 s (Ctrl+C pour quitter)…"
  sleep 10
done
EOF
chmod 700 "$PREFIX/bin/syrius-discord"

say "C'est prêt !"
echo "Lancement… (laisse Termux ouvert en arrière-plan, téléphone branché)"
echo "Plus tard, pour le relancer : ouvre Termux et tape  syrius-discord"
exec "$PREFIX/bin/syrius-discord"
