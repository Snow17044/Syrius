"""Vitesse en ligne : outils choisis selon la demande, IA rapides d'abord, IA lente ou en panne reléguée."""
import json
import time

from server import llm
from server.config import Config
from server.llm import ChatClient, Provider
from server.tools import registry


def P(name):
    return Provider(name, name, "http://x", "m", "k")


def names(tools):
    return {t["function"]["name"] for t in tools}


def tools_for(text, **kw):
    return names(registry.select_tools(registry.build_tools(Config(), {"internet": True}), text, **kw))


def test_discussion_simple_envoie_peu_d_outils():
    t = tools_for("Pourquoi la mer est salée ?")
    assert "web_search" in t and "remember" in t and "get_weather" in t  # le cœur reste
    assert not any(n.startswith("phone_") for n in t) and "show_diagram" not in t and "show_model" not in t
    full = registry.build_tools(Config(), {"internet": True})
    assert len(json.dumps([x for x in full if x["function"]["name"] in t])) < 0.55 * len(json.dumps(full))


def test_les_groupes_reviennent_quand_la_demande_les_evoque():
    assert "phone_timer" in tools_for("Mets un minuteur de 5 minutes")
    assert "phone_reminder" in tools_for("Rappelle-moi d'appeler Julie demain à 18h")
    assert "phone_image" in tools_for("Dessine un chat")
    assert "show_diagram" in tools_for("Fais-moi un schéma pour mon projet")
    assert "show_model" in tools_for("Montre-moi une maquette 3D d'un phare")
    assert "phone_sms" in tools_for("Préviens Julie que j'arrive")
    assert "scan_site" not in tools_for("Scanne mon site monsite.fr")  # le scanner est dans Syrius Code (Aurora)
    aurore = registry.build_tools(Config(), {"internet": True}, "aurore")
    assert "scan_site" in names(registry.select_tools(aurore, "Scanne mon site monsite.fr"))
    assert "scan_site" not in names(registry.select_tools(aurore, "Raconte une blague"))
    assert "show_dashboard" in names(registry.select_tools(aurore, "Voici mes ventes : 120, 340, 280. Fais un graphique"))

def test_suite_d_une_action_garde_tous_les_outils():
    assert "phone_timer" in tools_for("Oui vas-y", keep_all=True)
    # « oui » après une proposition d'action : la fin de la réponse précédente compte
    assert "phone_timer" in tools_for("Oui vas-y " + "Je peux te lancer un minuteur de 10 minutes ?")


def test_ia_rapides_avant_openrouter():
    c = ChatClient([P("openrouter"), P("mistral"), P("groq")])
    assert [p.name for p in c.ordered()] == ["mistral", "groq", "openrouter"]
    assert [p.name for p in c.ordered(fast=False)] == ["openrouter", "mistral", "groq"]  # « réflexion poussée » : l'ancien ordre


def test_ia_lente_ou_en_panne_passe_derriere():
    c = ChatClient([P("mistral"), P("groq"), P("gemini")])
    c._record("mistral", 12.0)  # 12 s avant le premier mot
    assert [p.name for p in c.ordered()][0] == "groq"
    c._fail("groq")
    assert [p.name for p in c.ordered()] == ["gemini", "mistral", "groq"]
    c.stats["groq"]["fail_at"] = time.time() - llm.FAIL_MEMORY - 1  # l'échec est oublié après 5 minutes
    assert [p.name for p in c.ordered()][0] == "groq"


def test_delai_maximal_court():
    assert ChatClient([P("a")]).timeout <= 30
