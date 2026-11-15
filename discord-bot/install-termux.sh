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

TOKEN_RE='[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{20,}'
KEY_RE='syb_[A-Za-z0-9_-]{20,}'
valid_env() {  # le fichier des clés est-il complet et propre ?
  [ -f "$ENV_FILE" ] && grep -qE "^DISCORD_TOKEN=${TOKEN_RE}\$" "$ENV_FILE" \
    && grep -qE "^SYRIUS_BOT_KEY=${KEY_RE}\$" "$ENV_FILE" && grep -qE '^SYRIUS_URL=https://[A-Za-z0-9.-]+/?$' "$ENV_FILE"
}
if ! valid_env; then
  say "Tes clés (rien ne s'affiche quand tu colles : c'est normal)"
  while :; do  # on garde seulement le jeton, même si du texte en trop a été collé autour
    read -r -s -p "Jeton du bot Discord : " RAW </dev/tty; echo
    DTOKEN=$(printf '%s' "$RAW" | grep -oE "$TOKEN_RE" | head -1 || true)
    [ -n "$DTOKEN" ] && break
    echo "Ce n'est pas un jeton de bot Discord. Recopie-le (portail développeur → Bot → Reset Token → Copy)."
  done
  while :; do
    read -r -s -p "Clé du bot (Réglages de Syrius → Syrius sur Discord) : " RAW </dev/tty; echo
    BKEY=$(printf '%s' "$RAW" | grep -oE "$KEY_RE" | head -1 || true)
    [ -n "$BKEY" ] && break
    echo "La clé du bot commence par syb_ : recopie-la depuis les réglages de Syrius."
  done
  read -r -p "Adresse de ton Syrius [https://syriusprojet1.vercel.app] : " SURL </dev/tty
  SURL=$(printf '%s' "${SURL:-https://syriusprojet1.vercel.app}" | grep -oE 'https://[A-Za-z0-9.-]+' | head -1 || true)
  SURL="${SURL:-https://syriusprojet1.vercel.app}"
  umask 077
  printf 'DISCORD_TOKEN=%s\nSYRIUS_BOT_KEY=%s\nSYRIUS_URL=%s\nTTS=espeak\n' "$DTOKEN" "$BKEY" "$SURL" > "$ENV_FILE"
  unset RAW DTOKEN BKEY
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
  node bot.js; code=\$?
  if [ "\$code" = 2 ]; then echo "Clés invalides : tape  syrius-discord-cles  pour les corriger."; exit 2; fi
  echo "Syrius s'est arrêté : redémarrage dans 10 s (Ctrl+C pour quitter)…"
  sleep 10
done
EOF
chmod 700 "$PREFIX/bin/syrius-discord"
cat > "$PREFIX/bin/syrius-discord-cles" <<FIN
#!$PREFIX/bin/bash
# Efface tes clés et les redemande (par exemple après « Reset Token » sur Discord).
rm -f "$ENV_FILE"
curl -fsSL "https://raw.githubusercontent.com/$REPO/main/discord-bot/install-termux.sh" | bash
FIN
chmod 700 "$PREFIX/bin/syrius-discord-cles"

say "C'est prêt !"
echo "Lancement… (laisse Termux ouvert en arrière-plan, téléphone branché)"
echo "Plus tard, pour le relancer : ouvre Termux et tape  syrius-discord"
echo "Pour changer tes clés : tape  syrius-discord-cles"
exec "$PREFIX/bin/syrius-discord"
