"""Regles metier d'Amont : filieres, statuts, echeances, alertes, article 105.

Module unique, sans dependance, partage par l'API, le courriel du matin et les robots.
Les dates sont manipulees en ISO 8601 (AAAA-MM-JJ). Jours ouvres : lundi a vendredi,
sans feries dans un premier temps (voir cahier des charges du 17/09/2026, section 3).
"""

from __future__ import annotations

import calendar
import json
import os
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Filieres et statuts
# ---------------------------------------------------------------------------

FILIERES: dict[str, dict] = {
    "rte_ee": {
        "libelle": "RTE étude exploratoire",
        "court": "RTE EE",
        "dimension": "MW",
        "etapes": [
            ("brouillon", "Dossier en préparation", "Pièces + contrôle art. 105"),
            ("pret_validation", "Prêt pour validation", "Portail pré-rempli, clic humain"),
            ("depose", "Déposé", "Recevabilité sous 8 j. ouvrés"),
            ("recevable", "Étude en cours", "6 semaines annoncées"),
            ("etude_recue", "Étude reçue", "Gratuite, sans file d'attente"),
            ("confirmation_demandee", "Confirmation demandée", "Réponse sous 15 j. ouvrés"),
            ("clos", "Clos", "Relais vers la PTF"),
        ],
    },
    "rte_ptf": {
        "libelle": "RTE PTF, fiche D2",
        "court": "RTE PTF",
        "dimension": "MW",
        "etapes": [
            ("brouillon", "Dossier en préparation", "D2, GPS, unifilaire, 42 k€ HT"),
            ("pret_validation", "Prêt pour envoi", "Courriel préparé, envoi humain"),
            ("depose", "Déposé", "Recevabilité sous 8 j. ouvrés"),
            ("recevable", "PTF en instruction", "3 mois"),
            ("ptf_recue", "PTF reçue", "Validité 3 mois, +3 sur demande"),
            ("file_attente", "File d'attente", "Maintien annuel, 1 k€/MW"),
            ("convention", "Convention", "Raccordement puis exploitation"),
        ],
    },
    "enedis": {
        "libelle": "Enedis",
        "court": "Enedis",
        "dimension": "kVA",
        "etapes": [
            ("brouillon", "Dossier en préparation", "Permis, plan de masse, puissance"),
            ("pret_validation", "Prêt pour validation", "Portail pré-rempli, clic humain"),
            ("depose", "Déposé", "Dossier complet sous 3 mois"),
            ("qualifiee", "Qualifiée", "PDR sous 1 ou 3 mois"),
            ("pdr_recue", "PDR reçue", "Validité 3 mois, acompte"),
            ("acceptee", "Acceptée", "Convention sous 9 mois, 12 si RTE"),
            ("convention", "Convention", "Travaux"),
            ("mise_en_service", "Mise en service", "CONSUEL, 10 j. ouvrés"),
        ],
    },
    "grdf": {
        "libelle": "GRDF",
        "court": "GRDF",
        "dimension": "Nm³/h",
        "etapes": [
            ("brouillon", "Fiche en préparation", "Fiche Grands Projets : site, gaz, plans"),
            ("pret_validation", "Prêt pour envoi", "Fiche et courriel préparés, envoi humain"),
            ("depose", "Envoyée", "Réponse de GRDF, ou redirection vers NaTran"),
            ("redirige_natran", "Redirigé vers NaTran", "NaTran prend le relais"),
            ("devis_recu", "Devis reçu", "Signature en ligne"),
            ("accepte", "Accepté", "Acompte, planification"),
            ("travaux", "Travaux", "10 j. ouvrés à 2 mois"),
            ("mise_en_service", "Mise en service", "Qualigaz, PCE, fournisseur"),
        ],
    },
    "natran": {
        "libelle": "NaTran (ex-GRTgaz)",
        "court": "NaTran",
        "dimension": "Nm³/h",
        "etapes": [
            ("brouillon", "Dossier en préparation", "Débits, pression, plans, foncier"),
            ("pret_validation", "Prêt pour envoi", "Courriel préparé, envoi humain"),
            ("depose", "Demande envoyée", "Étude préliminaire gratuite"),
            ("faisabilite", "Étude de faisabilité", "Convention payante, date contractuelle"),
            ("rapport_recu", "Rapport reçu", "Convention d'études sous 6 mois"),
            ("etudes_raccordement", "Études de raccordement", "Étude de base, offre"),
            ("contrat", "Contrat", "Travaux puis mise en service"),
            ("mise_en_service", "Mise en service", ""),
        ],
    },
}

ORDRE_FILIERES_BASE = ["rte_ee", "rte_ptf", "enedis", "grdf"]
FILIERES_OPTIONNELLES = ["natran"]


def _lire_config() -> dict:
    """amont_config.json a la racine d'Amont (ou AMONT_CONFIG). Absent : valeurs par defaut."""
    chemin = Path(os.environ.get("AMONT_CONFIG", Path(__file__).resolve().parent.parent / "amont_config.json"))
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


CONFIG = _lire_config()
ORDRE_FILIERES = ORDRE_FILIERES_BASE + [f for f in FILIERES_OPTIONNELLES if f in CONFIG.get("filieres_optionnelles", [])]
HORS_CHAINE = {"irrecevable": "Irrecevable", "abandonne": "Abandonné"}

# Statuts qui exigent des pieces : le passage a "depose" est refuse si une piece
# obligatoire manque (cahier des charges, 2.6).
PIECES_OBLIGATOIRES_POUR_DEPOT: dict[str, list[str]] = {
    "rte_ee": ["extrait_cadastral"],
    "rte_ptf": ["fiche_d2", "unifilaire", "preuve_virement"],
    "enedis": ["extrait_cadastral", "plan_masse"],
    "grdf": ["fiche_grdf"],
    "natran": [],
}

TYPES_PIECES = [
    "extrait_cadastral", "plan_situation", "plan_implantation", "plan_installation", "unifilaire", "permis", "preuve_virement",
    "fiche_d2", "fiche_grdf", "kbis", "plan_200", "plan_2000", "certificat_adressage", "annexe_cartes", "planning", "montee_en_charge", "mandat", "plan_masse", "photo_environnement",
    "etude_recue", "ptf", "pdr", "devis", "convention", "rapport_faisabilite", "autre",
]

# Champs specifiques a chaque filiere, stockes dans la colonne JSON "donnees".
CHAMPS_FILIERE: dict[str, list[str]] = {
    "rte_ee": [
        "puissance_mw", "hypothese_secondaire_mw", "d_km", "num_etude", "date_recevabilite",
        "date_etude_recue", "date_relance", "date_confirmation_demandee",
        "date_confirmation_recue", "solution", "cout_total_keur", "cout_client_keur",
        "delai_mois",
    ],
    "rte_ptf": [
        "puissance_mw", "d_km", "ref_etude_exploratoire", "gps_lat", "gps_lon",
        "alimentations_supplementaires", "date_virement", "date_recevabilite",
        "date_ptf_recue", "prorogation_ptf", "date_ptf_acceptee", "date_convention_signee",
        "nb_versements_forfaitaires", "date_signature_fasttrack", "date_permis_obtenu",
        "num_ptf", "poste_raccordement", "tension_raccordement_kv", "cout_total_keur", "cout_client_keur", "acompte_keur",
        "delai_mois", "delai_reduit_mois", "limitations_temporaires",
    ],
    "enedis": [
        "type_enedis", "puissance_kva", "complexite", "ouvrages_rte", "ref_dossier",
        "date_qualification", "date_pdr_recue", "date_pdr_acceptee", "date_convention_signee",
        "date_mise_en_service", "cout_client_keur",
    ],
    "grdf": [
        "debit_nm3h", "usage_gaz", "etude_requise", "ref_dossier", "date_devis_recu",
        "date_relance", "date_devis_accepte", "date_travaux_prevue", "date_mise_en_service",
        "cout_client_keur",
    ],
    "natran": [
        "debit_nm3h", "debit_min_nm3h", "pression_bar", "usage_gaz", "ref_dossier",
        "date_rapport_prevu", "date_rapport_recu", "date_convention_etudes",
        "date_offre_recue", "date_contrat_signe", "date_mise_en_service",
        "cout_etudes_keur", "cout_client_keur",
    ],
}


def filiere_valide(f: str | None) -> str:
    return f if f in FILIERES else "rte_ee"


def statuts_de(filiere: str) -> list[str]:
    return [e[0] for e in FILIERES[filiere_valide(filiere)]["etapes"]] + list(HORS_CHAINE)


def libelle_statut(filiere: str, statut: str) -> str:
    for cle, lib, _ in FILIERES[filiere_valide(filiere)]["etapes"]:
        if cle == statut:
            return lib
    return HORS_CHAINE.get(statut, statut or "")


# ---------------------------------------------------------------------------
# Article 105 de l'arrete du 9 juin 2020 : domaine de tension impose
# ---------------------------------------------------------------------------

DOMAINES = [
    {"n": "HTA", "seuil": 40, "K": 100, "u": "20 kV"},
    {"n": "HTB1", "seuil": 100, "K": 1000, "u": "63 / 90 kV"},
    {"n": "HTB2", "seuil": 400, "K": 10000, "u": "150 / 225 kV"},
]


def article_105(puissance_mw: float | None, d_km: float | None) -> dict | None:
    """Domaine de tension impose. Prac < min(seuil absolu, K/d)."""
    if not puissance_mw:
        return None
    for dom in DOMAINES:
        par_distance = dom["K"] / d_km if d_km and d_km > 0 else float("inf")
        if puissance_mw < min(dom["seuil"], par_distance):
            return {"n": dom["n"], "u": dom["u"]}
    return {"n": "HTB3", "u": "400 kV"}


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def lire_date(s) -> date | None:
    if not s or not isinstance(s, str) or len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def ajouter_jours_ouvres(d: date, n: int) -> date:
    c = d
    reste = n
    while reste > 0:
        c += timedelta(days=1)
        if c.weekday() < 5:
            reste -= 1
    return c


def ajouter_jours(d: date, n: int) -> date:
    return d + timedelta(days=n)


def ajouter_semaines(d: date, n: int) -> date:
    return d + timedelta(weeks=n)


def ajouter_mois(d: date, n: int) -> date:
    mois = d.month - 1 + n
    annee = d.year + mois // 12
    mois = mois % 12 + 1
    jour = min(d.day, calendar.monthrange(annee, mois)[1])
    return date(annee, mois, jour)


def previsionnel_semaines(puissance_mw: float) -> int:
    """Delai reel de remise d'une etude exploratoire, calibre sur le corpus (note du 03/09)."""
    if puissance_mw < 100:
        return 7
    if puissance_mw < 400:
        return 10
    return 16


# ---------------------------------------------------------------------------
# Echeances
# ---------------------------------------------------------------------------

def _nombre(v) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def echeances(d: dict, aujourdhui: date | None = None) -> list[dict]:
    """Liste des echeances d'une demande (dict aplati : colonnes + donnees).

    Chaque echeance : libelle, date (ISO), fait (bool), jours (relatif a aujourd'hui,
    negatif si depassee), severite (info, warn sous 14 jours, crit si depassee et non faite).
    """
    auj = aujourdhui or date.today()
    out: list[dict] = []

    def push(libelle: str, e: date | None, fait) -> None:
        if not e:
            return
        j = (e - auj).days
        fait_b = bool(fait)
        sev = "info"
        if not fait_b:
            if j < 0:
                sev = "crit"
            elif j <= 14:
                sev = "warn"
        out.append({"libelle": libelle, "date": e.isoformat(), "fait": fait_b, "jours": j, "severite": sev})

    f = filiere_valide(d.get("filiere"))
    mw = _nombre(d.get("puissance_mw"))
    depot = lire_date(d.get("date_depot"))
    g = lambda k: lire_date(d.get(k))  # noqa: E731

    if f == "rte_ee":
        recev, etude = g("date_recevabilite"), g("date_etude_recue")
        conf_d, conf_r = g("date_confirmation_demandee"), g("date_confirmation_recue")
        if depot:
            push("Recevabilité RTE, 8 jours ouvrés", ajouter_jours_ouvres(depot, 8), recev or etude)
        base = recev or depot
        if base:
            push("Remise de l'étude, délai annoncé de 6 semaines", ajouter_semaines(base, 6), etude)
            p = previsionnel_semaines(mw)
            push(f"Remise de l'étude, prévisionnel calibré à {p} semaines", ajouter_semaines(base, p), etude)
            if not etude:
                push("Relance écrite à viser sur l'article 1.2.2", ajouter_semaines(base, 6), g("date_relance"))
        if conf_d:
            push("Réponse RTE sur la confirmation de solution, 15 jours ouvrés", ajouter_jours_ouvres(conf_d, 15), conf_r)

    elif f == "rte_ptf":
        recev, ptf_r = g("date_recevabilite"), g("date_ptf_recue")
        ptf_a, conv, ft = g("date_ptf_acceptee"), g("date_convention_signee"), g("date_signature_fasttrack")
        proro = bool(d.get("prorogation_ptf"))
        if depot:
            push("Recevabilité de la D2, 8 jours ouvrés (fiche complète et virement reçu)", ajouter_jours_ouvres(depot, 8), recev or ptf_r)
        base = recev or depot
        if base:
            push("Remise de la PTF, 3 mois", ajouter_mois(base, 3), ptf_r)
        if ptf_r:
            validite = 6 if proro else 3
            push(f"Fin de validité de la PTF, {validite} mois" + (" (prorogée)" if proro else ""), ajouter_mois(ptf_r, validite), ptf_a)
            if not ptf_a and not proro:
                push("Dernier jour pour demander la prorogation de 3 mois", ajouter_mois(ptf_r, 3), False)
        if ptf_a and not conv:
            p = ptf_a
            while p <= auj:
                p = ajouter_mois(p, 12)
            push("Maintien en file d'attente : justificatif d'avancement ou 1 k€/MW", p, False)
            push("Fin des justificatifs de phase d'étude, 24 mois après acceptation", ajouter_mois(ptf_a, 24), False)
        if ft:
            push("Permis de construire à obtenir, 15 mois après signature fast-track", ajouter_mois(ft, 15), g("date_permis_obtenu"))

    elif f == "enedis":
        qual, pdr = g("date_qualification"), g("date_pdr_recue")
        acc, conv = g("date_pdr_acceptee"), g("date_convention_signee")
        if depot:
            push("Dossier complet à fournir, 3 mois (qualification)", ajouter_mois(depot, 3), qual or pdr)
        if qual:
            m = 3 if d.get("complexite") == "etude" else 1
            push(f"Proposition de raccordement Enedis, {m} mois", ajouter_mois(qual, m), pdr)
        if pdr:
            push("Fin de validité de la PDR, 3 mois, acompte à verser", ajouter_mois(pdr, 3), acc)
        if acc:
            m = 12 if d.get("ouvrages_rte") else 9
            push(f"Convention de raccordement, {m} mois" + (" (ouvrages RTE)" if d.get("ouvrages_rte") else ""), ajouter_mois(acc, m), conv)
        if conv:
            push("Convention à accepter, validité 3 mois", ajouter_mois(conv, 3), g("date_mise_en_service"))

    elif f == "grdf":
        devis, acc = g("date_devis_recu"), g("date_devis_accepte")
        if depot:
            # Grands Projets : aucun delai de reponse publie, on ne calcule que la relance
            if not devis and d.get("statut") != "redirige_natran":
                push("Relance de GRDF Grands Projets sans réponse", ajouter_jours(depot, 15), g("date_relance"))
        if devis:
            push("Fin de validité du devis, 3 mois (à confirmer sur l'offre)", ajouter_mois(devis, 3), acc)
        travaux = g("date_travaux_prevue")
        if acc and travaux:
            push("Début des travaux prévu", travaux, g("date_mise_en_service"))

    elif f == "natran":
        # Delais NaTran client final : seuls ceux ecrits dans les conventions types 2025 sont calcules.
        # La date de remise du rapport de faisabilite est contractuelle, propre a chaque convention.
        rapport = g("date_rapport_recu")
        prevu = g("date_rapport_prevu")
        if prevu:
            push("Remise du rapport de faisabilité, date contractuelle", prevu, rapport)
        if rapport:
            push("Convention d'études de raccordement à signer, 6 mois après le rapport", ajouter_mois(rapport, 6), g("date_convention_etudes"))
        if depot and not prevu and not rapport:
            push("Réponse à la demande, à relancer après 1 mois", ajouter_mois(depot, 1), g("date_offre_recue"))

    out.sort(key=lambda e: e["date"])
    return out


def prochaine_echeance(d: dict, aujourdhui: date | None = None) -> dict | None:
    for e in echeances(d, aujourdhui):
        if not e["fait"]:
            return e
    return None


def alertes(d: dict, aujourdhui: date | None = None) -> list[dict]:
    """Alertes d'une demande : echeances depassees ou proches, et alertes hors echeancier."""
    out: list[dict] = []
    for e in echeances(d, aujourdhui):
        if e["fait"]:
            continue
        if e["jours"] < 0:
            out.append({"severite": "crit", "texte": f"{e['libelle']} : dépassée de {-e['jours']} jours", "cle": e["libelle"]})
        elif e["jours"] <= 14:
            out.append({"severite": "warn", "texte": f"{e['libelle']} : dans {e['jours']} jours", "cle": e["libelle"]})
    statut = d.get("statut")
    if statut == "irrecevable":
        out.append({"severite": "crit", "texte": "Dossier déclaré irrecevable, pièce à compléter sans délai", "cle": "irrecevable"})
    if statut == "pret_validation":
        out.append({"severite": "warn", "texte": "Dossier préparé, en attente de votre validation d'envoi", "cle": "pret_validation"})
    f = filiere_valide(d.get("filiere"))
    if f == "rte_ptf":
        n = int(_nombre(d.get("nb_versements_forfaitaires")))
        if n >= 2:
            out.append({"severite": "crit", "texte": "Faculté de versement forfaitaire épuisée : seul un justificatif d'avancement maintient le rang", "cle": "versements"})
        elif n == 1:
            out.append({"severite": "warn", "texte": "Un versement forfaitaire déjà utilisé, il n'en reste qu'un", "cle": "versements"})
    if f == "grdf" and _nombre(d.get("debit_nm3h")) > 650:
        out.append({"severite": "info", "texte": "Débit au-delà des classes standard GRDF : la fiche GRDF reste la première démarche, GRDF redirige ensuite vers NaTran (ex-GRTgaz)", "cle": "grtgaz"})
    return out


# ---------------------------------------------------------------------------
# Suivi des dossiers : prochaine action et echanges (0.3, 26/10/2026)
# ---------------------------------------------------------------------------

SENS_ECHANGE = {"envoye": "Envoyé", "recu": "Reçu", "note": "Note"}
CANAUX_ECHANGE = {"mail": "Courriel", "telephone": "Téléphone", "portail": "Portail opérateur",
                  "courrier": "Courrier", "reunion": "Réunion"}
DELAI_RELANCE_JOURS = int(CONFIG.get("delai_relance_jours", 10))

# Action attendue de notre cote a chaque etape, par filiere. Vide : rien a faire.
ACTIONS: dict[str, dict[str, str]] = {
    "rte_ee": {
        "brouillon": "Compléter la D1 et la déposer sur le Portail RTE",
        "pret_validation": "Relire le formulaire pré-rempli et l'envoyer",
        "depose": "Attendre l'accusé de recevabilité RTE",
        "recevable": "Attendre l'étude exploratoire",
        "etude_recue": "Analyser l'étude, décider : PTF ou arrêt",
        "confirmation_demandee": "Attendre la confirmation de solution RTE",
        "clos": "Préparer la demande de PTF",
    },
    "rte_ptf": {
        "brouillon": "Remplir la D2, virer 42 k€ HT, joindre l'unifilaire",
        "pret_validation": "Relire le courriel D2 et l'envoyer",
        "depose": "Attendre la recevabilité de la D2",
        "recevable": "Attendre la PTF",
        "ptf_recue": "Accepter la PTF, la proroger ou renoncer",
        "file_attente": "Justifier le maintien annuel en file",
        "convention": "Suivre la convention et les travaux",
    },
    "enedis": {
        "brouillon": "Monter le dossier sur le portail Enedis",
        "pret_validation": "Relire le portail pré-rempli et valider",
        "depose": "Compléter le dossier jusqu'à la qualification",
        "qualifiee": "Attendre la proposition de raccordement",
        "pdr_recue": "Accepter la PDR et verser l'acompte",
        "acceptee": "Attendre la convention de raccordement",
        "convention": "Suivre les travaux, préparer le CONSUEL",
        "mise_en_service": "",
    },
    "grdf": {
        "brouillon": "Générer la fiche GRDF et préparer le courriel",
        "pret_validation": "Relire, signer la fiche puis envoyer le courriel à GRDF",
        "depose": "Attendre la réponse de GRDF ou sa redirection vers NaTran",
        "redirige_natran": "Ouvrir la demande NaTran avec la réponse de GRDF",
        "devis_recu": "Signer le devis avant expiration",
        "accepte": "Planifier les travaux avec GRDF",
        "travaux": "Suivre les travaux",
        "mise_en_service": "",
    },
    "natran": {
        "brouillon": "Réunir débits, pression, plans et foncier",
        "pret_validation": "Relire le courriel et l'envoyer à NaTran",
        "depose": "Attendre la réponse NaTran",
        "faisabilite": "Attendre le rapport de faisabilité",
        "rapport_recu": "Signer la convention d'études sous 6 mois",
        "etudes_raccordement": "Attendre l'offre de raccordement",
        "contrat": "Suivre les travaux",
        "mise_en_service": "",
    },
}
ACTIONS_HORS_CHAINE = {"irrecevable": "Compléter le dossier déclaré irrecevable et le redéposer", "abandonne": ""}
# Etapes ou la balle est chez l'operateur : l'action est une attente, pas un geste.
ETAPES_ATTENTE = {"depose", "recevable", "confirmation_demandee", "qualifiee", "acceptee", "faisabilite", "etudes_raccordement"}


VALIDATION_REQUISE = bool(CONFIG.get("validation_requise", True))
VALIDEURS = list(CONFIG.get("valideurs") or [])
ETAPES_AVANT_ENVOI = {"brouillon", "pret_validation", "irrecevable"}


def _nom_simple(n: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(n or "")) if unicodedata.category(c) != "Mn").lower().strip()


def peut_valider(qui: str) -> bool:
    """Liste valideurs vide : tout le monde. Sinon le nom (ou l'adresse) doit correspondre a une entree :
    « Brayane » suffit pour « Brayane Obadia »."""
    if not VALIDEURS:
        return True
    n = _nom_simple(qui)
    if len(n) < 3 or n == "interne":
        return False
    for v in VALIDEURS:
        v = _nom_simple(v)
        if n == v or n in v.split() or v in n or n.split("@")[0] in v.replace(" ", "."):
            return True
    return False


def prochaine_action(d: dict, pieces_manquantes: list[str] | None = None, attente: dict | None = None,
                     aujourdhui: date | None = None, validation: dict | None = None) -> dict:
    """Ce qu'il faut faire maintenant sur une demande.

    Ordre de priorite : action saisie a la main, echeance depassee, relance ecrite RTE due,
    courriel sans reponse au-dela du delai de relance, pieces manquantes, action de l'etape.
    Retour : {texte, niveau (crit, warn, info, attente, fait), source}.
    """
    manuelle = (d.get("prochaine_action") or "").strip()
    if manuelle:
        return {"texte": manuelle, "niveau": "info", "source": "manuel"}
    f = filiere_valide(d.get("filiere"))
    statut = d.get("statut") or "brouillon"
    ech = [e for e in echeances(d, aujourdhui) if not e["fait"]]
    for e in ech:
        if e["jours"] < 0 and not e["libelle"].startswith("Remise de l'étude, délai annoncé"):
            if e["libelle"].startswith("Relance écrite"):
                return {"texte": "Relancer RTE par écrit, en visant l'article 1.2.2", "niveau": "crit", "source": "echeance"}
            return {"texte": "En retard : " + e["libelle"].split(",")[0], "niveau": "crit", "source": "echeance"}
    if attente and attente.get("jours", 0) >= DELAI_RELANCE_JOURS:
        qui = attente.get("contact") or "l'opérateur"
        return {"texte": f"Relancer {qui}, sans réponse depuis {attente['jours']} jours", "niveau": "warn", "source": "echange"}
    if attente and attente.get("relance_le") and attente["relance_le"] <= (aujourdhui or date.today()).isoformat():
        return {"texte": "Relance prévue : " + (attente.get("objet") or "courriel en attente"), "niveau": "warn", "source": "echange"}
    if VALIDATION_REQUISE and validation is not None and statut in ETAPES_AVANT_ENVOI and not pieces_manquantes:
        etat = validation.get("etat")
        if etat == "demandee":
            return {"texte": "En attente de la validation du responsable", "niveau": "attente", "source": "validation"}
        if etat == "perimee":
            return {"texte": "Dossier modifié depuis la validation : la redemander", "niveau": "warn", "source": "validation"}
        if etat == "refusee":
            return {"texte": "Validation refusée : " + (validation.get("commentaire") or "voir le commentaire du responsable"),
                    "niveau": "crit", "source": "validation"}
        if etat != "validee" and statut == "brouillon":
            return {"texte": "Dossier complet : demander la validation du responsable", "niveau": "warn", "source": "validation"}
    texte = ACTIONS.get(f, {}).get(statut, ACTIONS_HORS_CHAINE.get(statut, ""))
    if statut in ("brouillon", "irrecevable") and pieces_manquantes:
        texte += " · manque : " + ", ".join(p.replace("_", " ") for p in pieces_manquantes)
    if not texte:
        return {"texte": "Rien à faire", "niveau": "fait", "source": "etape"}
    niveau = "attente" if statut in ETAPES_ATTENTE else ("crit" if statut == "irrecevable" else ("warn" if statut == "pret_validation" else "info"))
    return {"texte": texte, "niveau": niveau, "source": "etape"}


def dimension(d: dict) -> str:
    """Grandeur affichee dans les listes : MW, kVA ou Nm3/h selon la filiere."""
    f = filiere_valide(d.get("filiere"))
    if f in ("rte_ee", "rte_ptf"):
        v = d.get("puissance_mw")
        return f"{_fmt(v)} MW" if v else ""
    if f == "natran":
        v = d.get("debit_nm3h")
        return f"{_fmt(v)} Nm³/h" if v else ""
    if f == "enedis":
        v = d.get("puissance_kva")
        if v:
            return f"{_fmt(v)} kVA"
        return "chantier" if d.get("type_enedis") == "chantier" else ""
    v = d.get("debit_nm3h")
    return f"{_fmt(v)} Nm³/h" if v else ""


def _fmt(v) -> str:
    n = _nombre(v)
    return f"{n:,.0f}".replace(",", " ")
