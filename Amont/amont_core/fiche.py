"""Fiche identite d'un site : champs, champs requis par filiere, passage fiche vers demande.

Un site d'Amont est un projet (meme code). La fiche rassemble tout ce qu'il faut savoir du
site pour deposer les demandes de raccordement, une valeur par champ, avec sa provenance
(manuel, extraction d'un fichier source, valeur par defaut de la societe) et son etat
(a verifier ou valide). Module sans dependance, comme regles.py.
"""

from __future__ import annotations

from . import regles

# (cle, libelle, groupe, type, aide pour l'extraction)
CHAMPS_FICHE: list[tuple[str, str, str, str, str]] = [
    ("nom_installation", "Nom de l'installation", "Site", "text", "nom d'usage du site ou du projet datacenter"),
    ("adresse", "Adresse", "Site", "text", "numero et voie, ou lieu-dit, sans code postal ni commune"),
    ("code_postal", "Code postal", "Site", "text", "5 chiffres"),
    ("commune", "Commune du point de raccordement", "Site", "text", "commune ou se trouve le point de raccordement"),
    ("communes_secondaires", "Autres communes du site", "Site", "text", "si le site est a cheval sur plusieurs communes"),
    ("code_insee", "Code INSEE", "Site", "text", "code officiel geographique de la commune, 5 caracteres"),
    ("departement", "Département", "Site", "text", "numero du departement"),
    ("region", "Région", "Site", "text", ""),
    ("lat", "Latitude", "Site", "number", "WGS84 en degres decimaux"),
    ("lon", "Longitude", "Site", "number", "WGS84 en degres decimaux"),
    ("surface_ha", "Surface du terrain, ha", "Foncier et urbanisme", "number", "surface totale de l'emprise en hectares"),
    ("parcelles", "Parcelles cadastrales", "Foncier et urbanisme", "text", "liste section + numero, ex. AH 367, AH 368 ; site sur plusieurs communes : « Sochaux : AH 367 ; Exincourt : AD 45 »"),
    ("proprietaire", "Propriétaire foncier", "Foncier et urbanisme", "text", "proprietaire actuel du terrain"),
    ("maitrise_fonciere", "Maîtrise foncière", "Foncier et urbanisme", "text", "propriete, promesse de vente, option, bail..."),
    ("zonage_plu", "Zonage PLU", "Foncier et urbanisme", "text", "zone du PLU, ex. UYb"),
    ("zac_nom", "ZAC", "Foncier et urbanisme", "text", "nom de la zone d'amenagement concerte si le site en fait partie, sinon vide"),
    ("zac_lot", "N° de lot de la ZAC", "Foncier et urbanisme", "text", "numero de lot dans la ZAC si connu"),
    ("permis_numero", "N° permis de construire", "Foncier et urbanisme", "text", "ex. PC 025 547 26 X0001"),
    ("permis_date", "Date du permis", "Foncier et urbanisme", "date", ""),
    ("demandeur_societe", "Société demanderesse", "Demandeur", "text", ""),
    ("demandeur_siren", "SIREN", "Demandeur", "text", "9 chiffres"),
    ("demandeur_siret", "SIRET", "Demandeur", "text", "14 chiffres"),
    ("demandeur_tva", "TVA intracommunautaire", "Demandeur", "text", "FR + 11 caracteres"),
    ("demandeur_forme_juridique", "Forme juridique", "Demandeur", "text", "SAS, SCI, société civile... de la société qui demande le raccordement (souvent la société de projet)"),
    ("demandeur_rcs", "RCS, lieu d'immatriculation", "Demandeur", "text", "ville du greffe, ex. Paris"),
    ("demandeur_representant", "Représentant légal", "Demandeur", "text", "nom et fonction, ex. David TAIEB, Gérant ; signataire de la D2"),
    ("demandeur_siege_adresse", "Siège social, numéro et rue", "Demandeur", "text", ""),
    ("demandeur_siege_cp_ville", "Siège social, code postal et ville", "Demandeur", "text", "ex. 75008 Paris"),
    ("demandeur_siege_pays", "Siège social, pays", "Demandeur", "text", ""),
    ("demandeur_capital", "Capital social, €", "Demandeur", "number", "capital social de la societe demanderesse en euros (Kbis)"),
    ("adresse_facturation", "Adresse de facturation", "Demandeur", "text", ""),
    ("interlocuteur_nom", "Interlocuteur, nom", "Demandeur", "text", ""),
    ("interlocuteur_prenom", "Interlocuteur, prénom", "Demandeur", "text", ""),
    ("interlocuteur_civilite", "Interlocuteur, civilité", "Demandeur", "text", "Monsieur ou Madame"),
    ("interlocuteur_fonction", "Interlocuteur, fonction", "Demandeur", "text", "lettres, espaces, tirets uniquement (contrainte du portail RTE)"),
    ("interlocuteur_tel", "Téléphone", "Demandeur", "text", ""),
    ("interlocuteur_portable", "Téléphone portable", "Demandeur", "text", "exige par le portail Enedis"),
    ("interlocuteur_mail", "Courriel", "Demandeur", "text", ""),
    ("puissance_mw", "Puissance de raccordement, MW", "Électricité", "number", "puissance de soutirage demandee au reseau"),
    ("puissance_secondaire_mw", "Hypothèse secondaire, MW", "Électricité", "number", "deuxieme hypothese de puissance si etudiee"),
    ("date_mise_a_disposition", "Mise à disposition souhaitée", "Électricité", "date", "date de mise en service souhaitee du raccordement"),
    ("alimentations_secours", "Alimentations HTB supplémentaires", "Électricité", "number", "nombre d'alimentations de secours"),
    ("poste_rte", "Poste RTE pressenti", "Électricité", "text", "nom du poste electrique de raccordement pressenti"),
    ("tension_kv", "Tension du poste, kV", "Électricité", "number", ""),
    ("distance_poste_km", "Distance au poste, km", "Électricité", "number", "distance du site au poste pressenti"),
    ("contexte", "Contexte du projet", "Électricité", "textarea", "texte court decrivant le projet, repris dans le commentaire de la D1 (500 caracteres)"),
    ("complements_techniques", "Éléments complémentaires D1", "Électricité", "textarea", "profil de consommation, disponibilite souhaitee et questions a poser a RTE, repris a l'etape 4 de la D1 (1000 caracteres)"),
    ("puissance_securite_mw", "Puissance minimale de mise en sécurité, MW", "Électricité", "number", "facultatif, RTE peut demander des justifications"),
    ("puissance_soutirage_mw", "Puissance de soutirage max, MW", "Électricité", "number", "Psoutirage et Pmax de la D2 si differentes de la puissance de raccordement"),
    ("montee_en_charge", "Montée en charge", "Électricité", "text", "paliers de puissance cumulee par echeance, ex. « fin 2029 : 80 ; fin 2030 : 160 ; fin 2031 : 240 » (MW)"),
    ("production_secours", "Production de secours sur site", "Électricité", "text", "oui ou non : groupes electrogenes de secours"),
    ("secours_groupes", "Groupes de secours, puissances", "Électricité", "text", "nombre, puissance et fonctionnement des groupes, ex. 40 groupes de 3 MW, sans couplage au réseau"),
    ("transfo_tensions", "Transformateurs, tensions", "Électricité", "text", "tensions nominales kV/kV des transformateurs HTB du poste client, ex. 225/33 kV"),
    ("transfo_detail", "Transformateurs, nombre et puissance", "Électricité", "text", "nombre de transformateurs, enroulements et puissance apparente ; vide si non defini"),
    ("point_connexion", "Point de connexion, description", "Électricité", "textarea", "emplacement envisage du point de connexion, repris dans la D2 (section IV)"),
    ("reserve_fonciere_rte", "Foncier proposé à RTE", "Électricité", "text", "reserve fonciere proposee pour le poste RTE, ex. environ 0,5 ha au nord de l'emprise"),
    ("complements_d2", "Éléments complémentaires D2", "Électricité", "textarea", "texte libre ajoute a la section VI de la D2 (disponibilite, contraintes, questions a RTE)"),
    ("puissance_chantier_kva", "Puissance de chantier, kVA", "Chantier", "number", "alimentation provisoire de chantier"),
    ("date_debut_chantier", "Début du chantier", "Chantier", "date", ""),
    ("debit_gaz_nm3h", "Débit de gaz maximal, Nm³/h", "Gaz", "number", ""),
    ("debit_gaz_min_nm3h", "Débit de gaz minimal, Nm³/h", "Gaz", "number", ""),
    ("pression_gaz_bar", "Pression de livraison, bar", "Gaz", "number", "bar relatif"),
    ("usage_gaz", "Usage du gaz", "Gaz", "text", "groupes de secours, cogeneration, chaudiere..."),
    # fiche de renseignements « Grands Projets » de GRDF (premiere etape gaz, y compris au-dela des limites de GRDF)
    ("demandeur_naf", "Code NAF", "Demandeur", "text", "code NAF de la societe demanderesse, ex. 6820B"),
    ("site_contact_nom", "Interlocuteur site ou chantier, nom", "Demandeur", "text", "prenom et nom"),
    ("site_contact_fonction", "Interlocuteur site ou chantier, fonction", "Demandeur", "text", ""),
    ("site_contact_tel", "Interlocuteur site ou chantier, téléphone", "Demandeur", "text", ""),
    ("site_contact_portable", "Interlocuteur site ou chantier, portable", "Demandeur", "text", ""),
    ("site_contact_mail", "Interlocuteur site ou chantier, courriel", "Demandeur", "text", ""),
    ("gaz_batiment", "Gaz, dénomination du bâtiment", "Gaz", "text", "ex. OM01 - centrale de secours"),
    ("gaz_presentation", "Gaz, présentation du projet", "Gaz", "textarea", "texte de la rubrique « Présentation projet » de la fiche GRDF : projet, usage du gaz, hypothèses (PCI, PCS, rendement), montée en puissance, foncier ; sans préjuger de la solution de raccordement"),
    ("gaz_date_mise_en_service", "Gaz, mise en service souhaitée", "Gaz", "date", "date de mise en service souhaitee du raccordement gaz"),
    ("gaz_date_poste", "Gaz, mise en place du poste souhaitée", "Gaz", "date", "date souhaitee de mise en place du poste gaz"),
    ("gaz_puissance_installee_kw", "Gaz, puissance totale installée, kW PCS", "Gaz", "number", "puissance gaz totale installee, en kW PCS"),
    ("gaz_puissance_min_mw", "Gaz, puissance appelée minimum, MWPCS", "Gaz", "number", ""),
    ("gaz_puissance_max_mw", "Gaz, puissance appelée maximum, MWPCS", "Gaz", "number", "si absente, calculee depuis le debit maximal et le PCS"),
    ("gaz_conso_annuelle_mwh", "Gaz, consommation annuelle, MWhPCS/an", "Gaz", "number", "consommation previsionnelle annuelle du premier palier"),
    ("gaz_conso_jour_mwh", "Gaz, consommation journalière max, MWhPCS/jour", "Gaz", "number", ""),
    ("gaz_pression_demandee", "Gaz, pression d'alimentation", "Gaz", "text", "300 mbar, fil du gaz, ou autre pression avec son unite, ex. 4 à 6 bar rel."),
    ("gaz_double_ligne", "Gaz, poste double ligne", "Gaz", "text", "oui ou non"),
    ("gaz_redondance", "Gaz, redondance (second poste gaz)", "Gaz", "text", "oui ou non"),
    ("gaz_augmentation", "Gaz, augmentation de puissance prévue", "Gaz", "text", "oui ou non : extension ou ajout d'equipement ulterieur"),
    ("gaz_augmentation_kw", "Gaz, puissance à terme, kW PCS", "Gaz", "number", "puissance gaz visee apres augmentation, en kW PCS"),
    ("gaz_augmentation_date", "Gaz, date de l'augmentation", "Gaz", "text", "echeance ou plage, ex. 2030 à 2032"),
    ("gaz_augmentation_usage", "Gaz, usage de l'augmentation", "Gaz", "text", ""),
    ("gaz_poste_domaine", "Gaz, poste posé en domaine", "Gaz", "text", "prive ou public"),
    ("gaz_tranchees", "Gaz, tranchées ouvertes par", "Gaz", "text", "client ou GRDF"),
    ("gaz_tranchees_ml", "Gaz, longueur de tranchée", "Gaz", "text", "metres lineaires, ou « À définir »"),
    ("gaz_profil_10_ans", "Gaz, consommation années 1 à 10", "Gaz", "text", "MWh/an puis MWh/jour max, une paire par annee, ex. « 25800/12400 ; 51600/24800 ; 77400/37100 »"),
    ("gaz_solutions", "Gaz, solutions techniques", "Gaz", "text", "chaudiere a condensation, cogeneration, PAC gaz, PAC electrique, trigeneration, biomasse, solaire thermique, solaire photovoltaique, ou autre (ex. moteurs a gaz 20 MW)"),
]

CLES = [c[0] for c in CHAMPS_FICHE]
TYPES = {c[0]: c[3] for c in CHAMPS_FICHE}
LIBELLES = {c[0]: c[1] for c in CHAMPS_FICHE}
GROUPES = list(dict.fromkeys(c[2] for c in CHAMPS_FICHE))

_INTERLOCUTEUR = ["interlocuteur_nom", "interlocuteur_prenom", "interlocuteur_fonction", "interlocuteur_tel", "interlocuteur_mail"]

# Ce que chaque formulaire ou fiche d'operateur demande (releves du 04/09, 05/10, 10/09 et conventions NaTran 2025).
REQUIS_PAR_FILIERE: dict[str, list[str]] = {
    "rte_ee": ["nom_installation", "commune", "code_insee", "lat", "lon", "puissance_mw", "date_mise_a_disposition",
               "parcelles", "demandeur_siren", *_INTERLOCUTEUR, "contexte"],
    "rte_ptf": ["nom_installation", "adresse", "code_postal", "commune", "lat", "lon", "puissance_mw", "date_mise_a_disposition",
                "alimentations_secours", "production_secours", "demandeur_societe", "demandeur_forme_juridique", "demandeur_siren",
                "demandeur_rcs", "demandeur_representant", "demandeur_siege_adresse", "demandeur_siege_cp_ville", "demandeur_tva",
                "adresse_facturation", "interlocuteur_nom", "interlocuteur_tel", "interlocuteur_mail"],
    # parcours HTA « Un site industriel en HTA », releve le 28/10/2026 (le parcours chantier reste a relever)
    "enedis": ["adresse", "code_postal", "commune", "parcelles", "puissance_mw", "date_mise_a_disposition", "production_secours",
               "demandeur_societe", "demandeur_siret", "demandeur_siren", "demandeur_forme_juridique", "demandeur_rcs",
               "demandeur_capital", "demandeur_representant", "demandeur_siege_adresse", "demandeur_siege_cp_ville",
               "interlocuteur_civilite", *_INTERLOCUTEUR],
    "grdf": ["nom_installation", "adresse", "code_postal", "commune", "demandeur_societe", "demandeur_siret",
             "demandeur_representant", "demandeur_siege_adresse", "demandeur_siege_cp_ville", "interlocuteur_nom",
             "interlocuteur_mail", "gaz_date_mise_en_service", "debit_gaz_nm3h", "usage_gaz", "gaz_conso_annuelle_mwh",
             "gaz_pression_demandee", "gaz_presentation"],
    "natran": ["adresse", "commune", "lat", "lon", "parcelles", "proprietaire", "zonage_plu", "demandeur_societe",
               "interlocuteur_nom", "interlocuteur_mail", "debit_gaz_nm3h", "debit_gaz_min_nm3h", "pression_gaz_bar",
               "usage_gaz", "date_mise_a_disposition"],
}

CANAUX: dict[str, dict] = {
    "rte_ee": {"canal": "Portail Services RTE, formulaire dématérialisé (compte)", "url": "https://www.services-rte.com/fr/realiser-une-demande-detude-exploratoire.html", "robot": True},
    "rte_ptf": {"canal": "Fiche D2 PDF par courriel avec preuve de virement", "url": "mailto:rte-fcent-raccordement-conso-dist@rte-france.com", "robot": False},
    "enedis": {"canal": "Portail Raccordement Entreprise Enedis, procédure en ligne (robot Enedis)", "url": "https://www.raccordement-entreprise-enedis.fr/", "robot": True},
    "grdf": {"canal": "Fiche de renseignements Grands Projets (PDF) par courriel, toujours en premier ; NaTran suit par redirection de GRDF", "url": "mailto:jean-baptiste.jedrusko@grdf.fr", "robot": False},
    "natran": {"canal": "Demande à l'interlocuteur commercial NaTran, puis convention d'études", "url": "https://www.natrangroupe.com/", "robot": False},
}

# Champ de demande <- champ de fiche, copie a la creation et expose dans le payload.
VERS_DEMANDE: dict[str, dict[str, str]] = {
    "_commun": {"site": "nom_installation", "commune": "commune", "departement": "departement"},
    "rte_ee": {"puissance_mw": "puissance_mw", "hypothese_secondaire_mw": "puissance_secondaire_mw", "d_km": "distance_poste_km"},
    "rte_ptf": {"puissance_mw": "puissance_mw", "d_km": "distance_poste_km", "gps_lat": "lat", "gps_lon": "lon",
                "alimentations_supplementaires": "alimentations_secours"},
    "enedis": {},  # Pracc HTA : puissance de la fiche (MW x 1000) ; puissance_kva de la demande la remplace si saisie
    "grdf": {"debit_nm3h": "debit_gaz_nm3h", "usage_gaz": "usage_gaz"},
    "natran": {"debit_nm3h": "debit_gaz_nm3h", "debit_min_nm3h": "debit_gaz_min_nm3h", "pression_bar": "pression_gaz_bar",
               "usage_gaz": "usage_gaz"},
}

# Valeurs reprises sur chaque nouvelle fiche, modifiables dans amont_config.json ("demandeur").
DEMANDEUR_DEFAUT = {
    "demandeur_societe": "CASTIGNAC",
    "demandeur_siren": "880034798",
    "interlocuteur_nom": "RINAUDO",
    "interlocuteur_prenom": "Alexis",
    "interlocuteur_fonction": "Data Automation and Systems Analyst",
    "interlocuteur_tel": "0184258000",
    "interlocuteur_mail": "arinaudo@castignac.com",
}


def demandeur_defaut() -> dict:
    d = dict(DEMANDEUR_DEFAUT)
    d.update({k: v for k, v in (regles.CONFIG.get("demandeur") or {}).items() if k in CLES})
    return d


def normaliser(cle: str, valeur):
    """Valeur stockee (texte) a partir d'une saisie ou d'une extraction. None si vide."""
    if valeur is None:
        return None
    if isinstance(valeur, bool):
        valeur = "oui" if valeur else "non"
    v = str(valeur).strip()
    if v == "":
        return None
    t = TYPES.get(cle, "text")
    if t == "number":
        v = v.replace(" ", "").replace(" ", "").replace(",", ".").lstrip("~")
        try:
            n = float(v)
        except ValueError:
            return None
        return str(int(n)) if n.is_integer() and cle not in ("lat", "lon") else str(n)
    if t == "date":
        import re
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
        if m:
            v = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        return v[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", v) else None
    if cle in ("demandeur_siren", "demandeur_siret", "code_postal"):
        return v.replace(" ", "")
    return v


def valeur_typee(cle: str, v):
    if v is None:
        return None
    if TYPES.get(cle) == "number":
        try:
            n = float(v)
            return int(n) if n.is_integer() and cle not in ("lat", "lon") else n
        except ValueError:
            return None
    return v


def completude(valeurs: dict, filieres: list[str]) -> dict:
    """Pour chaque filiere : champs requis manquants et a verifier. valeurs = {cle: {"valeur", "valide"}}."""
    out = {}
    for f in filieres:
        requis = REQUIS_PAR_FILIERE.get(f, [])
        manquants = [k for k in requis if not (valeurs.get(k) or {}).get("valeur")]
        a_verifier = [k for k in requis if (valeurs.get(k) or {}).get("valeur") and not (valeurs.get(k) or {}).get("valide")]
        out[f] = {
            "requis": len(requis),
            "manquants": manquants,
            "a_verifier": a_verifier,
            "pret": not manquants and not a_verifier,
            "taux": round(100 * (len(requis) - len(manquants)) / len(requis)) if requis else 100,
            **CANAUX.get(f, {}),
        }
    return out


def vers_demande(filiere: str, valeurs: dict) -> dict:
    """Champs de demande pre-remplis depuis la fiche (valeurs = {cle: valeur typee})."""
    out = {}
    for groupe in ("_commun", filiere):
        for cle_demande, cle_fiche in VERS_DEMANDE.get(groupe, {}).items():
            v = valeurs.get(cle_fiche)
            if v not in (None, ""):
                out[cle_demande] = v
    if filiere == "enedis":
        out.setdefault("type_enedis", "hta")  # site < 40 MW raccorde en HTA ; le chantier se choisit a la main
    return out
