"""Releve de la boite Outlook (Microsoft 365) vers les echanges d'Amont. Lecture seule.

Chaque message echange avec RTE, Enedis, GRDF ou NaTran est telecharge en .eml (MIME complet, pieces jointes
comprises) et depose sur /api/echanges/eml : Amont devine la demande, clot les attentes de reponse, range et lit
les etudes RTE, et ignore les doublons (identifiant du message). Rien n'est envoye, deplace ni supprime dans Outlook.

Un message n'est depose que s'il a un correspondant externe ET que (a) ce correspondant est dans un domaine suivi
(rte-france.com, enedis.fr, grdf.fr, natran, grtgaz) ou (b) l'objet ou l'apercu contient un code de demande, un
numero d'etude ou un numero de dossier connu d'Amont. Les echanges purement internes sont ignores.

Installation, une fois par poste :  pip install msal
Configuration : bloc "outlook" de amont_config.json (voir 2026_10_29_amont_releve_outlook.md) :
    {"outlook": {"tenant_id": "...", "client_id": "...", "amont_url": "https://amont.arinaudo.fr"}}
Premiere connexion : le script affiche un code a saisir sur https://microsoft.com/devicelogin ; ensuite le jeton se
renouvelle seul (cache dans %LOCALAPPDATA%\\AmontOutlook).

Usage :
    python 2026_10_29_amont_releve_outlook.py --simulation          # liste ce qui serait depose, ne depose rien
    python 2026_10_29_amont_releve_outlook.py                       # un passage
    python 2026_10_29_amont_releve_outlook.py --boucle 10           # un passage toutes les 10 minutes
    python 2026_10_29_amont_releve_outlook.py --depuis 90           # remonte 90 jours (defaut 30)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

GRAPH = "https://graph.microsoft.com/v1.0"
PORTEE = ["Mail.Read"]
DOMAINES_DEFAUT = ["rte-france.com", "enedis.fr", "grdf.fr", "natrangroupe.com", "natran.com", "grtgaz.com"]
DOSSIERS_COURRIER = ["inbox", "sentitems"]
TAILLE_MAX = 30 * 1024 * 1024  # limite du depot .eml d'Amont
DOSSIER = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share")) / "AmontOutlook"
RACINE = Path(__file__).resolve().parent


# ------------------------------------------------------------------ configuration
def charger_config(chemin: Path | None = None) -> dict:
    chemin = chemin or Path(os.environ.get("AMONT_CONFIG", RACINE / "amont_config.json"))
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        brut = {}
    cfg = dict(brut.get("outlook") or {})
    cfg.setdefault("amont_url", os.environ.get("AMONT_URL", "http://localhost:8000"))
    cfg.setdefault("domaines", DOMAINES_DEFAUT)
    cfg.setdefault("depuis_jours", 30)
    # domaines de la societe : leurs messages ne comptent pas comme un correspondant externe
    internes = {a.split("@")[-1].lower() for a in (brut.get("mes_adresses") or []) if "@" in a}
    cfg["internes"] = sorted(set(cfg.get("internes") or []) | internes | {"castignac.com"})
    cfg["domaines"] = [d.lower() for d in cfg["domaines"]]
    cfg["auteur"] = cfg.get("auteur") or f"outlook:{os.environ.get('USERNAME') or os.environ.get('USER') or 'poste'}"
    return cfg


# ------------------------------------------------------------------ choix des messages
def adresses(msg: dict) -> list[str]:
    """Toutes les adresses d'un message Graph : expediteur, destinataires, copie (minuscules)."""
    out = []
    for cle in ("from", "sender"):
        a = ((msg.get(cle) or {}).get("emailAddress") or {}).get("address")
        if a:
            out.append(a.lower())
    for cle in ("toRecipients", "ccRecipients"):
        for r in msg.get(cle) or []:
            a = (r.get("emailAddress") or {}).get("address")
            if a:
                out.append(a.lower())
    return list(dict.fromkeys(out))


def codes_demandes(demandes: list[dict]) -> list[str]:
    """Codes reconnus dans un objet : id de demande, numero d'etude, numero de dossier (4 caracteres au moins)."""
    codes = set()
    for d in demandes:
        for cle in ("id", "num_etude", "ref_dossier", "num_ptf"):
            v = str(d.get(cle) or "").strip().lower()
            if len(v) >= 4:
                codes.add(v)
    return sorted(codes)


def pertinent(msg: dict, cfg: dict, codes: list[str]) -> tuple[bool, str]:
    adr = adresses(msg)
    externes = [a for a in adr if a.split("@")[-1] not in cfg["internes"]]
    if not externes:
        return False, "echange interne"
    suivis = [a for a in externes if any(a.split("@")[-1] == d or a.split("@")[-1].endswith("." + d) for d in cfg["domaines"])]
    if suivis:
        return True, "domaine suivi : " + suivis[0].split("@")[-1]
    texte = ((msg.get("subject") or "") + " " + (msg.get("bodyPreview") or "")).lower()
    for code in codes:
        if re.search(r"(?<![a-z0-9])" + re.escape(code) + r"(?![a-z0-9])", texte):
            return True, f"code connu : {code}"
    return False, "ni domaine suivi ni code connu"


# ------------------------------------------------------------------ Microsoft Graph
class Graph:
    def __init__(self, jeton: str):
        self.jeton = jeton

    def _requete(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.jeton, "Accept": "application/json"})
        for essai in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code in (429, 503, 504) and essai < 3:  # limitation de debit : on respecte Retry-After
                    time.sleep(min(int(e.headers.get("Retry-After") or 5), 60))
                    continue
                raise RuntimeError(f"Graph {e.code} sur {url.split('?')[0]} : {e.read()[:300].decode('utf-8', 'replace')}") from None
        raise RuntimeError("Graph : trop de tentatives")

    def json(self, url: str) -> dict:
        return json.loads(self._requete(url))

    def messages(self, dossier: str, depuis: datetime):
        """Messages recus depuis la date, du plus recent au plus ancien, pages comprises."""
        params = urllib.parse.urlencode({
            "$filter": "receivedDateTime ge " + depuis.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "$orderby": "receivedDateTime desc", "$top": "50",
            "$select": "id,internetMessageId,subject,from,sender,toRecipients,ccRecipients,receivedDateTime,bodyPreview,hasAttachments"})
        url = f"{GRAPH}/me/mailFolders/{dossier}/messages?{params}"
        while url:
            page = self.json(url)
            yield from page.get("value", [])
            url = page.get("@odata.nextLink")

    def mime(self, id_: str) -> bytes:
        return self._requete(f"{GRAPH}/me/messages/{urllib.parse.quote(id_, safe='')}/$value")


def jeton(cfg: dict, interactif: bool = False) -> str:
    try:
        import msal
    except ImportError:
        sys.exit("msal manque : pip install msal")
    for cle in ("tenant_id", "client_id"):
        if not cfg.get(cle):
            sys.exit(f"« {cle} » absent du bloc outlook de amont_config.json")
    DOSSIER.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER / "cache.bin"
    cache = msal.SerializableTokenCache()
    if chemin.exists():
        cache.deserialize(chemin.read_text(encoding="utf-8"))
    app = msal.PublicClientApplication(cfg["client_id"], authority=f"https://login.microsoftonline.com/{cfg['tenant_id']}", token_cache=cache)
    res = None
    comptes = app.get_accounts()
    if comptes:
        res = app.acquire_token_silent(PORTEE, account=comptes[0])
    if not res:
        if interactif:
            res = app.acquire_token_interactive(PORTEE)
        else:
            flux = app.initiate_device_flow(PORTEE)
            if "user_code" not in flux:
                sys.exit("connexion impossible : " + json.dumps(flux, ensure_ascii=False)[:300])
            print(flux["message"], flush=True)
            res = app.acquire_token_by_device_flow(flux)
    if cache.has_state_changed:
        chemin.write_text(cache.serialize(), encoding="utf-8")
    if not res or "access_token" not in res:
        sys.exit("connexion refusee : " + str((res or {}).get("error_description") or res)[:300])
    return res["access_token"]


# ------------------------------------------------------------------ Amont
def http_json(url: str, entetes: dict | None = None, corps: bytes | None = None, methode: str | None = None) -> dict | list:
    req = urllib.request.Request(url, data=corps, headers=entetes or {}, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Amont {e.code} sur {url} : {e.read()[:300].decode('utf-8', 'replace')}") from None


def deposer_eml(cfg: dict, contenu: bytes, nom: str) -> dict:
    """POST multipart sur /api/echanges/eml (bibliotheque standard seulement)."""
    limite = uuid.uuid4().hex
    corps = (f'--{limite}\r\nContent-Disposition: form-data; name="fichiers"; filename="{nom}"\r\n'
             "Content-Type: message/rfc822\r\n\r\n").encode() + contenu + f"\r\n--{limite}--\r\n".encode()
    return http_json(cfg["amont_url"].rstrip("/") + "/api/echanges/eml",
                     {"Content-Type": f"multipart/form-data; boundary={limite}", "X-Amont-Auteur": cfg["auteur"],
                      "X-Amont-Origine": "outlook"}, corps, "POST")


def nom_eml(msg: dict) -> str:
    jour = (msg.get("receivedDateTime") or "")[:10].replace("-", "_") or "sans_date"
    objet = re.sub(r"[^A-Za-z0-9_.\-]", "_", msg.get("subject") or "courriel")[:60].strip("_") or "courriel"
    return f"{jour}_{objet}.eml"


# ------------------------------------------------------------------ passage
def etat_charger() -> dict:
    try:
        return json.loads((DOSSIER / "etat.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"traites": {}}


def etat_ecrire(etat: dict) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    (DOSSIER / "etat.json").write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")


def traiter(graph, deposer, cfg: dict, codes: list[str], etat: dict, depuis: datetime, simulation: bool = False,
            journal=print) -> dict:
    """Un passage. graph : objet a .messages(dossier, depuis) et .mime(id) ; deposer(contenu, nom) -> reponse d'Amont."""
    bilan = {"vus": 0, "deposes": 0, "doublons": 0, "ignores": 0, "refuses": 0, "erreurs": 0}
    # ordre chronologique, tous dossiers confondus : une reponse n'est deposee qu'apres la demande qu'elle clot
    tous = [(m.get("receivedDateTime") or "", d, m) for d in DOSSIERS_COURRIER for m in graph.messages(d, depuis)]
    for _, dossier, msg in sorted(tous, key=lambda x: x[0]):
        bilan["vus"] += 1
        id_ = msg["id"]
        if id_ in etat["traites"]:
            continue
        ok, raison = pertinent(msg, cfg, codes)
        if not ok:
            bilan["ignores"] += 1
            etat["traites"][id_] = {"statut": "ignore", "raison": raison, "le": datetime.now().isoformat(timespec="seconds")}
            continue
        objet = (msg.get("subject") or "(sans objet)")[:80]
        if simulation:
            journal(f"   [simulation] {dossier} : {objet} ({raison})")
            continue
        try:
            contenu = graph.mime(id_)
            if len(contenu) > TAILLE_MAX:
                raise RuntimeError(f"message de {len(contenu) // (1024 * 1024)} Mo, au-dela de 30 Mo")
            rep = deposer(contenu, nom_eml(msg))
        except RuntimeError as e:
            bilan["erreurs"] += 1
            journal(f"   erreur : {objet} : {e}")
            continue  # pas memorise : repris au prochain passage
        if rep.get("refuses"):
            bilan["refuses"] += 1
            motif = rep["refuses"][0].get("motif", "")
            journal(f"   non rattache : {objet} ({motif})")
            etat["traites"][id_] = {"statut": "refuse", "raison": motif, "le": datetime.now().isoformat(timespec="seconds")}
            continue
        doublon = any(c.get("doublon") for c in rep.get("crees", []))
        bilan["doublons" if doublon else "deposes"] += 1
        if not doublon:
            c = rep["crees"][0]
            journal(f"   depose : {objet} -> {c.get('demande_id') or c.get('projet_code')} ({c.get('sens')})")
        etat["traites"][id_] = {"statut": "depose", "le": datetime.now().isoformat(timespec="seconds")}
    return bilan


def passage(cfg: dict, args, interactif: bool = False) -> dict:
    graph = Graph(jeton(cfg, interactif))
    demandes = http_json(cfg["amont_url"].rstrip("/") + "/api/demandes")
    codes = codes_demandes(demandes)
    etat = etat_charger()
    depuis = datetime.now(timezone.utc) - timedelta(days=args.depuis or cfg["depuis_jours"])
    bilan = traiter(graph, lambda c, n: deposer_eml(cfg, c, n), cfg, codes, etat, depuis, args.simulation)
    if not args.simulation:
        etat_ecrire(etat)
    return bilan


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--simulation", action="store_true", help="liste ce qui serait depose, ne depose rien")
    p.add_argument("--depuis", type=int, default=0, help="remonter de N jours (defaut : 30 ou « depuis_jours »)")
    p.add_argument("--boucle", type=int, default=0, help="repeter toutes les N minutes")
    p.add_argument("--navigateur", action="store_true", help="connexion par fenetre de navigateur au lieu du code a saisir")
    args = p.parse_args()
    cfg = charger_config()
    while True:
        try:
            b = passage(cfg, args, args.navigateur)
            print(f"{datetime.now():%H:%M} : {b['vus']} vus, {b['deposes']} deposes, {b['doublons']} doublons, "
                  f"{b['ignores']} ignores, {b['refuses']} non rattaches, {b['erreurs']} erreurs", flush=True)
        except (RuntimeError, urllib.error.URLError) as e:
            print("passage en echec :", e, flush=True)
        if not args.boucle:
            break
        time.sleep(args.boucle * 60)


if __name__ == "__main__":
    main()
