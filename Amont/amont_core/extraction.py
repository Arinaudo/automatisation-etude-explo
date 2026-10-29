"""Extraction des donnees de la fiche identite depuis les fichiers sources d'un site.

Deux moteurs, cumules :
  1. lecture du texte (PDF, Word, Excel, PowerPoint, JSON, texte) ;
  2. analyse :
     - par regles (expressions regulieres calees sur les documents du corpus : etudes de faisabilite
       DatacenterSiteAnalyzer, etudes exploratoires RTE, reglements de PLU...), toujours appliquees ;
     - par IA locale si elle est configuree (voir amont_core/ia.py : Ollama, puis le serveur interne).
       Elle complete les regles : champs qu'elles n'ont pas trouves, et lecture des scans et des plans
       (pages rendues en images, envoyees au modele de vision). Chaque valeur proposee par l'IA est
       recherchee dans le texte du document : introuvable, elle est gardee avec une confiance basse
       et la mention « non retrouvée », pour la verification.

Le resultat est une liste de propositions {champ, valeur, extrait, confiance}. Rien n'est ecrit
ici : c'est le stockage qui decide de remplir un champ vide ou de garder la proposition en attente.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import fiche, ia

MAX_PAGES_VISION = 4
RESOLUTION_VISION = 110  # dpi : lisible pour un modele de vision, leger en memoire

TYPES_SOURCES = {
    "faisabilite": "Étude de faisabilité",
    "etude_rte": "Étude RTE",
    "plu": "Règlement ou plan de PLU",
    "cadastre": "Cadastre",
    "foncier": "Foncier (cession, promesse, acte)",
    "permis": "Permis, autorisation",
    "plan": "Plan, schéma",
    "presentation": "Présentation",
    "tableur": "Tableur",
    "societe": "Société (Kbis, RIB)",
    "autre": "Autre",
}


# ------------------------------------------------------------------- lecture
def lire_texte(chemin: Path) -> str:
    ext = chemin.suffix.lower()
    if ext == ".pdf":
        return _texte_pdf(chemin)
    if ext == ".docx":
        import docx
        d = docx.Document(str(chemin))
        parties = [p.text for p in d.paragraphs]
        for t in d.tables:
            for r in t.rows:
                parties.append(" | ".join(c.text for c in r.cells))
        return "\n".join(parties)
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(str(chemin), read_only=True, data_only=True)
        lignes = []
        for ws in wb.worksheets:
            lignes.append(f"# Onglet {ws.title}")
            for r in ws.iter_rows(values_only=True):
                cells = [str(c) for c in r if c not in (None, "")]
                if cells:
                    lignes.append(" | ".join(cells))
        return "\n".join(lignes)
    if ext == ".pptx":
        from pptx import Presentation
        lignes = []
        for i, s in enumerate(Presentation(str(chemin)).slides, start=1):
            lignes.append(f"# Diapositive {i}")
            for sh in s.shapes:
                if sh.has_text_frame:
                    lignes.append(sh.text_frame.text)
                if getattr(sh, "has_table", False) and sh.has_table:
                    for r in sh.table.rows:
                        lignes.append(" | ".join(c.text for c in r.cells))
        return "\n".join(lignes)
    if ext == ".json":
        try:
            return _json_en_texte(json.loads(chemin.read_text(encoding="utf-8")))
        except ValueError:
            return chemin.read_text(encoding="utf-8", errors="replace")
    if ext in (".txt", ".md", ".csv"):
        return chemin.read_text(encoding="utf-8", errors="replace")
    return ""


def _texte_pdf(chemin: Path) -> str:
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", str(chemin), "-"], capture_output=True, timeout=120)
            if r.returncode == 0:
                return r.stdout.decode("utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            pass
    import pdfplumber
    with pdfplumber.open(str(chemin)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages[:200])


def _json_en_texte(o, prefixe: str = "") -> str:
    """Aplatit un JSON (ex. sortie du DatacenterSiteAnalyzer) en lignes « cle : valeur »."""
    lignes = []
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                lignes.append(_json_en_texte(v, f"{prefixe}{k}."))
            else:
                lignes.append(f"{prefixe}{k} : {v}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            lignes.append(_json_en_texte(v, f"{prefixe}{i}."))
    else:
        lignes.append(f"{prefixe} {o}")
    return "\n".join(x for x in lignes if x)


# ---------------------------------------------------------------- classement
def classer(nom: str, texte: str) -> str:
    n = nom.lower()
    t = texte[:4000].lower()
    if re.search(r"analysis|faisabilit|dc opportunity|site ?analy", n) or "verdict" in t and "score" in t:
        return "faisabilite"
    if re.search(r"(^|[_\W])(ee|ptf)([_\W]|$)|rte", n) or "etude exploratoire n°" in t or "étude exploratoire n°" in t:
        return "etude_rte"
    if "plu" in n or "plan local d" in t:
        return "plu"
    if "cadastr" in n or "extrait cadastral" in t or "relevé de propriété" in t:
        return "cadastre"
    if re.search(r"cession|promesse|acte|compromis|vente", n):
        return "foncier"
    if re.search(r"permis|(^|[_\W])pc([_\W]|$)|arr[eê]t[eé]", n):
        return "permis"
    if re.search(r"kbis|rib|statuts", n):
        return "societe"
    if re.search(r"plan|unifilaire|masse|implantation", n):
        return "plan"
    if Path(n).suffix in (".pptx", ".ppt"):
        return "presentation"
    if Path(n).suffix in (".xlsx", ".xlsm", ".csv"):
        return "tableur"
    return "autre"


# -------------------------------------------------------------------- regles
def _extrait(texte: str, debut: int, fin: int, marge: int = 60) -> str:
    s = texte[max(0, debut - marge):min(len(texte), fin + marge)]
    return re.sub(r"\s+", " ", s).strip()


def _nombre_fr(s: str) -> float | None:
    s = s.replace(" ", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def par_regles(nom: str, texte: str, type_source: str) -> list[dict]:
    props: list[dict] = []
    vus: set[str] = set()

    def ajouter(champ, valeur, m=None, confiance=0.6, extrait=None):
        if champ in vus or valeur in (None, ""):
            return
        vus.add(champ)
        props.append({"champ": champ, "valeur": valeur, "confiance": confiance,
                      "extrait": extrait if extrait is not None else (_extrait(texte, m.start(), m.end()) if m else "")})

    # Localisation : « Ville : 25400 Exincourt », « Commune : ... », en-tete RTE « SUR LA COMMUNE D'ANGOULEME (16) »
    m = re.search(r"(?:Ville|Commune|Localisation)\s*:\s*(\d{5})\s+([A-ZÀ-Ý][\wÀ-ÿ'’\- ]{1,40}?)\s*(?:\n|$|,|;)", texte)
    if m:
        ajouter("code_postal", m.group(1), m, 0.8)
        ajouter("commune", m.group(2).strip(), m, 0.7)
        ajouter("departement", m.group(1)[:2] if not m.group(1).startswith("97") else m.group(1)[:3], m, 0.7)
    m = re.search(r"SUR LA COMMUNE D['’]\s?([A-ZÀ-Ý][A-ZÀ-Ý'’\- ]+?)\s*\((\d{2,3}|2[AB])\)", texte)
    if m:
        ajouter("commune", m.group(1).strip().title(), m, 0.8)
        ajouter("departement", m.group(2), m, 0.8)
    m = re.search(r"Région\s*:\s*([^\n•]{3,40})", texte)
    if m:
        ajouter("region", m.group(1).strip(), m, 0.8)

    # Adresse en tete des etudes de faisabilite : ligne au-dessus de « 25400 Commune »
    m = re.search(r"^\s*([^\n:]{3,80}?)\s+(\d{5})\s+([A-ZÀ-Ý][\wÀ-ÿ'’\- ]+)\s*$", texte[:600], re.M)
    if m and type_source == "faisabilite":
        ajouter("adresse", m.group(1).strip(), m, 0.5)

    # GPS : « GPS : 47.506038, 6.827314 », « Latitude : 45.63696 ... Longitude : 0.13179 »
    m = re.search(r"(?:GPS|Coordonnées(?: du site)?)\s*:\s*(-?\d{1,2}[.,]\d{3,})\s*[,;/ ]\s*(-?\d{1,3}[.,]\d{3,})", texte)
    if m:
        ajouter("lat", _nombre_fr(m.group(1)), m, 0.8)
        ajouter("lon", _nombre_fr(m.group(2)), m, 0.8)
    m = re.search(r"Latitude\s*:?\s*(-?\d{1,2}[.,]\d{3,}).{0,80}?Longitude\s*:?\s*(-?\d{1,3}[.,]\d{3,})", texte, re.S)
    if m:
        ajouter("lat", _nombre_fr(m.group(1)), m, 0.8)
        ajouter("lon", _nombre_fr(m.group(2)), m, 0.8)

    # Puissance : entete RTE « D'UNE PUISSANCE DE 60 MW », « Puissance de raccordement ... 60 MW »
    m = re.search(r"PUISSANCE DE\s+(\d[\d\s,.]*)\s*MW", texte) or \
        re.search(r"Puissance de raccordement[^\n]{0,40}\n?\s*(\d[\d\s,.]*)\s*MW", texte, re.I)
    if m:
        ajouter("puissance_mw", _nombre_fr(m.group(1)), m, 0.8)
    m = re.search(r"Date de mise en service souhaitée\s*\n?\s*(\d{2}/\d{2}/\d{4})", texte)
    if m:
        ajouter("date_mise_a_disposition", m.group(1), m, 0.7)

    # Poste RTE : « PE (poste électrique) d'Étupes (225 kV) à 1.56 km », on garde la tension la plus haute
    postes = []
    for m in re.finditer(r"(?:\bPE\b|[Pp]oste(?: source)?(?: électrique)?)(?:\s*\([^)]{0,30}\))?\s*(?:RTE\s+)?(?:d['’]\s?|de\s+)?"
                         r"([A-ZÀ-Ý][\wÀ-ÿ'’\-]+(?:[ \-][A-ZÀ-Ý][\wÀ-ÿ'’\-]+){0,3})\s*\((\d{2,3})\s*kV[^)]*\)\s*à\s*(\d+(?:[.,]\d+)?)\s*km", texte):
        if m.group(1).upper() == "RTE":
            continue
        postes.append((int(m.group(2)), -(_nombre_fr(m.group(3)) or 0), m))
    if postes:
        kv, moins_d, m = max(postes)
        ajouter("poste_rte", m.group(1), m, 0.6)
        ajouter("tension_kv", kv, m, 0.6)
        ajouter("distance_poste_km", -moins_d, m, 0.6)

    # Cadastre : detail des etudes de faisabilite « AH 367 : 112 813 m² », sinon « section AH n° 367 », « parcelle AH 367 »
    if type_source != "plu":
        parcelles, premier = [], None
        for m in re.finditer(r"\b([A-Z]{1,2}) (\d{1,4}) : [\d\s\u202f]+ m²", texte):
            p = f"{m.group(1)} {int(m.group(2))}"
            premier = premier or m
            if p not in parcelles:
                parcelles.append(p)
        if not parcelles:
            for m in re.finditer(r"(?i:section|parcelles?|cadastr\w*)\s*:?\s*([A-Z]{1,2})\s*(?:n°|no|numéro)?\s*(\d{1,4})\b", texte):
                p = f"{m.group(1)} {int(m.group(2))}"
                premier = premier or m
                if p not in parcelles:
                    parcelles.append(p)
        if parcelles:
            ajouter("parcelles", ", ".join(parcelles[:40]), premier, 0.7)
    m = re.search(r"INSEE\s*:?\s*(\d{5}|2[AB]\d{3})", texte)
    if m:
        ajouter("code_insee", m.group(1), m, 0.5)

    # Surface du terrain
    m = re.search(r"(?:surface|superficie|emprise|terrain|foncier)[^\n]{0,50}?(\d+(?:[,.]\d+)?)\s*ha\b", texte, re.I)
    if m and type_source != "plu":
        ajouter("surface_ha", _nombre_fr(m.group(1)), m, 0.5)

    # Zonage PLU : etudes de faisabilite « Analyse PLU — Zone UYb (Exincourt) », nom de fichier « ..._zone_UYb_... »
    zones = []
    for m in re.finditer(r"Analyse PLU\s*[—-]\s*Zone\s+(\S+)\s*\(([^)]+)\)", texte):
        z = f"{m.group(1)} ({m.group(2).strip()})"
        if z not in zones:
            zones.append(z)
    m_nom = re.search(r"zone[_\s-]+([A-Z]{1,3}[a-z0-9]{0,3})", nom)
    if zones:
        m = re.search(r"Analyse PLU\s*[—-]\s*Zone", texte)
        ajouter("zonage_plu", ", ".join(zones), m, 0.8)
    elif m_nom:
        ajouter("zonage_plu", m_nom.group(1), None, 0.7, extrait=f"nom du fichier : {nom}")

    # Permis de construire
    m = re.search(r"\bPC\s?\d{3}\s?\d{3}\s?\d{2}\s?[A-Z0-9]{5}\b", texte)
    if m:
        ajouter("permis_numero", re.sub(r"\s+", " ", m.group(0)), m, 0.8)

    # Societe : pas dans les documents d'administrations ou d'operateurs, dont le SIRET est le leur
    # (extrait cadastral DGFiP, etude RTE, reglement de PLU)
    if type_source not in ("cadastre", "etude_rte", "plu"):
        m = re.search(r"SIRET\D{0,12}(\d{3}\s?\d{3}\s?\d{3}\s?\d{5})", texte)
        if m:
            ajouter("demandeur_siret", m.group(1).replace(" ", ""), m, 0.6)
        m = re.search(r"\bFR\s?[0-9A-Z]{2}\s?\d{3}\s?\d{3}\s?\d{3}\b", texte)
        if m:
            ajouter("demandeur_tva", m.group(0).replace(" ", ""), m, 0.6)

    # Proprietaire
    m = re.search(r"[Pp]ropriétaire(?: actuel| foncier)?\s*:\s*([^\n]{3,80})", texte)
    if m:
        ajouter("proprietaire", m.group(1).strip(), m, 0.6)

    # Gaz et chantier
    m = re.search(r"(\d[\d\s]*(?:[,.]\d+)?)\s*(?:N?m3|Nm³|m³\s?\(n\))\s*/\s*h", texte)
    if m:
        ajouter("debit_gaz_nm3h", _nombre_fr(m.group(1)), m, 0.4)
    m = re.search(r"chantier[^\n]{0,60}?(\d[\d\s]*)\s*kVA", texte, re.I)
    if m:
        ajouter("puissance_chantier_kva", _nombre_fr(m.group(1)), m, 0.5)

    for p in props:
        p["valeur"] = fiche.normaliser(p["champ"], p["valeur"])
    return [p for p in props if p["valeur"] is not None]


# ------------------------------------------------------------------------ IA
def ia_disponible() -> bool:
    return ia.disponible()


def _consigne(nom: str, type_source: str, connu: dict, partie: str = "") -> str:
    champs = "\n".join(f"- {c[0]} : {c[1]}" + (f" ({c[4]})" if c[4] else "") for c in fiche.CHAMPS_FICHE)
    deja = "\n".join(f"- {k} = {v}" for k, v in connu.items() if v) or "(rien)"
    return f"""Tu aides a remplir la fiche d'un site de datacenter en France, pour les demandes de raccordement electrique
et gaz (RTE, Enedis, GRDF). Document : « {nom} » (type : {type_source}){partie}.

Champs possibles (cle : description) :
{champs}

Deja dans la fiche, pour contexte :
{deja}

Regles strictes :
- Ne renvoie QUE des valeurs ecrites dans le document. Aucune supposition. Si un champ n'y est pas, ne le renvoie pas.
- Le site est le terrain du projet datacenter. Le poste electrique, un operateur ou un client cite ne sont pas le site.
- Dans une etude RTE, le demandeur est un client tiers : n'en tire ni societe ni interlocuteur.
- Dates au format AAAA-MM-JJ. Nombres sans unite, point decimal (ex. 30.28).
- « extrait » : la phrase du document qui contient la valeur, recopiee mot pour mot, 200 caracteres au plus.
- « confiance » entre 0 et 1.

Reponds en JSON : {{"valeurs": [{{"champ": "cle", "valeur": "...", "extrait": "...", "confiance": 0.9}}]}}"""


SCHEMA_IA = {
    "type": "object",
    "properties": {"valeurs": {"type": "array", "items": {
        "type": "object",
        "properties": {"champ": {"type": "string", "enum": fiche.CLES}, "valeur": {"type": "string"},
                       "extrait": {"type": "string"}, "confiance": {"type": "number"}},
        "required": ["champ", "valeur", "extrait", "confiance"]}}},
    "required": ["valeurs"],
}


def _simplifier(t: str) -> str:
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", str(t)) if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[\s\u00a0\u202f]+", " ", t).strip()


def _retrouvee(champ: str, valeur: str, extrait: str, texte_simple: str) -> bool:
    """Garde-fou contre l'invention : la valeur (ou l'extrait cite) doit se lire dans le document."""
    if not texte_simple:
        return True  # image ou scan : rien a comparer
    ex = _simplifier(extrait)
    if len(ex) >= 15 and ex[:60] in texte_simple:
        return True
    v = _simplifier(valeur)
    if len(v) >= 3 and v in texte_simple:
        return True
    chiffres = re.sub(r"\D", "", valeur)
    if len(chiffres) >= 2 and chiffres in re.sub(r"\D", "", texte_simple):
        return True
    if fiche.TYPES.get(champ) == "number":
        try:
            n = float(valeur)
            variantes = {f"{n:g}", f"{n:g}".replace(".", ","), f"{n:,.0f}".replace(",", " ")}
            return any(_simplifier(x) in texte_simple for x in variantes)
        except ValueError:
            return False
    return False


def _morceaux(texte: str) -> list[str]:
    """Decoupe pour tenir dans le contexte du modele (environ 3 caracteres par jeton en francais)."""
    taille = max(6000, (ia.reglages()["contexte"] - 3500) * 3)
    if len(texte) <= taille:
        return [texte]
    out, i = [], 0
    while i < len(texte):
        out.append(texte[i:i + taille])
        i += taille - 800
    return out


def _pages_en_images(chemin: Path) -> list[bytes]:
    if not shutil.which("pdftoppm"):
        return []
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", str(RESOLUTION_VISION), "-png", "-f", "1", "-l", str(MAX_PAGES_VISION), str(chemin), f"{d}/p"],
                       capture_output=True, timeout=180)
        return [p.read_bytes() for p in sorted(Path(d).glob("p*.png"))]


def par_ia(chemin: Path, nom: str, texte: str, type_source: str, connu: dict) -> tuple[list[dict], dict]:
    """Propositions de l'IA et statistiques (appels, secondes). Leve ia.ErreurIA si le modele ne repond pas."""
    ext = chemin.suffix.lower()
    stats = {"appels": 0, "secondes": 0.0, "mode": ""}
    brutes: list[dict] = []
    texte_simple = ""
    if len(texte.strip()) >= 200:
        stats["mode"] = "texte"
        texte_simple = _simplifier(texte)
        parts = _morceaux(texte)
        for k, morceau in enumerate(parts, start=1):
            partie = f", partie {k} sur {len(parts)}" if len(parts) > 1 else ""
            rep, st = ia.demander_json(_consigne(nom, type_source, connu, partie) + f"\n\n<document>\n{morceau}\n</document>",
                                       schema=SCHEMA_IA)
            stats["appels"] += 1
            stats["secondes"] += st["secondes"]
            brutes += (rep.get("valeurs") if isinstance(rep, dict) else rep) or []
    elif ia.vision_disponible() and ext in (".pdf", ".png", ".jpg", ".jpeg", ".webp"):
        stats["mode"] = "vision"
        images = _pages_en_images(chemin) if ext == ".pdf" else [chemin.read_bytes()]
        if not images:
            return [], stats
        rep, st = ia.demander_json(_consigne(nom, type_source, connu, f", {len(images)} page(s) en image"), images=images,
                                   schema=SCHEMA_IA)
        stats["appels"] += 1
        stats["secondes"] += st["secondes"]
        brutes += (rep.get("valeurs") if isinstance(rep, dict) else rep) or []
    else:
        return [], stats
    meilleures: dict[tuple, dict] = {}
    ecartees: list[str] = []
    for p in brutes:
        if not isinstance(p, dict):
            continue
        champ = p.get("champ")
        if champ not in fiche.CLES:
            continue
        v = fiche.normaliser(champ, p.get("valeur"))
        if v is None:
            continue
        try:
            conf = max(0.0, min(1.0, float(p.get("confiance", 0.6))))
        except (TypeError, ValueError):
            conf = 0.6
        extrait = str(p.get("extrait") or "")[:300]
        if not _retrouvee(champ, v, extrait, texte_simple):
            ecartees.append(f"{champ} = {v}")
            continue  # introuvable dans le texte : probablement inventee, ecartee
        cle = (champ, v)
        if cle not in meilleures or conf > meilleures[cle]["confiance"]:
            meilleures[cle] = {"champ": champ, "valeur": v, "extrait": extrait, "confiance": round(conf * 0.9, 2)}
    stats["ecartees"] = ecartees
    return list(meilleures.values()), stats


def combiner(regles_: list[dict], ia_: list[dict]) -> list[dict]:
    """Les regles d'abord (calees sur le corpus). L'IA ajoute les champs absents ; sur un champ deja trouve,
    une valeur differente est gardee pour apparaitre comme divergence a arbitrer."""
    out = list(regles_)
    vus = {(p["champ"], str(p["valeur"])) for p in regles_}
    for p in ia_:
        if (p["champ"], str(p["valeur"])) in vus:
            continue
        out.append(p)
    return out


# ------------------------------------------------------------------- entree
def extraire(chemin: Path, nom: str, connu: dict | None = None) -> dict:
    """Lit un fichier source et propose des valeurs. Ne leve pas : l'erreur est rendue dans le resultat."""
    res = {"type_source": "autre", "methode": "", "propositions": [], "nb_caracteres": 0, "erreur": None}
    try:
        texte = lire_texte(chemin)
    except Exception as e:  # fichier corrompu, format inattendu
        texte = ""
        res["erreur"] = f"lecture impossible : {e}"
    res["nb_caracteres"] = len(texte)
    res["type_source"] = classer(nom, texte)
    par_r = par_regles(nom, texte, res["type_source"])
    res["methode"] = "regles"
    res["propositions"] = par_r
    if ia_disponible():
        try:
            par_i, st = par_ia(chemin, nom, texte, res["type_source"], connu or {})
            if st["appels"]:
                res["methode"] = "ia+regles" if par_r else "ia"
                res["propositions"] = combiner(par_r, par_i)
                res["ia"] = {**st, "secondes": round(st["secondes"], 1), "propositions": len(par_i)}
            elif len(texte.strip()) < 200 and not res["erreur"]:
                res["erreur"] = "pas de texte lisible et pas de modèle de vision configuré (AMONT_IA_MODELE_VISION)"
        except ia.ErreurIA as e:
            res["erreur"] = f"IA indisponible, règles seules : {e}"
        except Exception as e:  # reponse inattendue : on garde les regles
            res["erreur"] = f"IA en erreur ({type(e).__name__} : {e}), règles seules"
    elif len(texte.strip()) < 200 and not res["erreur"]:
        res["erreur"] = "pas de texte lisible (scan ou plan) : l'extraction par IA est nécessaire pour ce fichier"
    return res
