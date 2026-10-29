"""Fiche de renseignements « Grands Projets » de GRDF et courriel d'envoi.

Pour un datacenter, la premiere demarche gaz est toujours cette fiche, adressee a l'interlocuteur Grands Projets
de GRDF, meme quand le reseau est absent a proximite ou que le besoin depasse ce que GRDF distribue : GRDF
redirige ensuite vers NaTran. La fiche est un PDF a champs (AcroForm, 207 widgets) envoye par courriel, comme la D2.
Le modele (modeles/fiche_grdf_modele.pdf) est la fiche OM01 videe de ses valeurs ; les champs fixes (contact GRDF,
libelles, logo) sont conserves.

remplir() ecrit chaque champ depuis la fiche du site ; une valeur requise absente est ecrite « à compléter ».
Rien ne part sans relecture : la fiche sort en PDF, a relire, signer (page 2) et a joindre au courriel. courriel()
prepare le message d'envoi (.eml non envoye, X-Unsent) : le dernier clic, « Envoyer », reste humain.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

from . import d2

MODELE = Path(__file__).resolve().parent / "modeles" / "fiche_grdf_modele.pdf"
DESTINATAIRE_GRDF = "jean-baptiste.jedrusko@grdf.fr"
A_COMPLETER = "à compléter"
PCS_KWH_NM3 = 11.2  # pouvoir calorifique superieur du gaz naturel H, kWh/m3(n)
LIGNES_PROFIL = 10  # le tableau « année 1 à 10 » de la fiche

# Pieces joignables au courriel, dans l'ordre : (type de piece Amont, libelle).
PIECES_COURRIEL = [
    ("fiche_grdf", "la fiche de renseignements Grands Projets, complétée et signée"),
    ("plan_situation", "le plan de situation avec l'emplacement du poste gaz"),
    ("plan_cadastral_1000", "le plan cadastral au 1/1000e, format portrait"),
    ("plan_200", "le plan au 1/200e"),
    ("plan_2000", "le plan au 1/2000e"),
    ("kbis", "l'extrait Kbis de la société"),
    ("certificat_adressage", "le certificat d'adressage"),
]
TYPES_JOINTS = [t for t, _ in PIECES_COURRIEL]

P1 = "P1.Nouveau batiment."
_CB = "Check Box2.0.0.1.1.1.0.0."

# Champs texte : cle de donnees -> nom qualifie du champ PDF.
TEXTES = {
    "moa_societe": "exemple: Nom propre, SCI, SCCV, SNC,etc.0.0", "moa_siret": "siret.0", "moa_naf": "code naf.0",
    "contact_nom": "interlocuteur.0", "contact_fonction": "fonction.0", "contact_tel": "exemple: 01 00 00 00 00.0.1.1.0",
    "contact_portable": "exemple: 01 00 00 00 00.0.1.1.1.1.1.1", "contact_mail": "exemple: martinedupont(@)mail.com.0.1.1.1.1",
    "sign_societe": "exemple: Nom propre, SCI, SCCV, SNC,etc.0.1.0", "sign_siret": "siret.1.0", "sign_naf": "code naf.1",
    "sign_adresse": "fonction.1.1", "sign_nom": "interlocuteur.1.0", "sign_fonction": "fonction.1.0.0",
    "sign_tel": "exemple: 01 00 00 00 00.0.1.1.1.0.0", "sign_portable": "exemple: 01 00 00 00 00.0.1.1.1.0.1",
    "sign_mail": "exemple: martinedupont(@)mail.com.0.1.1.0",
    "site_nom": "interlocuteur.1.1.0", "site_fonction": "fonction.1.0.1", "site_tel": "exemple: 01 00 00 00 00.0.1.1.1.1.0",
    "site_portable": "exemple: 01 00 00 00 00.0.1.1.1.1.1.0", "site_mail": "exemple: martinedupont(@)mail.com.0.1.1.1.0",
    "projet_nom": "nom projet.0.0", "adresse_postale": "adresse postale.0", "adresse_physique": "adresse physique",
    "zac": "exemple: ZAC du Bon Temps Paris Sud", "lot": "exemple Lot 8a", "date_mes": "Date1.0", "date_poste": "Date1.1",
    "presentation": "nom projet.0.1",
    "batiment": P1 + 'Exemple: Projet " Les fleurs bleues" Batiment A1', "energie_autre": P1 + "autre.0",
    "pce": P1 + "PCE.0", "gi": P1 + "PCE.1.0", "besoin_autre": P1 + "autre.1.0.0",
    "puissance_installee_kw": P1 + "besoins.0", "puissance_min_mw": P1 + "Puissance.Minoimum.0",
    "puissance_max_mw": P1 + "Puissance.Minoimum.1", "conso_annuelle": P1 + "consommation.0",
    "conso_jour": P1 + "consommation.1.0.0", "pression_autre": P1 + "autre.1.0.1.0",
    "augmentation_kw": P1 + "consommation.1.0.1.0", "augmentation_date": P1 + "Date1.0", "augmentation_usage": P1 + "usages.0",
    "tranchees_ml": P1 + "usages.1.0", "solution_autre": P1 + "usages.1.1",
}
for _i, (_a, _b, _c, _d) in enumerate([("Nom société.0", "Interlocuteur.0", "téléphone.0", "MAil.0"),
                                       ("Nom société.1.0", "Interlocuteur.1", "téléphone.1", "MAil.1"),
                                       ("Nom société.2.0", "Interlocuteur.2", "téléphone.2", "MAil.2"),
                                       ("Nom société.3.0", "Interlocuteur.3", "téléphone.3", "MAil.3")]):
    TEXTES.update({f"interv{_i}_societe": _a, f"interv{_i}_nom": _b, f"interv{_i}_tel": _c, f"interv{_i}_mail": _d})
for _i in range(LIGNES_PROFIL):
    TEXTES[f"annee{_i}_conso"] = P1 + f"Consommation annuelle.{_i}"
    TEXTES[f"annee{_i}_jour"] = P1 + f"Consommation journélière.{_i}"

# Cases a cocher : cle de donnees -> nom qualifie ; une case est cochee quand la donnee vaut True.
CASES = {
    "neuf": "Check Box1.0.0", "existant": "Check Box1.0.1",
    "piece_situation": "Check Box1.1.3.0", "piece_cadastre": "Check Box1.1.2", "piece_kbis": "Check Box1.1.3.1.1",
    "piece_200": "Check Box1.1.3.1.0.0", "piece_adressage": "Check Box1.1.3.1.0.1", "piece_2000": "Check Box1.1.3.2.0",
    "dest_rcu": P1 + _CB + "1.0.1.0.0.1.0.0.0.0", "dest_datacenter": P1 + _CB + "1.0.1.0.0.1.0.0.0.2",
    "dest_autres": P1 + _CB + "1.0.1.0.0.1.0.0.0.3",
    "nrj_gaz": P1 + _CB + "1.0.1.0.0.0", "nrj_elec": P1 + _CB + "1.0.1.1", "nrj_rcu": P1 + _CB + "1.0.1.2",
    "nrj_bois": P1 + _CB + "1.0.1.3", "nrj_fioul": P1 + _CB + "1.0.1.4.0", "nrj_autre": P1 + _CB + "1.0.1.4.1",
    "besoin_process": P1 + _CB + "1.0.0.1.0.0", "besoin_chauffage": P1 + _CB + "1.0.0.1.1", "besoin_ecs": P1 + _CB + "1.0.0.1.2",
    "besoin_autre_case": P1 + _CB + "1.0.0.1.3.0",
    "pression_300": P1 + _CB + "1.0.0.1.0.1.1", "pression_fil": P1 + _CB + "1.0.0.1.0.1.2",
    "double_oui": P1 + _CB + "1.0.0.1.3.1.0.0", "double_non": P1 + _CB + "1.0.0.1.3.1.1",
    "redond_oui": P1 + _CB + "1.0.0.1.3.1.0.1", "redond_non": P1 + _CB + "1.0.0.1.3.1.0.2",
    "augm_non": P1 + "Check Box3", "augm_oui": P1 + "Check Box4",
    "poste_prive": P1 + _CB + "1.0.0.1.0.1.0.1.0", "poste_public": P1 + _CB + "1.0.0.1.0.1.0.1.1.0",
    "tranchees_client": P1 + _CB + "1.0.0.1.0.1.0.1.1.1.0", "tranchees_grdf": P1 + _CB + "1.0.0.1.0.1.0.1.1.1.1",
    "sol_chaudiere": P1 + _CB + "0.0.0.0", "sol_cogeneration": P1 + _CB + "0.0.0.1", "sol_pac_gaz": P1 + _CB + "0.0.0.2",
    "sol_pac_elec": P1 + _CB + "0.0.0.3", "sol_trigeneration": P1 + _CB + "0.0.0.4", "sol_biomasse": P1 + _CB + "0.0.0.5",
    "sol_solaire_th": P1 + _CB + "0.0.0.6", "sol_photovoltaique": P1 + _CB + "0.0.0.7", "sol_autres": P1 + _CB + "0.0.0.8",
}
CHOIX_SUPPRESSION = "supression de branchements"
SUPPRESSION_DEFAUT = "Pas de suppression/non concerné"

# Mots reconnus dans « solutions techniques » -> case.
SOLUTIONS = [
    ("sol_chaudiere", r"chaudi[eè]re"), ("sol_cogeneration", r"co-?g[eé]n[eé]ration"), ("sol_pac_gaz", r"pac\s+gaz|pompe.+gaz"),
    ("sol_pac_elec", r"pac\s+[eé]lectrique|pompe.+[eé]lectrique"), ("sol_trigeneration", r"tri-?g[eé]n[eé]ration"),
    ("sol_biomasse", r"biomasse"), ("sol_solaire_th", r"solaire\s+thermique"), ("sol_photovoltaique", r"photovolta"),
]

# Valeur requise absente : ecrite « à compléter » et listee dans manquants().
REQUIS = {
    "moa_societe": "maîtrise d'ouvrage ou raison sociale", "moa_siret": "SIRET", "contact_nom": "interlocuteur, nom",
    "contact_mail": "interlocuteur, courriel", "sign_adresse": "adresse d'envoi du devis", "sign_nom": "signataire",
    "projet_nom": "nom du projet", "adresse_postale": "adresse du projet", "date_mes": "date de mise en service souhaitée",
    "puissance_max_mw": "puissance appelée maximum", "conso_annuelle": "consommation annuelle", "presentation": "présentation du projet",
}


# ------------------------------------------------------------------ mise en forme
def _num(v) -> float | None:
    try:
        return float(str(v).replace(" ", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def milliers(v) -> str:
    """567800 -> « 567 800 » ; 20.2 -> « 20,2 »."""
    n = _num(v)
    if n is None:
        return str(v or "")
    if n.is_integer():
        return f"{int(n):,}".replace(",", " ")
    return f"{n:,.1f}".replace(",", " ").replace(".", ",")


def _oui_non(v) -> bool | None:
    t = str(v or "").strip().lower()
    if t in ("oui", "o", "true", "1", "yes"):
        return True
    if t in ("non", "n", "false", "0", "no"):
        return False
    return None


def _nom_prenom(prenom, nom) -> str:
    return " ".join(x for x in (str(prenom or "").strip(), str(nom or "").strip()) if x)


def _representant(rep: str) -> tuple[str, str]:
    """« David TAIEB, Gérant » -> (« David TAIEB », « Gérant »)."""
    nom, _, fonction = str(rep or "").partition(",")
    return nom.strip(), fonction.strip()


def profil(texte: str) -> list[tuple[str, str]]:
    """« 25800/12400 ; 51600/24800 » -> [(« 25 800 », « 12 400 »), ...]. Liste vide si illisible."""
    out = []
    for part in re.split(r"[;\n]+", texte or ""):
        m = re.match(r"\s*(?:ann[eé]e\s*\d+\s*[:=-]?\s*)?([\d\s.,]+?)\s*(?:MWh)?\s*[/:|]\s*([\d\s.,]+?)\s*(?:MWh)?\s*$", part)
        if m and _num(m.group(1)) is not None and _num(m.group(2)) is not None:
            out.append((milliers(m.group(1)), milliers(m.group(2))))
    return out[:LIGNES_PROFIL]


def presentation_defaut(v: dict) -> str:
    """Texte de la rubrique « Présentation projet » quand la fiche n'en porte pas : a relire."""
    site = v.get("nom_installation") or ""
    commune = v.get("commune") or ""
    societe = v.get("demandeur_societe") or ""
    morceaux = [f"Centre de données {site}" + (f" porté par {societe}" if societe else "") + (f" à {commune}" if commune else "") + "."]
    if v.get("parcelles"):
        morceaux.append(f"Parcelles {v['parcelles']}" + (f", soit {d2.nb(v['surface_ha'])} ha" if v.get("surface_ha") else "") + ".")
    if v.get("usage_gaz"):
        besoin = f"Le besoin en gaz porte sur : {v['usage_gaz']}."
        if v.get("debit_gaz_nm3h"):
            besoin += f" Débit maximal {milliers(v['debit_gaz_nm3h'])} m3(n)/h."
        morceaux.append(besoin)
    morceaux.append("Nous ne préjugeons pas de la solution de raccordement.")
    return " ".join(morceaux)


# ------------------------------------------------------------------ donnees de la fiche
def donnees(v: dict, demande: dict, pieces: list[dict], code: str) -> dict:
    """Toutes les cases de la fiche. v : valeurs typees de la fiche du site ; pieces : pieces du projet (types)."""
    types = {p["type"] for p in pieces}
    rep_nom, rep_fonction = _representant(v.get("demandeur_representant"))
    cp_ville = " ".join(x for x in (str(v.get("code_postal") or ""), str(v.get("commune") or "")) if x)
    siege = ", ".join(x for x in (v.get("demandeur_siege_adresse"), v.get("demandeur_siege_cp_ville")) if x)
    nom_site = str(v.get("nom_installation") or code)
    commune = str(v.get("commune") or "")
    projet = nom_site if not commune or commune.lower() in nom_site.lower() else f"{nom_site}, {commune}"
    if commune and v.get("departement") and f"({v['departement']})" not in projet:
        projet += f" ({v['departement']})"
    adresse = str(v.get("adresse") or "")
    adresse_postale = ", ".join(x for x in (adresse, cp_ville) if x)

    debit_max = _num(v.get("debit_gaz_nm3h"))
    debit_min = _num(v.get("debit_gaz_min_nm3h"))
    pmax = _num(v.get("gaz_puissance_max_mw"))
    if pmax is None and debit_max is not None:
        pmax = round(debit_max * PCS_KWH_NM3 / 1000, 1)
    pmin = _num(v.get("gaz_puissance_min_mw"))
    if pmin is None and debit_min is not None:
        pmin = round(debit_min * PCS_KWH_NM3 / 1000, 1)
    kw = _num(v.get("gaz_puissance_installee_kw"))
    if kw is None and pmax is not None:
        kw = round(pmax * 1000)
    annees = profil(v.get("gaz_profil_10_ans"))
    conso = v.get("gaz_conso_annuelle_mwh") or (annees[0][0] if annees else "")
    conso_jour = v.get("gaz_conso_jour_mwh") or (annees[0][1] if annees else "")

    pression = str(v.get("gaz_pression_demandee") or "").strip()
    if not pression and v.get("pression_gaz_bar") not in (None, ""):
        pression = f"{d2.nb(v['pression_gaz_bar'])} bar rel."
    p_low = pression.lower()
    pression_300 = bool(re.search(r"\b300\s*mbar", p_low))
    pression_fil = "fil du gaz" in p_low or "fil de l'eau" in p_low
    pression_autre = "" if (pression_300 or pression_fil) else pression

    solutions = str(v.get("gaz_solutions") or "")
    sol_cases = {k: bool(re.search(motif, solutions, re.I)) for k, motif in SOLUTIONS}
    reste = solutions
    for _, motif in SOLUTIONS:
        reste = re.sub(motif, "", reste, flags=re.I)
    reste = re.sub(r"^[\s,;/&+-]+|[\s,;/&+-]+$", "", re.sub(r"\s*[,;/]\s*[,;/]*\s*", ", ", reste)).strip(" ,;")
    if not solutions and v.get("usage_gaz"):
        reste = str(v["usage_gaz"])

    augmentation = _oui_non(v.get("gaz_augmentation"))
    domaine = str(v.get("gaz_poste_domaine") or "privé").lower()
    tranchees = str(v.get("gaz_tranchees") or "client").lower()
    zac = str(v.get("zac_nom") or "")

    x: dict = {
        "moa_societe": v.get("demandeur_societe") or "", "moa_siret": _siret(v.get("demandeur_siret")),
        "moa_naf": v.get("demandeur_naf") or "À confirmer",
        "contact_nom": _nom_prenom(v.get("interlocuteur_prenom"), v.get("interlocuteur_nom")), "contact_fonction": v.get("interlocuteur_fonction") or "",
        "contact_tel": v.get("interlocuteur_tel") or "", "contact_portable": v.get("interlocuteur_portable") or "",
        "contact_mail": v.get("interlocuteur_mail") or "",
        "sign_societe": "Identique à la MOA", "sign_siret": _siret(v.get("demandeur_siret")), "sign_naf": v.get("demandeur_naf") or "À confirmer",
        "sign_adresse": siege, "sign_nom": rep_nom, "sign_fonction": rep_fonction, "sign_tel": "", "sign_portable": "", "sign_mail": "",
        "site_nom": v.get("site_contact_nom") or "", "site_fonction": v.get("site_contact_fonction") or "",
        "site_tel": v.get("site_contact_tel") or "", "site_portable": v.get("site_contact_portable") or "",
        "site_mail": v.get("site_contact_mail") or "",
        "projet_nom": projet, "adresse_postale": adresse_postale,
        "adresse_physique": "Identique" + (f" - parcelles {v['parcelles']}" if v.get("parcelles") else ""),
        "zac": zac, "lot": str(v.get("zac_lot") or ("À préciser" if zac else "")),
        "date_mes": d2.date_fr(v.get("gaz_date_mise_en_service") or v.get("date_mise_a_disposition")),
        "date_poste": d2.date_fr(v.get("gaz_date_poste")),
        "presentation": str(v.get("gaz_presentation") or presentation_defaut(v)),
        "batiment": str(v.get("gaz_batiment") or nom_site),
        "energie_autre": "", "pce": "", "gi": "",
        "besoin_autre": str(v.get("usage_gaz") or ""),
        "puissance_installee_kw": milliers(kw) if kw is not None else "", "puissance_min_mw": milliers(pmin) if pmin is not None else "",
        "puissance_max_mw": milliers(pmax) if pmax is not None else "", "conso_annuelle": milliers(conso) if conso != "" else "",
        "conso_jour": milliers(conso_jour) if conso_jour != "" else "", "pression_autre": pression_autre,
        "augmentation_kw": milliers(v.get("gaz_augmentation_kw")) if v.get("gaz_augmentation_kw") not in (None, "") else "",
        "augmentation_date": str(v.get("gaz_augmentation_date") or ""), "augmentation_usage": str(v.get("gaz_augmentation_usage") or ""),
        "tranchees_ml": str(v.get("gaz_tranchees_ml") or "À définir"),
        "solution_autre": reste,
        "suppression": SUPPRESSION_DEFAUT,
        # cases
        "neuf": True, "existant": False,
        "piece_situation": "plan_situation" in types, "piece_cadastre": "plan_cadastral_1000" in types, "piece_kbis": "kbis" in types,
        "piece_200": "plan_200" in types, "piece_2000": "plan_2000" in types, "piece_adressage": "certificat_adressage" in types,
        "dest_rcu": False, "dest_datacenter": True, "dest_autres": False,
        "nrj_gaz": False, "nrj_elec": False, "nrj_rcu": False, "nrj_bois": False, "nrj_fioul": False, "nrj_autre": False,
        "besoin_process": False, "besoin_chauffage": False, "besoin_ecs": False, "besoin_autre_case": bool(v.get("usage_gaz")),
        "pression_300": pression_300, "pression_fil": pression_fil,
        "poste_prive": "public" not in domaine, "poste_public": "public" in domaine,
        "tranchees_client": "grdf" not in tranchees, "tranchees_grdf": "grdf" in tranchees,
        "sol_autres": bool(reste), **sol_cases,
    }
    dl, rd = _oui_non(v.get("gaz_double_ligne")), _oui_non(v.get("gaz_redondance"))
    x.update({"double_oui": dl is True, "double_non": dl is False, "redond_oui": rd is True, "redond_non": rd is False,
              "augm_oui": augmentation is True, "augm_non": augmentation is False})
    for i in range(LIGNES_PROFIL):
        x[f"annee{i}_conso"], x[f"annee{i}_jour"] = annees[i] if i < len(annees) else ("", "")
    for i in range(4):  # installateur, BE thermique, architecte : « À désigner » tant qu'ils ne sont pas choisis
        x.update({f"interv{i}_societe": "À désigner" if i < 3 else "", f"interv{i}_nom": "", f"interv{i}_tel": "", f"interv{i}_mail": ""})
    # contexte pour le courriel et les alertes (pas des champs du PDF)
    x["_debit_max"] = debit_max
    x["_annees"] = len(annees)
    x["_usage"] = str(v.get("usage_gaz") or "")
    x["_pression"] = pression
    x["_augmentation_kw"] = _num(v.get("gaz_augmentation_kw"))
    return x


def _siret(v) -> str:
    c = re.sub(r"\D", "", str(v or ""))
    if len(c) == 14:
        return f"{c[:3]} {c[3:6]} {c[6:9]} {c[9:]}"
    return str(v or "")


def manquants(x: dict) -> list[str]:
    out = [lib for k, lib in REQUIS.items() if not x.get(k)]
    if not x.get("pression_300") and not x.get("pression_fil") and not x.get("pression_autre"):
        out.append("pression d'alimentation en gaz")
    return out


def alertes_fiche(x: dict) -> list[str]:
    """Points a verifier avant l'envoi, sans rapport avec une case vide."""
    out = []
    if x["_annees"] and x["_annees"] < LIGNES_PROFIL:
        out.append(f"tableau de consommation : {x['_annees']} année(s) sur {LIGNES_PROFIL}, les suivantes restent vides")
    if not x["_annees"]:
        out.append("tableau de consommation années 1 à 10 vide : GRDF le demande pour dimensionner")
    if x["moa_naf"] == "À confirmer":
        out.append("code NAF « À confirmer » : à renseigner si connu (Kbis)")
    return out


# ------------------------------------------------------------------ ecriture du PDF
def _qualifie(annot) -> str:
    noms, o = [], annot
    while o is not None:
        o = o.get_object()
        if o.get("/T") is not None:
            noms.append(str(o["/T"]))
        o = o.get("/Parent")
    return ".".join(reversed(noms))


def _ajuster(texte: str, largeur: float, hauteur: float, multiligne: bool, maxi: float = 9.0) -> tuple[float, str]:
    """(taille en pt, texte) : plus grande taille qui fait tenir le texte dans la case, plancher 5 pt.
    Une case a plusieurs lignes recoit le texte deja coupe aux mots (le PDF ne le fait pas a l'ecriture)."""
    import textwrap
    taille = maxi
    while True:
        par_ligne = max(1, int((largeur - 4) / (taille * 0.42)))
        if not multiligne:
            if len(texte) <= par_ligne or taille <= 5.0:
                return taille, texte
        else:
            lignes = [l for p in texte.split("\n") for l in (textwrap.wrap(p, par_ligne) or [""])]
            if len(lignes) * taille * 1.15 <= hauteur - 1 or taille <= 5.0:
                return taille, "\n".join(lignes)
        taille -= 0.5


def _nom_pypdf(annot) -> str:
    """Nom sous lequel pypdf reconnait ce champ : le widget lui-meme s'il porte /FT et /T, sinon son parent.
    La fiche melange les deux structures (widget sous un champ, ou widget nomme sous un champ intermediaire)."""
    if "/FT" in annot and "/T" in annot:
        return _qualifie(annot)
    return _qualifie(annot["/Parent"]) if "/Parent" in annot else _qualifie(annot)


def traduction(w) -> dict[str, str]:
    """{nom qualifie du widget : nom reconnu par pypdf} pour tous les widgets du document."""
    out = {}
    for page in w.pages:
        for a in page.get("/Annots", []):
            a = a.get_object()
            if a.get("/Subtype") == "/Widget":
                out[_qualifie(a)] = _nom_pypdf(a)
    return out


def valeurs_pdf(x: dict) -> tuple[dict, dict]:
    """(champs texte, cases) a ecrire, par nom de champ PDF. Une valeur requise absente sort « à compléter »."""
    textes = {}
    for cle, champ in TEXTES.items():
        val = str(x.get(cle) or "")
        if cle in REQUIS and not val:
            val = A_COMPLETER
        textes[champ] = val
    if not x.get("pression_300") and not x.get("pression_fil") and not x.get("pression_autre"):
        textes[TEXTES["pression_autre"]] = A_COMPLETER
    textes[CHOIX_SUPPRESSION] = x.get("suppression") or SUPPRESSION_DEFAUT
    cases = {champ: ("/Yes" if x.get(cle) else "/Off") for cle, champ in CASES.items()}
    return textes, cases


def remplir(x: dict, modele: Path = MODELE) -> bytes:
    """La fiche remplie, en PDF. Les champs fixes du modele (contact GRDF, libelles, logo) sont conserves."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, TextStringObject

    textes, cases = valeurs_pdf(x)
    w = PdfWriter(clone_from=PdfReader(str(modele)))
    purger_apparences(w, {c for c, val in textes.items() if not val})
    for page in w.pages:
        for a in page.get("/Annots", []):
            a = a.get_object()
            nom = _qualifie(a)
            if nom not in textes or not textes[nom]:
                continue
            champ = a if "/DA" in a else a.get("/Parent", a).get_object()
            da = str(champ.get("/DA") or "")
            m = re.search(r"([\d.]+)\s+Tf", da)
            if not m:
                continue
            ff = int(a.get("/Ff") or (a["/Parent"].get_object().get("/Ff") if "/Parent" in a else 0) or 0)
            r = [float(c) for c in a["/Rect"]]
            taille, textes[nom] = _ajuster(textes[nom], r[2] - r[0], r[3] - r[1], bool(ff & 4096))
            champ[NameObject("/DA")] = TextStringObject(da[:m.start(1)] + f"{taille:g}" + da[m.end(1):])
    trad = traduction(w)
    for page in w.pages:
        w.update_page_form_field_values(page, {trad[c]: val for c, val in {**textes, **cases}.items()}, auto_regenerate=False)
    sortie = io.BytesIO()
    w.write(sortie)
    return sortie.getvalue()


def purger_apparences(w, noms) -> None:
    """Supprime l'apparence enregistree des champs texte dont le nom est dans noms : sans cela, un champ vide garde
    l'ancien texte dessine (pypdf ne redessine pas un champ vide)."""
    from pypdf.generic import NameObject
    for page in w.pages:
        for a in page.get("/Annots", []):
            a = a.get_object()
            if _qualifie(a) in noms and "/AP" in a:
                del a[NameObject("/AP")]


def noms_champs(modele: Path = MODELE) -> set[str]:
    """Noms qualifies des champs du modele (verification des correspondances)."""
    from pypdf import PdfReader
    return set((PdfReader(str(modele)).get_fields() or {}).keys())


# ------------------------------------------------------------------ courriel d'envoi
def courriel(v: dict, demande: dict, pieces: list[dict], destinataires: list[str], copie: list[str] | None = None) -> dict:
    """Objet, corps et liste ordonnee des pieces a joindre. pieces : pieces Amont (derniere version par type)."""
    x = donnees(v, demande, pieces, demande.get("projet_code") or "")
    site = v.get("nom_installation") or demande.get("projet_code") or ""
    commune = v.get("commune") or demande.get("commune") or ""
    dep = v.get("departement") or demande.get("departement") or ""
    lieu = f"{commune} ({dep})" if dep else commune
    objet = f"{lieu}, {site} : demande de raccordement gaz, fiche de renseignements Grands Projets"
    choisies = choisir_pieces(pieces)
    libelles = dict(PIECES_COURRIEL)
    corps = ["Bonjour,", ""]
    corps.append(f"Je vous prie de bien vouloir trouver ci-joint la fiche de renseignements Grands Projets relative au projet de centre de "
                 f"données {site}" + (f", situé à {lieu}" if lieu else "") + ".")
    corps.append("")
    besoin = []
    if x["_usage"]:
        besoin.append(f"Le besoin en gaz concerne l'usage suivant : {x['_usage'][:1].lower() + x['_usage'][1:]}")
    if x["puissance_max_mw"]:
        besoin.append(f"une puissance maximale appelée de {x['puissance_max_mw']} MWPCS" + (f" (soit {milliers(x['_debit_max'])} m3(n)/h)" if x["_debit_max"] else ""))
    if x["_pression"]:
        besoin.append(f"à une pression de {x['_pression']}")
    if x["date_mes"]:
        besoin.append(f"pour une mise en service souhaitée au {x['date_mes']}")
    if besoin:
        corps.append(", ".join(besoin) + ".")
    if x["augm_oui"] and x["_augmentation_kw"]:
        corps.append(f"Une montée en puissance est prévue, jusqu'à {milliers(x['_augmentation_kw'])} kW PCS"
                     + (f" ({x['augmentation_date']})" if x["augmentation_date"] else "") + ".")
    if besoin or (x["augm_oui"] and x["_augmentation_kw"]):
        corps.append("")
    corps.append("Nous ne préjugeons pas de la solution de raccordement et restons disponibles pour tout échange utile à l'étude "
                 "du dossier, y compris s'il devait relever du transport.")
    corps.append("")
    if choisies:
        corps += ["Le dossier comprend les pièces suivantes :", ""]
        for i, p in enumerate(choisies, 1):
            corps.append(f"{i}. {libelles.get(p['type'], p['nom_fichier'])} ;")
        corps[-1] = corps[-1][:-2] + "."
        corps.append("")
    corps += ["Vous remerciant de votre retour, je vous souhaite une excellente journée.", "", "Cordialement,", ""]
    nom = _nom_prenom(v.get("interlocuteur_prenom"), v.get("interlocuteur_nom"))
    corps += [y for y in (nom, v.get("interlocuteur_fonction"), v.get("interlocuteur_tel"), v.get("interlocuteur_mail")) if y]
    taille = sum(p.get("taille_octets") or 0 for p in choisies)
    alertes = []
    fiches = [p for p in choisies if p["type"] == "fiche_grdf"]
    if not fiches:
        alertes.append("fiche GRDF absente : la générer, la relire, la signer (page 2) et la joindre")
    elif not any("sign" in p["nom_fichier"].lower() for p in fiches):
        alertes.append("la fiche jointe est la version générée, non signée : déposer le PDF signé (type fiche grdf, nom contenant « signee »)")
    if not any(p["type"] == "plan_situation" for p in choisies):
        alertes.append("plan de situation avec l'emplacement du poste gaz absent")
    if not any(p["type"] == "plan_cadastral_1000" for p in choisies):
        alertes.append("plan cadastral au 1/1000e en portrait absent : le générer depuis le bloc GRDF (cadastre.gouv.fr)")
    if taille > d2.TAILLE_MAX_COURRIEL:
        alertes.append(f"pièces de {taille // (1024 * 1024)} Mo au total : au-delà de 15 Mo, envoyer par lien de transfert")
    return {"a": destinataires, "cc": copie or [], "objet": objet, "corps": "\n".join(corps), "pieces": choisies,
            "taille_octets": taille, "alertes": alertes}


def choisir_pieces(pieces: list[dict]) -> list[dict]:
    """Derniere version de chaque type joignable ; pour la fiche, la version signee l'emporte sur la version generee."""
    dernieres: dict[str, dict] = {}
    for p in sorted(pieces, key=lambda y: (y.get("ajoute_le") or "", y["id"])):
        if p["type"] not in TYPES_JOINTS:
            continue
        if p["type"] == "fiche_grdf" and "fiche_grdf" in dernieres:
            deja_signee = "sign" in dernieres["fiche_grdf"]["nom_fichier"].lower()
            if deja_signee and "sign" not in p["nom_fichier"].lower():
                continue
        dernieres[p["type"]] = p
    return [dernieres[t] for t in TYPES_JOINTS if t in dernieres]


eml = d2.eml
