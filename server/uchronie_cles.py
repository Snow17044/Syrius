"""Bouton « Envoyer mes clés d'IA au site Uchronie » (réservé au propriétaire, dans la page Uchronie de Syrius).

Vercel cache les clés « sensibles » à tout le monde : on ne peut pas les recopier d'un projet à l'autre à la main sans
les retaper. Syrius, lui, les connaît pendant qu'il tourne. Ce bouton les envoie donc directement de Syrius vers le
projet Vercel « uchronie » (avec la clé VERCEL_TOKEN de Syrius), toujours en « sensibles », puis relance le site.
Les valeurs ne sont jamais renvoyées à l'application, ni écrites dans les journaux : seuls les NOMS sont affichés.
"""
from __future__ import annotations

from .publish import PublishError, _call

PROJECT = "uchronie"


def ai_keys(cfg) -> dict[str, str]:
    """Clés d'IA de ce Syrius (seulement celles qui existent)."""
    keys = {
        "GROQ_API_KEY": cfg.groq_api_key, "GEMINI_API_KEY": cfg.gemini_api_key,
        "MISTRAL_API_KEY": cfg.mistral_api_key, "OPENROUTER_API_KEY": cfg.openrouter_api_key,
        "CLOUDFLARE_API_TOKEN": cfg.cloudflare_api_key, "CLOUDFLARE_ACCOUNT_ID": cfg.cloudflare_account_id,
        "GITHUB_MODELS_TOKEN": cfg.github_models_token,
    }
    return {k: v.strip() for k, v in keys.items() if isinstance(v, str) and v.strip()}


def send(cfg) -> dict:
    """Copie les clés vers le projet « uchronie » et le relance. Renvoie {"sent": [noms], "redeployed": bool}."""
    token, team = cfg.vercel_token, cfg.vercel_team_id
    if not token:
        raise PublishError("La clé VERCEL_TOKEN n'est pas configurée dans le Vercel de Syrius.")
    keys = ai_keys(cfg)
    if not keys:
        raise PublishError("Ce Syrius n'a aucune clé d'IA à envoyer.")
    code, project = _call(token, "GET", f"/v9/projects/{PROJECT}", team)
    if code == 404:
        raise PublishError("Le projet Vercel « uchronie » est introuvable.")
    if code != 200 or not project.get("id"):
        raise PublishError(f"Vercel refuse l'accès au projet « uchronie » ({code}).")
    pid = project["id"]
    sent = []
    for name, value in keys.items():
        code, _ = _call(token, "POST", f"/v10/projects/{pid}/env?upsert=true", team,
                        {"key": name, "value": value, "type": "sensitive", "target": ["production"]})
        if code not in (200, 201):
            raise PublishError(f"Vercel a refusé d'enregistrer {name} ({code}). Clés déjà envoyées : "
                               f"{', '.join(sent) or 'aucune'}.")
        sent.append(name)
    link = project.get("link") or {}
    redeployed = False
    if link.get("type") == "github" and link.get("repoId"):
        code, _ = _call(token, "POST", "/v13/deployments", team, {
            "name": PROJECT, "project": pid, "target": "production",
            "gitSource": {"type": "github", "repoId": link["repoId"], "ref": link.get("productionBranch") or "main"}})
        redeployed = code in (200, 201)
    return {"sent": sent, "redeployed": redeployed}
