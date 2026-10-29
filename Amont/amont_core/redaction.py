"""Redaction des textes des demandes a partir de la fiche du site, par l'IA locale.

Deux textes de la D1 RTE (etude exploratoire), repris tels quels par le robot :
  contexte                 « Commentaires relatifs a votre demande », 500 caracteres au plus
  complements_techniques   « Elements complementaires... », 1000 caracteres au plus

Le texte produit entre dans la fiche « a verifier » (ou en valeur divergente si le champ est deja
rempli) : rien n'est envoye sans relecture. Le style suit les textes ecrits a la main pour Sochaux
le 08/10/2026, donnes au modele comme exemples.
"""

from __future__ import annotations

import re

from . import fiche, ia

TEXTES = {
    "contexte": {
        "limite": 500,
        "role": "le commentaire de la demande d'etude exploratoire RTE (formulaire D1, champ « Commentaires relatifs a votre demande »)",
        "contenu": "le projet (datacenter, surface, communes, porteur), la puissance de raccordement visee en soutirage, "
                   "et ce que l'on attend de l'etude : solutions de raccordement envisageables, poste de rattachement, "
                   "delais et ordre de grandeur des couts, avec l'objectif d'un raccordement rapide",
        "exemple": "Projet de datacenter d'environ 30 ha, sur les communes de Sochaux et Exincourt (le poste sera sur la commune "
                   "de Sochaux), porté par Castignac. Puissance de raccordement visée 300 MW en soutirage. Nous souhaitons "
                   "connaître les solutions de raccordement envisageables (poste de rattachement, délais et ordre de grandeur "
                   "des coûts) afin d'avoir un raccordement le plus rapide possible.",
    },
    "complements_techniques": {
        "limite": 1000,
        "role": "les « Elements complementaires relatifs a l'installation et au niveau de disponibilite souhaite » de la D1 RTE",
        "contenu": "le profil de consommation d'un datacenter (quasi constant, facteur de charge eleve), la montee en puissance "
                   "par phases, le niveau de disponibilite recherche, puis 3 ou 4 questions numerotees pour l'etude : "
                   "contraintes de transit sur le reseau amont autour du poste pressenti, renforcements et delais, "
                   "compensation de puissance reactive, raccordement avec limitations temporaires et puissance disponible a court terme",
        "exemple": "Installation de type datacenter, consommation quasi constante (facteur de charge élevé), montée en puissance "
                   "envisagée par phases jusqu'à 300 MW. Niveau de disponibilité recherché élevé, compatible avec un usage "
                   "datacenter. Questions complémentaires pour l'étude : 1) contraintes de transit éventuelles sur le réseau amont, "
                   "notamment autour du poste 225 kV d'Étupes ; 2) renforcements amont nécessaires et délais associés ; "
                   "3) besoins de compensation de puissance réactive à prévoir côté client ; 4) possibilité d'un raccordement "
                   "avec limitations temporaires de puissance dans l'attente des renforcements, et puissance disponible à court terme.",
    },
}

FAITS = ["nom_installation", "commune", "communes_secondaires", "departement", "surface_ha", "parcelles", "zonage_plu",
         "demandeur_societe", "puissance_mw", "puissance_secondaire_mw", "date_mise_a_disposition", "alimentations_secours",
         "poste_rte", "tension_kv", "distance_poste_km"]


def couper(texte: str, limite: int) -> str:
    """Au plus `limite` caracteres, coupe a la derniere fin de phrase ou de proposition."""
    t = re.sub(r"\s+", " ", texte).strip().strip('"').strip()
    if len(t) <= limite:
        return t
    t = t[:limite]
    for sep in (". ", " ; ", "; "):
        i = t.rfind(sep)
        if i > limite * 0.6:
            return t[:i + 1].rstrip(" ;") + ("" if t[i] == "." else ".")
    return t[:t.rfind(" ")].rstrip(",;") + "."


def rediger(champ: str, valeurs: dict) -> dict:
    if champ not in TEXTES:
        raise ValueError(f"pas de rédaction automatique pour le champ {champ}")
    if not ia.disponible():
        raise ValueError("IA non configurée : voir AMONT_IA_URL et AMONT_IA_MODELE")
    t = TEXTES[champ]
    faits = "\n".join(f"- {fiche.LIBELLES.get(k, k)} : {valeurs[k]}" for k in FAITS if valeurs.get(k) not in (None, ""))
    if not faits:
        raise ValueError("fiche du site trop vide pour rédiger : renseigner au moins la commune et la puissance")
    consigne = f"""Redige en francais {t['role']}, pour un projet de datacenter porte par la societe Castignac.

Faits connus (n'utilise que ceux-ci, n'invente aucun chiffre ni aucun nom) :
{faits}

Contenu attendu : {t['contenu']}.
Si un fait manque (poste, surface...), n'en parle pas.
Longueur : {t['limite']} caracteres au plus, espaces compris, en un seul paragraphe. Ton sobre et factuel, sans formule de politesse
finale, sans titre, sans guillemets.

Exemple ecrit pour un autre site, a imiter pour le ton et la structure, pas pour les chiffres :
{t['exemple']}

Reponds en JSON : {{"texte": "..."}}"""
    rep, stats = ia.demander_json(consigne, max_jetons=900, temperature=0.3,
                                  schema={"type": "object", "properties": {"texte": {"type": "string"}}, "required": ["texte"]})
    brut = str((rep or {}).get("texte") or "").strip() if isinstance(rep, dict) else ""
    if not brut:
        raise ValueError("le modèle n'a pas rendu de texte")
    texte = couper(brut, t["limite"])
    # garde-fou : chaque nombre du texte doit venir des faits ou de l'exemple de structure (1) 2) 3)...)
    nombres_faits = set(re.findall(r"\d+(?:[.,]\d+)?", faits))
    inventes = [n for n in re.findall(r"\d+(?:[.,]\d+)?", texte)
                if n not in nombres_faits and n.replace(",", ".") not in nombres_faits and not (len(n) == 1 and n in "123456")]
    return {"champ": champ, "texte": texte, "longueur": len(texte), "limite": t["limite"], "coupe": len(brut) > t["limite"],
            "nombres_a_verifier": inventes, "modele": stats.get("modele"), "secondes": stats.get("secondes")}
