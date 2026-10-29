"""Lecture des reponses des operateurs : aujourd'hui l'etude exploratoire RTE.

Les etudes RTE suivent un gabarit stable (corpus 2023 a 2026 : Haynecourt, Fortum, E-Valley, Angouleme,
Oursel-Maison) : cartouche « ETUDE EXPLORATOIRE n° 26-4883 », tableau « Expose de la demande », domaine de
tension (article 105 et distance « d »), puis une section « 2.x Solution » par solution etudiee avec tension,
cout du raccordement, contribution du client et delai. Lecture par regles, sans IA : c'est exact et
verifiable. L'IA locale ne sert qu'en secours, si les regles ne trouvent aucune solution (gabarit change).

Rien n'est reporte dans la demande sans clic : on montre les solutions, l'utilisateur choisit celle a reporter,
et un point « a verifier » est cree pour le responsable.
"""

from __future__ import annotations

import re
from datetime import date

from . import ia


def _nb(t: str) -> float | None:
    t = (t or "").replace(" ", " ").replace("\xa0", " ").strip()
    t = re.sub(r"(?<=\d) (?=\d{3}\b)", "", t).replace(" ", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _keur(valeur: str, unite: str) -> int | None:
    n = _nb(valeur)
    if n is None:
        return None
    return int(round(n * 1000)) if unite.upper().startswith("M") else int(round(n))


def _date(t: str) -> str | None:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", t or "")
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", t or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def est_etude_rte(texte: str) -> bool:
    t = texte[:6000].upper()
    return "ETUDE EXPLORATOIRE" in t.replace("É", "E") and ("RTE" in t or "RESEAU DE TRANSPORT" in t)


def lire_etude_exploratoire(texte: str) -> dict:
    """Champs d'une etude exploratoire RTE (texte issu de pdftotext -layout). Valeurs absentes : None."""
    t = texte.replace("’", "'").replace("\f", "\n")
    out: dict = {"type": "etude_exploratoire_rte", "num_etude": None, "date_etude": None, "date_demande": None,
                 "puissance_mw": None, "puissances_mw": [], "d_km": None, "poste_reference": None, "domaine": None,
                 "solutions": [], "methode": "regles"}
    m = re.search(r"ETUDE EXPLORATOIRE\s*n\s*°\s*(\d{2}-\d{3,5})", t, re.I)
    out["num_etude"] = m.group(1) if m else None
    if not out["num_etude"]:
        m = re.search(r"\b(\d{2}-\d{4})\b", t[:3000])
        out["num_etude"] = m.group(1) if m else None
    m = re.search(r"Date\s*:\s*(\d{1,2}/\d{1,2}/\d{4}|\d{4}\.\d{2}\.\d{2})", t)
    out["date_etude"] = _date(m.group(1)) if m else None
    m = re.search(r"Date de la demande\s+(\d{1,2}/\d{1,2}/\d{4})", t)
    out["date_demande"] = _date(m.group(1)) if m else None
    m = re.search(r"puissances? de raccordement demandées? de ([\d\s,]+MW(?:\s*et\s*[\d\s,]+MW)?)", t, re.I)
    if m:
        out["puissances_mw"] = [int(_nb(x)) for x in re.findall(r"([\d\s,]+?)\s*MW", m.group(1)) if _nb(x)]
    if not out["puissances_mw"]:
        m = re.search(r"Puissance de raccordement au\s+([\d\s,]+)\s*MW", t)
        if m and _nb(m.group(1)):
            out["puissances_mw"] = [int(_nb(m.group(1)))]
    if not out["puissances_mw"]:
        m = re.search(r"Puissance de raccordement[^\n]{0,40}?\s([\d\s]{2,6})\s*MW", t)
        if m and _nb(m.group(1)):
            out["puissances_mw"] = [int(_nb(m.group(1)))]
    out["puissance_mw"] = max(out["puissances_mw"]) if out["puissances_mw"] else None
    m = re.search(r"distance «\s*d\s*» entre .{0,80}?poste RTE ([^,\n]{3,60}?)\s+a été\s*(?:\n\s*)?estimée? à\s+([\d,\.]+)\s*km", t, re.S)
    if m:
        out["poste_reference"] = re.sub(r"\s+", " ", m.group(1)).strip()
        out["d_km"] = _nb(m.group(2))
    m = re.search(r"tension de raccordement de\s+(?:\n\s*)?référence est (?:la )?(HTB\d|HTA)\s*(?:\(([^)]+)\))?", t, re.S)
    if m:
        out["domaine"] = m.group(1) + (f" ({m.group(2)})" if m.group(2) else "")

    # solutions : « 2.1 Solution 1 : ... », « 2.1 Solution étudiée : ... », « 2.1 Solution : ... »
    entetes = list(re.finditer(r"^\s*2\.(\d)\s+Solution[^:\n]*:\s*(.+)$", t, re.M))
    for k, e in enumerate(entetes):
        fin = entetes[k + 1].start() if k + 1 < len(entetes) else len(t)
        bloc = t[e.end():fin]
        titre = e.group(2).strip()
        suite = bloc.lstrip("\n").split("\n", 1)[0].strip()
        if suite and not re.search(r"Schéma|Tension|Description|ETUDE|Page", suite) and len(suite) < 90:
            titre += " " + suite
        titre = re.sub(r"\s*-\s*Schéma.*$", "", titre).rstrip(" :;-")
        sol = {"numero": int(e.group(1)), "titre": re.sub(r"\s+", " ", titre).strip(), "tension_kv": None,
               "puissance_mw": None, "cout_total_keur": None, "cout_client_keur": None, "delai_mois": None, "delai_texte": None}
        m = re.search(r"Tension de raccordement\s+(\d+)\s*kV(?:\s+pour une puissance de raccordement de\s+([\d\s]+)\s*MW)?", bloc)
        if m:
            sol["tension_kv"] = int(m.group(1))
            sol["puissance_mw"] = int(_nb(m.group(2))) if m.group(2) and _nb(m.group(2)) else None
        m = re.search(r"Coût du raccordement\s*:\s*([\d\s,\.]+?)\s*(M€|k€)", bloc)
        if m:
            sol["cout_total_keur"] = _keur(m.group(1), m.group(2))
        m = re.search(r"Contribution du client\s*:\s*([\d\s,\.]+?)\s*(M€|k€)", bloc)
        if m:
            sol["cout_client_keur"] = _keur(m.group(1), m.group(2))
        m = re.search(r"Délai de raccordement\s+(?:Le délai de raccordement est estimé à\s+)?(?:environ\s+)?(\d+)\s*(mois|ans?)\b", bloc)
        if m:
            sol["delai_mois"] = int(m.group(1)) * (12 if m.group(2).startswith("an") else 1)
            sol["delai_texte"] = f"{m.group(1)} {m.group(2)}"
        out["solutions"].append(sol)
    if not out["puissance_mw"]:
        ps = [x["puissance_mw"] for x in out["solutions"] if x.get("puissance_mw")]
        out["puissance_mw"] = max(ps) if ps else None
    return out


SCHEMA_IA = {"type": "object", "properties": {
    "num_etude": {"type": "string"}, "date_etude": {"type": "string"}, "date_demande": {"type": "string"},
    "puissance_mw": {"type": "number"}, "d_km": {"type": "number"}, "poste_reference": {"type": "string"},
    "solutions": {"type": "array", "items": {"type": "object", "properties": {
        "titre": {"type": "string"}, "tension_kv": {"type": "number"}, "cout_total_keur": {"type": "number"},
        "cout_client_keur": {"type": "number"}, "delai_mois": {"type": "number"}},
        "required": ["titre"]}}},
    "required": ["solutions"]}


def lire(texte: str) -> dict:
    """Regles d'abord ; IA locale en secours si aucune solution n'est trouvee."""
    r = lire_etude_exploratoire(texte)
    if r["solutions"] or not ia.disponible():
        return r
    consigne = ("Extrait de cette etude exploratoire RTE les champs demandes. Couts en milliers d'euros (k€), delais en mois, "
                "dates AAAA-MM-JJ. Une entree par solution de raccordement etudiee. N'invente rien.\n\n<document>\n"
                + texte[:40000] + "\n</document>")
    rep, _ = ia.demander_json(consigne, schema=SCHEMA_IA)
    if isinstance(rep, dict):
        for k in ("num_etude", "date_etude", "date_demande", "puissance_mw", "d_km", "poste_reference"):
            if not r.get(k) and rep.get(k):
                r[k] = rep[k]
        r["solutions"] = [{"numero": i + 1, "titre": str(s.get("titre") or ""), "tension_kv": s.get("tension_kv"),
                           "puissance_mw": None, "cout_total_keur": s.get("cout_total_keur"), "cout_client_keur": s.get("cout_client_keur"),
                           "delai_mois": s.get("delai_mois"), "delai_texte": None} for i, s in enumerate(rep.get("solutions") or [])]
        r["methode"] = "ia"
    return r


def champs_demande(analyse: dict, numero_solution: int | None) -> dict:
    """Champs de la demande RTE EE a reporter pour la solution choisie (None : sans solution)."""
    out = {}
    if analyse.get("num_etude"):
        out["num_etude"] = analyse["num_etude"]
    if analyse.get("date_etude"):
        out["date_etude_recue"] = analyse["date_etude"]
    if analyse.get("d_km") is not None:
        out["d_km"] = analyse["d_km"]
    sol = next((s for s in analyse.get("solutions") or [] if s["numero"] == numero_solution), None)
    if sol:
        out["solution"] = sol["titre"][:200]
        for k in ("cout_total_keur", "cout_client_keur", "delai_mois"):
            if sol.get(k) is not None:
                out[k] = sol[k]
    return out


def aujourdhui() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# PTF RTE (0.9, 28/10/2026). Gabarit des Conditions Particulieres : page 2 « RESUME DE LA PROPOSITION DE RTE »
# (demande, solution, delai, contribution, acompte), article 4-1 (tension). Calibre sur les PTF 24-4062-02
# (Calais, 300 MW, 400 kV) et 25-3905 (Beauvais, 300 MW, 225 kV).
# ---------------------------------------------------------------------------

def est_ptf_rte(texte: str) -> bool:
    t = texte[:8000].upper().replace("É", "E")
    return "PROPOSITION TECHNIQUE ET FINANCIERE" in t and ("RTE" in t or "RESEAU DE TRANSPORT" in t)


_NOMBRE = r"(\d[\d  \xa0]*(?:[,.]\d+)?)"


def _montant(fenetre: str) -> int | None:
    """Premier montant d'une fenetre de texte, en k€ (unite € ou k€ lue dans la fenetre)."""
    m = re.search(_NOMBRE + r"(?=\s*(?:k€|M€|€|\n|$))", fenetre)
    if not m:
        return None
    n = _nb(m.group(1))
    if n is None:
        return None
    u = re.search(r"(k€|M€|€)", fenetre)
    unite = u.group(1) if u else "€"
    if unite == "M€":
        return int(round(n * 1000))
    if unite == "k€":
        return int(round(n))
    return int(round(n / 1000))


def lire_ptf(texte: str) -> dict:
    """Champs d'une PTF RTE (texte pdftotext -layout). Valeurs absentes : None."""
    t = texte.replace("’", "'").replace("\f", "\n")
    out: dict = {"type": "ptf_rte", "num_ptf": None, "client": None, "date_demande": None, "puissance_mw": None,
                 "solution": None, "poste": None, "tension_kv": None, "domaine_reference": None, "delai_mois": None,
                 "delai_reduit_mois": None, "delai_texte": None, "cout_client_keur": None, "acompte_keur": None,
                 "validite_mois": None, "limitations": None, "methode": "regles", "solutions": []}
    m = re.search(r"PROPOSITION TECHNIQUE ET FINANCIERE\s*N\s*°\s*([\d]{2}-[\d]{3,5}(?:-\d{2})?)", t, re.I)
    out["num_ptf"] = m.group(1) if m else None
    m = re.search(r"Bénéficiaire\s*:\s*\n\s*(.+?),", t)
    out["client"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else None
    resume = t
    m = re.search(r"RESUME DE LA PROPOSITION", t, re.I)
    if m:
        fin = re.search(r"SOMMAIRE|PREAMBULE", t[m.end():])
        resume = t[m.end(): m.end() + (fin.start() if fin else 6000)]
    m = re.search(r"Le (\d{1,2}/\d{1,2}/\d{4}),[^\n]{0,120}?demande de PTF", resume)
    out["date_demande"] = _date(m.group(1)) if m else None
    m = re.search(r"Pracc\)?\s*demandée par le Client\s*:\s*([\d\s]+)\s*MW", t) or re.search(r"demande de PTF[^.]{0,160}?([\d ]{2,6})\s*MW", resume, re.S)
    if m and _nb(m.group(1)):
        out["puissance_mw"] = int(_nb(m.group(1)))
    m = re.search(r"SOLUTION DE RACCORDEMENT PROPOSEE\s*(.+?)\s*(?:□|\n\s*\n\s*\n)\s*(?:DELAI|$)", resume, re.S | re.I)
    if not m:
        m = re.search(r"SOLUTION DE RACCORDEMENT PROPOSEE\s*(.+?)DELAI DE MISE", resume, re.S | re.I)
    if m:
        s = re.sub(r"\s+", " ", m.group(1).replace("□", " ")).strip(" .")
        s = re.sub(r"^La solution de raccordement proposée est composée des Ouvrages de raccordement suivants\s*:\s*", "", s)
        out["solution"] = s[:1500]
    zone_poste = out["solution"] or resume
    m = re.search(r"poste (?:RTE )?(?:des |de la |du |de |d')?([A-ZÉÈÀÂÎÔ][A-ZÉÈÀÂÎÔ' \-]{2,40}?)\s+(\d{2,3})\s*kV", zone_poste)
    if m:
        out["poste"] = f"{m.group(1).strip().title()} {m.group(2)} kV"
    ms = list(re.finditer(r"Article 4-1 TENSION DE RACCORDEMENT(?!\s*\.)\s*(.{0,600})", t, re.S | re.I))  # pas le sommaire
    m = ms[-1] if ms else None
    if m:
        bloc = m.group(1)
        d = re.search(r"domaine de tension de raccordement de référence est (?:la )?(HTB\d|HTA)\s*(?:\((\d+)\s*kV\))?", bloc)
        if d:
            out["domaine_reference"] = d.group(1) + (f" ({d.group(2)} kV)" if d.group(2) else "")
        k = re.search(r"effectué à la tension\s*(\d{2,3})\s*kV", bloc)
        if k:
            out["tension_kv"] = int(k.group(1))
    m = re.search(r"DELAI DE MISE A DISPOSITION\s*(.+?)(?:□|CONTRIBUTION FINANCIERE)", resume, re.S | re.I)
    bloc = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    out["delai_texte"] = bloc[:600] or None
    m = re.search(r"délai de (?:mise à disposition )?(?:du )?raccordement est de\s*(\d+)\s*mois", bloc or t, re.I)
    if not m:
        m = re.search(r"Délai de Raccordement est de\s*(\d+)\s*mois", t)
    out["delai_mois"] = int(m.group(1)) if m else None
    m = re.search(r"(?:ramené|réduit)\s+à\s*(\d+)\s*mois", bloc)
    out["delai_reduit_mois"] = int(m.group(1)) if m else None
    m = re.search(r"limitations temporaires[^.]{0,200}?([\d ]{3,6})\s*heures par ans?\s*jusqu'en\s*(\d{4})", re.sub(r"\s+", " ", resume), re.I)
    if m:
        out["limitations"] = f"{_nb(m.group(1)):g} h/an jusqu'en {m.group(2)}"
    m = re.search(r"Contribution financière totale, hors taxes, à la charge du Client(.{0,160})", resume, re.S)
    if m:
        out["cout_client_keur"] = _montant(m.group(1))
    m = re.search(r"acompte, hors taxes, à verser à la signature(.{0,200})", resume, re.S)
    if m:
        out["acompte_keur"] = _montant(m.group(1))
    m = re.search(r"engage RTE pour une durée de\s*(\d+)\s*mois", t)
    out["validite_mois"] = int(m.group(1)) if m else None
    # une « solution » pour reutiliser l'affichage et le report des etudes
    out["solutions"] = [{"numero": 1, "titre": (out["poste"] or "Solution PTF") + (f", {out['tension_kv']} kV" if out["tension_kv"] and "kV" not in (out["poste"] or "") else ""),
                         "tension_kv": out["tension_kv"], "puissance_mw": out["puissance_mw"], "cout_total_keur": None,
                         "cout_client_keur": out["cout_client_keur"], "delai_mois": out["delai_mois"], "delai_texte": None}]
    return out


SCHEMA_PTF = {"type": "object", "properties": {
    "num_ptf": {"type": "string"}, "puissance_mw": {"type": "number"}, "solution": {"type": "string"},
    "tension_kv": {"type": "number"}, "delai_mois": {"type": "number"}, "cout_client_keur": {"type": "number"},
    "acompte_keur": {"type": "number"}}, "required": ["num_ptf"]}


def lire_ptf_complete(texte: str) -> dict:
    """Regles d'abord ; IA locale pour les seuls champs manquants (gabarit change)."""
    r = lire_ptf(texte)
    manque = [k for k in ("num_ptf", "delai_mois", "cout_client_keur") if r.get(k) is None]
    if not manque or not ia.disponible():
        return r
    consigne = ("Extrait de cette proposition technique et financiere RTE les champs demandes. Montants en milliers d'euros (k€) "
                "hors taxes, delais en mois. N'invente rien : champ absent si introuvable.\n\n<document>\n" + texte[:30000] + "\n</document>")
    rep, _ = ia.demander_json(consigne, schema=SCHEMA_PTF)
    if isinstance(rep, dict):
        for k in SCHEMA_PTF["properties"]:
            if r.get(k) in (None, "") and rep.get(k) not in (None, ""):
                r[k] = rep[k]
        r["methode"] = "regles+ia"
        r["solutions"][0].update({"cout_client_keur": r["cout_client_keur"], "delai_mois": r["delai_mois"], "tension_kv": r["tension_kv"]})
    return r


def champs_ptf(analyse: dict) -> dict:
    """Champs de la demande RTE PTF a reporter depuis une PTF lue."""
    out = {}
    for src, dst in (("num_ptf", "num_ptf"), ("cout_client_keur", "cout_client_keur"), ("delai_mois", "delai_mois"),
                     ("delai_reduit_mois", "delai_reduit_mois"), ("acompte_keur", "acompte_keur"), ("tension_kv", "tension_raccordement_kv"),
                     ("poste", "poste_raccordement"), ("limitations", "limitations_temporaires")):
        if analyse.get(src) not in (None, ""):
            out[dst] = analyse[src]
    return out
