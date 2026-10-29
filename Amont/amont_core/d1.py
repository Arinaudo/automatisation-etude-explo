"""Plan de remplissage du formulaire D1 du Portail Services RTE (etude exploratoire).

Source unique du mapping fiche -> formulaire, partagee par le site (apercu « pret pour le robot »)
et par le robot du poste (2026_10_26_amont_robot_d1.py), qui lit ce plan par l'API au lieu de
porter son propre mapping. Structure relevee en direct les 04/09 et 05/10/2026 (5 etapes,
Angular Material, ciblage par libelle de question).

Types d'action :
  radio     clic sur l'option d'un groupe de boutons radio, repere par sa question
  texte     affectation de la valeur + evenements input et blur (champs simples)
  frappe    vraies frappes clavier puis Tab (SIREN : declenche la recherche de la societe)
  case      case a cocher reperee par son libelle (Consommation...)
  liste     liste deroulante mat-select, option par texte
  commune   frappes + choix dans l'autocompletion, a faire AVANT le GPS (il l'efface)
  date      calendrier seulement (champ en lecture seule) : annee, mois, jour par aria-label
  fichier   piece jointe PDF, 2 Mo maximum, telechargee depuis Amont par le robot
L'etape 5 n'a aucune action : le robot s'arrete avant l'interrupteur de certification.
"""

from __future__ import annotations

import re
from datetime import date

URL_D1 = "https://www.services-rte.com/fr/realiser-une-demande-detude-exploratoire.html"
TAILLE_MAX_PIECE = 2 * 1024 * 1024
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
TITRES = {1: "Société", 2: "Demande", 3: "Installation", 4: "Données techniques", 5: "Validation"}


def nettoyer_fonction(f: str) -> str:
    """Le champ Fonction du portail refuse virgules, &, /, chiffres (regex cachee, releve du 05/10)."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-zÀ-ÿ' -]", " ", f or "")).strip()


def _gps(v) -> str | None:
    """maxlength=8 sur les champs GPS : 5 decimales au plus, puis coupe a 8 caracteres."""
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    t = f"{x:.5f}".rstrip("0").rstrip(".")
    return t[:8]


def _date_cal(v) -> dict | None:
    try:
        d = date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None
    return {"iso": d.isoformat(), "annee": str(d.year), "mois": f"{MOIS[d.month - 1]} {d.year}",
            "jour": f"{d.day} {MOIS[d.month - 1]} {d.year}"}


def _nombre_txt(v) -> str | None:
    if v in (None, ""):
        return None
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        return None
    return str(int(x)) if x == int(x) else str(x)


def plan(payload: dict, aujourdhui: date | None = None) -> dict:
    """payload : sortie de Registre.payload() (demande aplatie, fiche, pieces)."""
    auj = aujourdhui or date.today()
    fi = payload.get("fiche") or {}
    g = lambda k, *alt: next((v for v in [payload.get(k), *[payload.get(a) for a in alt], fi.get(k), *[fi.get(a) for a in alt]]  # noqa: E731
                              if v not in (None, "")), None)
    pieces = {}
    # la piece la plus recente de chaque type : un extrait recupere a nouveau remplace le precedent
    for p in sorted(payload.get("pieces") or [], key=lambda x: (x.get("ajoute_le") or "", x.get("id") or 0), reverse=True):
        if p["type"] in ("extrait_cadastral", "plan_installation") and p["type"] not in pieces:
            pieces[p["type"]] = {"id": p["id"], "nom": p["nom_fichier"], "taille": p.get("taille_octets")}

    etapes: dict[int, list] = {i: [] for i in range(1, 6)}

    def act(n, question, type_, valeur, requis=True, source="", note="", **extra):
        manque = requis and valeur in (None, "")
        etapes[n].append({"question": question, "type": type_, "valeur": valeur, "requis": requis,
                          "source": source, "note": note, "manque": manque, **extra})

    # 1 SOCIETE
    act(1, "Êtes-vous une société française", "radio", "Oui", source="fixe")
    act(1, "Numéro de SIREN", "frappe", fi.get("demandeur_siren"), source="fiche : SIREN",
        note="le nom de la société doit s'afficher après la frappe")
    act(1, "Vous disposez d'une boîte aux lettres", "radio", "Nominative", source="fixe", par_valeur=True)
    act(1, "Nom de l'interlocuteur", "texte", fi.get("interlocuteur_nom"), source="fiche")
    act(1, "Prénom de l'interlocuteur", "texte", fi.get("interlocuteur_prenom"), source="fiche")
    act(1, "Fonction de l'interlocuteur", "texte", nettoyer_fonction(fi.get("interlocuteur_fonction") or "") or None,
        requis=False, source="fiche", note="nettoyée : lettres, espaces, tirets, apostrophes")
    act(1, "Téléphone de contact", "texte", re.sub(r"[^0-9+]", "", str(fi.get("interlocuteur_tel") or "")) or None, source="fiche")
    act(1, "Adresse mail de contact", "texte", fi.get("interlocuteur_mail"), source="fiche")
    act(1, "Êtes-vous mandataire", "radio", "Non", source="fixe")

    # 2 DEMANDE
    act(2, "Type de demande", "radio", "Nouveau raccordement HTB", source="fixe", par_valeur=True)
    act(2, "Consommation", "case", "Consommation", source="fixe", note="seule nature cochée")
    act(2, "Quel est le secteur d'activité", "liste", "Datacenter", source="fixe")
    ctx = fi.get("contexte") or ""
    act(2, "Commentaires relatifs à votre demande", "texte", ctx[:500] or None, requis=False, source="fiche : contexte",
        note=(f"coupé à 500 caractères (texte de {len(ctx)})" if len(ctx) > 500 else f"{len(ctx)} / 500 caractères"))

    # 3 INSTALLATION
    act(3, "Nom de l'installation", "texte", fi.get("nom_installation") or payload.get("site"), source="fiche")
    act(3, "Nom de la commune", "commune", fi.get("commune") or payload.get("commune"), source="fiche",
        note="avant le GPS, qui est effacé au choix de la commune ; code INSEE rempli par le portail"
             + (f" (attendu {fi['code_insee']})" if fi.get("code_insee") else ""))
    act(3, "Latitude", "texte", _gps(fi.get("lat")), source="fiche", note="5 décimales au plus")
    act(3, "Longitude", "texte", _gps(fi.get("lon")), source="fiche")
    cal = _date_cal(fi.get("date_mise_a_disposition"))
    note_date = ""
    if cal and cal["iso"] <= auj.isoformat():
        note_date = "date passée : le portail n'accepte qu'une date à partir de demain"
        cal = None
    act(3, "Date souhaitée de mise à disposition", "date", cal["iso"] if cal else None, source="fiche",
        note=note_date or "par le calendrier", calendrier=cal)
    ec = pieces.get("extrait_cadastral")
    act(3, "Extrait cadastral", "fichier", ec["nom"] if ec else None, requis=False, source="pièce de la demande",
        note=("absent : la recevabilité tombe sous 8 jours ouvrés" if not ec else
              ("au-delà de 2 Mo, refusé par le portail" if (ec.get("taille") or 0) > TAILLE_MAX_PIECE else "PDF ≤ 2 Mo")),
        piece=ec, index_fichier=0, bloquant=not ec)

    # 4 DONNEES TECHNIQUES
    act(4, "Avez-vous un raccordement existant en HTA", "radio", "Non", source="fixe")
    act(4, "Avez-vous formulé une demande de raccordement en HTA", "radio", "Non", source="fixe")
    act(4, "Puissance de raccordement souhaitée", "texte", _nombre_txt(g("puissance_mw")), source="demande ou fiche")
    alim = _nombre_txt(fi.get("alimentations_secours"))
    if alim not in (None, "0", "1", "2"):
        alim = None
    act(4, "Combien d'alimentations HTB supplémentaires", "radio", alim or "0", source="fiche" if alim else "défaut",
        note="1 ou 2 : contribution de 70 à 85 %" if alim and alim != "0" else "")
    act(4, "Avez-vous besoin d'un niveau minimal de puissance de court-circuit", "radio", "Non", source="fixe")
    act(4, "Puissance minimale de mise en sécurité", "texte", _nombre_txt(fi.get("puissance_securite_mw")), requis=False, source="fiche")
    comp = fi.get("complements_techniques") or ""
    act(4, "Éléments complémentaires relatifs à l'installation", "texte", comp[:1000] or None, requis=False,
        source="fiche : éléments complémentaires",
        note=(f"coupé à 1000 caractères (texte de {len(comp)})" if len(comp) > 1000 else f"{len(comp)} / 1000 caractères"))
    pl = pieces.get("plan_installation")
    act(4, "Plan de l'installation", "fichier", pl["nom"] if pl else None, requis=False, source="pièce de la demande",
        note="facultatif : plan de situation + implantation + unifilaire fusionnés, PDF ≤ 2 Mo", piece=pl, index_fichier=1)

    sortie = []
    for n in range(1, 6):
        sortie.append({"numero": n, "titre": TITRES[n], "actions": etapes[n]})
    sortie[-1]["arret"] = ("Le robot s'arrête ici. À vous : relire les 4 étapes, activer l'interrupteur de certification, "
                           "cliquer sur Envoyer, puis passer la demande à « Déposé » dans Amont.")
    manquants = [f"étape {e['numero']} : {a['question']}" for e in sortie for a in e["actions"] if a["manque"]]
    alertes = [f"étape {e['numero']} : {a['question']} : {a['note']}" for e in sortie for a in e["actions"]
               if a.get("bloquant") or "refusé" in (a.get("note") or "") or "passée" in (a.get("note") or "") or "coupé" in (a.get("note") or "")]
    return {"demande": payload.get("id"), "projet": payload.get("projet_code"), "url": URL_D1, "etapes": sortie,
            "manquants": manquants, "alertes": alertes, "pret": not manquants}
