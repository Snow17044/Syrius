#!/usr/bin/env bash
# Lance tous les contrôles de sécurité de Syrius.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== 1. Tests (fonctionnement + sécurité) =="
python -m pytest -q
echo "== 2. Analyse du code (bandit) =="
bandit -q -r server
echo "== 3. Failles connues dans les dépendances (pip-audit / base OSV) =="
pip-audit -r requirements.txt --require-hashes
echo "== 4. Aucun secret dans le dépôt =="
if git ls-files | grep -E '(^|/)\.env$'; then echo "ERREUR : .env est suivi par git"; exit 1; fi
if git grep -nE 'sk-ant-[A-Za-z0-9_-]{20,}' -- ':!scripts/security_check.sh'; then echo "ERREUR : clé API dans le code"; exit 1; fi
echo "✅ Tous les contrôles sont passés."
