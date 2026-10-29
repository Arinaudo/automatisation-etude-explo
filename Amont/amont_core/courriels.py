"""Lecture des courriels deposes dans Amont (.eml) et rattachement a une demande.

En attendant le branchement d'une boite mail (backend a definir), les echanges arrivent
de trois facons : saisie manuelle, depot d'un fichier .eml (Outlook web et nouveau Outlook :
« Telecharger » sur le message), ou POST /api/echanges par un futur programme de releve.
Sans dependance hors bibliotheque standard.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime

LIMITE_CORPS = 6000
LIMITE_RESUME = 700
# Debut d'un message cite : on coupe le resume avant.
_CITATION = re.compile(
    r"^\s*(De\s*:|From\s*:|-{3,}\s*(Message d'origine|Original Message)|Le .{5,80} a écrit\s*:|On .{5,80} wrote:|Envoyé\s*:)",
    re.IGNORECASE | re.MULTILINE,
)


def _texte_html(h: str) -> str:
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = html.unescape(h)
    h = re.sub(r"[ \t\xa0]+", " ", h)
    return re.sub(r"\n\s*\n+", "\n\n", h).strip()


def _adresses(valeurs) -> list[str]:
    return [a.lower() for _, a in getaddresses([v for v in valeurs if v]) if a]


def lire_eml(contenu: bytes) -> dict:
    """Champs utiles d'un .eml : expediteur, destinataires, objet, date ISO, message_id, corps, pieces jointes."""
    msg = BytesParser(policy=policy.default).parsebytes(contenu)
    date_iso = None
    if msg["date"]:
        try:
            dt = parsedate_to_datetime(str(msg["date"]))
            if dt.tzinfo:
                dt = dt.astimezone().replace(tzinfo=None)
            date_iso = dt.replace(microsecond=0).isoformat(sep=" ")
        except (TypeError, ValueError):
            date_iso = None
    corps = ""
    partie = msg.get_body(preferencelist=("plain", "html"))
    if partie is not None:
        try:
            brut = partie.get_content()
        except (LookupError, ValueError):
            brut = (partie.get_payload(decode=True) or b"").decode("utf-8", "replace")
        corps = _texte_html(brut) if partie.get_content_type() == "text/html" else brut.strip()
    pj = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    exp = _adresses([str(msg["from"] or "")])
    return {
        "expediteur": exp[0] if exp else "",
        "expediteur_nom": _nom(str(msg["from"] or "")),
        "destinataires": ", ".join(_adresses([str(msg["to"] or ""), str(msg["cc"] or "")])),
        "objet": str(msg["subject"] or "").strip(),
        "date": date_iso,
        "message_id": str(msg["message-id"] or "").strip() or None,
        "corps": corps[:LIMITE_CORPS],
        "pieces_jointes": pj,
    }


def pieces_jointes(contenu: bytes) -> list[tuple[str, bytes]]:
    """(nom, contenu) des pieces jointes PDF d'un .eml."""
    msg = BytesParser(policy=policy.default).parsebytes(contenu)
    out = []
    for p in msg.iter_attachments():
        nom = p.get_filename() or ""
        if nom.lower().endswith(".pdf") or p.get_content_type() == "application/pdf":
            data = p.get_payload(decode=True)
            if data:
                out.append((nom or "piece_jointe.pdf", data))
    return out


def _nom(entete: str) -> str:
    noms = [n for n, _ in getaddresses([entete]) if n]
    return noms[0] if noms else ""


def resume(corps: str) -> str:
    """Le message propre, sans l'historique cite, coupe a environ 700 caracteres."""
    m = _CITATION.search(corps or "")
    t = (corps[:m.start()] if m else corps or "").strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    if len(t) > LIMITE_RESUME:
        t = t[:LIMITE_RESUME].rsplit(" ", 1)[0] + " […]"
    return t


def deviner_sens(expediteur: str, mes_adresses: list[str]) -> str:
    mes = {a.lower().strip() for a in mes_adresses if a}
    if expediteur and expediteur.lower() in mes:
        return "envoye"
    domaines = {a.split("@")[-1] for a in mes if "@" in a}
    if expediteur and expediteur.split("@")[-1] in domaines:
        return "envoye"
    return "recu"


def deviner_demande(texte: str, demandes: list[dict]) -> tuple[str | None, str | None]:
    """(demande_id, projet_code) d'apres l'objet et le corps : code de demande, n° d'etude RTE,
    n° de dossier operateur, puis nom de site ou de commune (projet seul). (None, None) sinon."""
    t = (texte or "").lower()
    if not t:
        return None, None
    for d in demandes:
        for cle in ("id", "num_etude", "ref_dossier"):
            v = str(d.get(cle) or "").strip().lower()
            if len(v) >= 4 and re.search(r"(?<![a-z0-9])" + re.escape(v) + r"(?![a-z0-9])", t):
                return d["id"], d["projet_code"]
    projets = {}
    for d in demandes:
        for cle in ("site", "commune"):
            v = str(d.get(cle) or "").strip().lower()
            if len(v) >= 5 and v in t:
                projets.setdefault(d["projet_code"], set()).add(d["filiere"])
    if len(projets) == 1:
        return None, next(iter(projets))
    return None, None


def deviner_filiere(texte: str, adresse: str) -> str | None:
    """Filiere probable d'un echange d'apres l'adresse et le texte, pour choisir la demande du projet."""
    a = (adresse or "").lower()
    t = (texte or "").lower()
    if "rte-france" in a or "rte france" in t:
        return "rte_ptf" if re.search(r"\bptf\b|fiche d2|proposition technique", t) else "rte_ee"
    if "enedis" in a or "enedis" in t:
        return "enedis"
    if "grdf" in a or "grdf" in t:
        return "grdf"
    if "natran" in a or "grtgaz" in a or "natran" in t:
        return "natran"
    return None


def maintenant() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")
