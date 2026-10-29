"""Acces au modele de langue d'Amont : local d'abord (Ollama aujourd'hui, serveur interne a RTX 5090 demain).

Aucun document ne sort de Castignac : le modele tourne sur une machine de l'entreprise (ou, pour les
tests, sur le serveur perso). Trois facons de parler au modele, choisies par AMONT_IA_API :

  ollama     API native d'Ollama (/api/chat). Defaut. Permet de fixer la taille de contexte (num_ctx,
             sinon Ollama tronque a 2 a 4k jetons sans prevenir), le format JSON et de couper le
             « raisonnement » des modeles qui en ont un (qwen3).
  openai     API compatible OpenAI (/v1/chat/completions) : vLLM, llama.cpp server, LM Studio...
             C'est le choix probable sur le serveur a RTX 5090 si l'on y sert le modele avec vLLM.
  anthropic  API Claude, conservee pour memoire (cle ANTHROPIC_API_KEY). A n'utiliser que si des
             documents peuvent sortir de l'entreprise.

Variables (ou section "ia" de amont_config.json, les variables l'emportent) :
  AMONT_IA_URL              ex. http://host.docker.internal:11434 (Ollama sur la machine hote du conteneur)
  AMONT_IA_API              ollama | openai | anthropic            (defaut : ollama)
  AMONT_IA_MODELE           modele texte, ex. qwen3:8b
  AMONT_IA_MODELE_VISION    modele qui lit les images (scans, plans), ex. gemma3:12b ; vide = pas de vision
  AMONT_IA_CONTEXTE         taille de contexte en jetons (defaut 16384)
  AMONT_IA_DELAI            secondes par appel (defaut 600 : un 8B sur processeur est lent)
  AMONT_IA_CLE              jeton d'API si le serveur en demande un (vLLM --api-key)
  AMONT_IA=non              coupe l'IA, les regles seules s'appliquent

Bibliotheque standard seulement.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

from . import regles


class ErreurIA(Exception):
    pass


def _conf(cle: str, defaut=None):
    env = os.environ.get("AMONT_IA_" + cle.upper())
    if env not in (None, ""):
        return env
    return (regles.CONFIG.get("ia") or {}).get(cle, defaut)


def reglages() -> dict:
    api = (_conf("api", "ollama") or "ollama").lower()
    url = (_conf("url") or "").rstrip("/")
    if api == "anthropic":
        url = url or "https://api.anthropic.com"
    return {
        "api": api,
        "url": url,
        "modele": _conf("modele", "claude-sonnet-4-5" if api == "anthropic" else ""),
        "modele_vision": _conf("modele_vision", ""),
        "contexte": int(_conf("contexte", 16384)),
        "delai": int(_conf("delai", 600)),
        "cle": _conf("cle") or (os.environ.get("ANTHROPIC_API_KEY") if api == "anthropic" else None),
    }


def disponible() -> bool:
    if os.environ.get("AMONT_IA", "").lower() == "non":
        return False
    r = reglages()
    if r["api"] == "anthropic":
        return bool(r["cle"] and r["modele"])
    return bool(r["url"] and r["modele"])


def vision_disponible() -> bool:
    r = reglages()
    return disponible() and (bool(r["modele_vision"]) or r["api"] == "anthropic")


def description() -> str:
    if not disponible():
        return ""
    r = reglages()
    lieu = {"ollama": "Ollama", "openai": "serveur local", "anthropic": "API Claude"}.get(r["api"], r["api"])
    t = f"{r['modele']} ({lieu})"
    if r["modele_vision"] and r["modele_vision"] != r["modele"]:
        t += f", vision : {r['modele_vision']}"
    return t


# --------------------------------------------------------------------------- transport
def _post(url: str, corps: dict, delai: int, en_tetes: dict | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    h.update(en_tetes or {})
    req = urllib.request.Request(url, data=json.dumps(corps).encode("utf-8"), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if e.code == 404 and "model" in detail.lower():
            raise ErreurIA(f"modèle absent du serveur : {corps.get('model')} ({detail})") from None
        raise ErreurIA(f"le serveur du modèle a répondu {e.code} : {detail}") from None
    except (TimeoutError, OSError) as e:
        raise ErreurIA(f"serveur du modèle injoignable ou trop lent ({type(e).__name__} : {e}) à {url}") from None


def _get(url: str, delai: int = 10) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=delai) as r:
            return json.loads(r.read())
    except (OSError, ValueError) as e:
        raise ErreurIA(f"serveur du modèle injoignable ({type(e).__name__} : {e}) à {url}") from None


_PENSEE = re.compile(r"<think>.*?</think>", re.S)


def demander(consigne: str, images: list[bytes] | None = None, json_attendu: bool = True, schema: dict | None = None,
             max_jetons: int = 4000, temperature: float = 0.1) -> tuple[str, dict]:
    """Envoie une consigne (et des images PNG/JPEG) au modele. Retourne (reponse texte, statistiques)."""
    if not disponible():
        raise ErreurIA("IA non configurée (AMONT_IA_URL et AMONT_IA_MODELE)")
    r = reglages()
    vision = bool(images)
    modele = (r["modele_vision"] or r["modele"]) if vision else r["modele"]
    if vision and not vision_disponible():
        raise ErreurIA("aucun modèle de vision configuré (AMONT_IA_MODELE_VISION)")
    t0 = time.time()
    if r["api"] == "ollama":
        msg = {"role": "user", "content": consigne}
        if images:
            msg["images"] = [base64.b64encode(i).decode() for i in images]
        corps = {"model": modele, "messages": [msg], "stream": False,
                 "options": {"num_ctx": r["contexte"], "temperature": temperature, "num_predict": max_jetons}}
        if re.search(r"qwen3|deepseek-r1|magistral", modele, re.I):
            corps["think"] = False  # raisonnement inutile ici, et il mange le budget de jetons
        if json_attendu:
            corps["format"] = schema or "json"
        try:
            rep = _post(r["url"] + "/api/chat", corps, r["delai"])
        except ErreurIA as e:
            if "think" not in corps or "think" not in str(e).lower():
                raise
            corps.pop("think")  # Ollama ancien ou modele sans mode raisonnement
            rep = _post(r["url"] + "/api/chat", corps, r["delai"])
        texte = (rep.get("message") or {}).get("content") or ""
        stats = {"modele": modele, "jetons_entree": rep.get("prompt_eval_count"), "jetons_sortie": rep.get("eval_count")}
    elif r["api"] == "openai":
        contenu: list | str = consigne
        if images:
            contenu = [{"type": "text", "text": consigne}] + [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(i).decode()}} for i in images]
        corps = {"model": modele, "messages": [{"role": "user", "content": contenu}], "temperature": temperature,
                 "max_tokens": max_jetons}
        if json_attendu:
            corps["response_format"] = ({"type": "json_schema", "json_schema": {"name": "reponse", "schema": schema}}
                                        if schema else {"type": "json_object"})
        base = r["url"] if r["url"].endswith("/v1") else r["url"] + "/v1"
        rep = _post(base + "/chat/completions", corps, r["delai"], {"Authorization": f"Bearer {r['cle']}"} if r["cle"] else None)
        texte = ((rep.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        u = rep.get("usage") or {}
        stats = {"modele": modele, "jetons_entree": u.get("prompt_tokens"), "jetons_sortie": u.get("completion_tokens")}
    elif r["api"] == "anthropic":
        contenu = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(i).decode()}}
                   for i in images or []] + [{"type": "text", "text": consigne}]
        rep = _post(r["url"] + "/v1/messages", {"model": modele, "max_tokens": max_jetons, "messages": [{"role": "user", "content": contenu}]},
                    r["delai"], {"x-api-key": r["cle"], "anthropic-version": "2023-06-01"})
        texte = "".join(b.get("text", "") for b in rep.get("content") or [])
        u = rep.get("usage") or {}
        stats = {"modele": modele, "jetons_entree": u.get("input_tokens"), "jetons_sortie": u.get("output_tokens")}
    else:
        raise ErreurIA(f"AMONT_IA_API inconnu : {r['api']}")
    stats["secondes"] = round(time.time() - t0, 1)
    return _PENSEE.sub("", texte).strip(), stats


def demander_json(consigne: str, images: list[bytes] | None = None, schema: dict | None = None, **kw):
    """Comme demander(), reponse decodee en JSON. Tolere un texte autour ou des balises ```json."""
    texte, stats = demander(consigne, images, True, schema, **kw)
    return lire_json(texte), stats


def lire_json(texte: str):
    t = texte.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        pass
    for motif in (r"\{.*\}", r"\[.*\]"):
        m = re.search(motif, t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                continue
    raise ErreurIA("réponse du modèle illisible (JSON attendu) : " + t[:200])


def etat() -> dict:
    """Diagnostic pour le site et le script de test : serveur joignable, modeles presents."""
    r = reglages()
    out = {"configuree": disponible(), "api": r["api"], "url": r["url"], "modele": r["modele"],
           "modele_vision": r["modele_vision"], "joignable": None, "modeles_serveur": [], "manquants": [], "erreur": None}
    if not out["configuree"] or r["api"] == "anthropic":
        return out
    try:
        if r["api"] == "ollama":
            noms = [m.get("name") or m.get("model") for m in _get(r["url"] + "/api/tags").get("models", [])]
        else:
            base = r["url"] if r["url"].endswith("/v1") else r["url"] + "/v1"
            noms = [m.get("id") for m in _get(base + "/models").get("data", [])]
        out["joignable"] = True
        out["modeles_serveur"] = noms
        for m in {r["modele"], r["modele_vision"]} - {""}:
            if not any(n == m or n == m + ":latest" or n.split(":")[0] == m for n in noms):
                out["manquants"].append(m)
    except ErreurIA as e:
        out["joignable"] = False
        out["erreur"] = str(e)
    return out
