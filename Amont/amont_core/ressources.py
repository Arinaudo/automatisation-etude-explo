"""Documents et liens d'origine pour remplir chaque demande, par filiere et par etape.

Amorces au premier demarrage (table ressources vide), puis modifiables depuis la page
Documents du site : les portails changent d'adresse, les fiches de collecte de version.
etape vide : la ressource vaut pour toutes les etapes de la filiere. filiere « commun » : pour toutes.
verifie_le : date a laquelle le lien a ete constate valide (releve, recherche ou saisie).
"""

from __future__ import annotations

TYPES_RESSOURCE = {
    "formulaire": "Formulaire à remplir",
    "document": "Document modèle",
    "envoi": "Adresse d'envoi",
    "reglementation": "Texte de référence",
    "outil": "Outil pour une pièce",
}

# (filiere, etape, type, libelle, url, notes, verifie_le)
DEFAUT: list[tuple[str, str, str, str, str, str, str]] = [
    # --- communs : pieces que toutes les demandes reclament
    ("commun", "brouillon", "outil", "Cadastre : extrait de plan cadastral", "https://www.cadastre.gouv.fr/",
     "Extrait du plan au point de raccordement, PDF de 2 Mo au plus pour le portail RTE.", ""),
    ("commun", "brouillon", "outil", "Géoportail de l'urbanisme : PLU et zonage", "https://www.geoportail-urbanisme.gouv.fr/",
     "Règlement de zone et servitudes.", ""),
    ("commun", "brouillon", "outil", "Annuaire des entreprises : SIREN, SIRET, TVA", "https://annuaire-entreprises.data.gouv.fr/",
     "Identifiants du demandeur.", ""),
    # --- RTE etude exploratoire
    ("rte_ee", "brouillon", "formulaire", "Portail Services RTE : demande d'étude exploratoire (D1)",
     "https://www.services-rte.com/fr/realiser-une-demande-detude-exploratoire.html",
     "Formulaire dématérialisé, compte Castignac. Rempli par le robot D1, envoi à la main.", "2026-10-05"),
    ("rte_ee", "pret_validation", "formulaire", "Portail Services RTE : demande d'étude exploratoire (D1)",
     "https://www.services-rte.com/fr/realiser-une-demande-detude-exploratoire.html",
     "Relire les 4 étapes, activer la certification, envoyer. Puis passer la demande à « Déposé ».", "2026-10-05"),
    ("rte_ee", "", "formulaire", "Portail Services RTE : accueil et suivi des demandes", "https://www.services-rte.com/fr/home.html",
     "Accès aux demandes déposées.", "2026-10-26"),
    ("rte_ee", "", "reglementation", "Procédure de raccordement RTE, délibération CRE 2026-32 (annexe)",
     "https://www.cre.fr/fileadmin/Documents/Deliberations/2026/260204_2026-32_Procedure_raccordement_RTE_annexe.pdf",
     "Étude exploratoire : recevabilité, délai de 6 semaines, confirmation de solution.", "2026-10-26"),
    # --- RTE PTF
    ("rte_ptf", "brouillon", "document", "Médiathèque client RTE : fiches de collecte, dont la D2",
     "http://clients.rte-france.com/lang/fr/clients_distributeurs/mediatheque_client/offre.jsp",
     "Adresse citée par la CRE (délibération de juillet 2026) pour la fiche D2, non testée. Déposer ici la fiche D2 vierge une fois récupérée.", ""),
    ("rte_ptf", "pret_validation", "envoi", "Envoi de la D2 : service raccordement consommateurs RTE",
     "mailto:rte-fcent-raccordement-conso-dist@rte-france.com",
     "D2 complète, GPS du point de connexion, unifilaire, preuve de virement de la somme forfaitaire.", "2026-09-10"),
    ("rte_ptf", "", "reglementation", "Procédure de raccordement RTE, délibération CRE 2026-32 (annexe)",
     "https://www.cre.fr/fileadmin/Documents/Deliberations/2026/260204_2026-32_Procedure_raccordement_RTE_annexe.pdf",
     "Demande de PTF, file d'attente, maintien annuel.", "2026-10-26"),
    ("rte_ptf", "", "reglementation", "Procédure de raccordement fast-track, délibération CRE 2025-120 (annexe)",
     "https://www.cre.fr/fileadmin/Documents/Deliberations/2025/250507_2025-120_Procedure_raccordement_Fast_track_annexe.pdf",
     "Dispositif accéléré pour les grands consommateurs.", "2026-10-26"),
    # --- Enedis
    ("enedis", "brouillon", "formulaire", "Enedis : Portail Raccordement Entreprise", "https://www.raccordement-entreprise-enedis.fr/",
     "Procédure en ligne, alimentation de chantier et raccordements entreprise.", "2026-10-07"),
    ("enedis", "", "formulaire", "Enedis : Connect Racco, raccordement HTA définitif", "https://connect-racco.enedis.fr/",
     "Compte requis. Pour un site de moins de 40 MW raccordé en HTA.", "2026-09-10"),
    # --- GRDF
    ("grdf", "brouillon", "formulaire", "GRDF : fiche de renseignements Grands Projets (modèle)",
     "", "PDF à champs, générée par Amont, à envoyer par courriel à l'interlocuteur Grands Projets de GRDF. Toujours la première démarche gaz, même sans réseau à proximité ou au-delà des limites de GRDF ; GRDF redirige ensuite vers NaTran.", "2026-10-29"),
    ("grdf", "brouillon", "formulaire", "GRDF : demande de raccordement entreprise (formulaire public)",
     "https://monespace.grdf.fr/demande-raccordement-reseau-gaz/entreprise",
     "Formulaire public sans compte, pour les petits raccordements : non utilisé pour les datacenters.", "2026-09-10"),
    # --- NaTran
    ("natran", "", "envoi", "NaTran (ex-GRTgaz) : site et contacts commerciaux", "https://www.natrangroupe.com/",
     "Pas de portail : demande à l'interlocuteur commercial.", ""),
]
