# -*- coding: utf-8 -*-
"""
DCEX-SUIVI : noyau de suivi de la chaine de raccordement RTE.

Couvre toute la chaine, de la demande d'etude exploratoire (fiche D1)
jusqu'au maintien annuel en file d'attente :

    D1 depose -> recevabilite (8 jours ouvres) -> etude exploratoire (6 semaines)
    -> confirmation de validite (15 jours) -> demande de PTF / fiche D2 (3 mois)
    -> PTF recue (validite 3 mois) -> acceptation = entree en file d'attente
    -> maintien annuel (justificatifs d'avancement ou 1 k EUR / MW)

Le registre est un simple fichier JSON, versionnable et lisible a la main.
Aucune dependance externe : bibliotheque standard uniquement.

Usage :
    python 2026_09_03_dcex_racc_suivi.py init
    python 2026_09_03_dcex_racc_suivi.py add --id AIV-600 --projet "AI-Valley" ...
    python 2026_09_03_dcex_racc_suivi.py list
    python 2026_09_03_dcex_racc_suivi.py alertes
    python 2026_09_03_dcex_racc_suivi.py set AIV-600 statut=depose date_depot=2026-09-15
    python 2026_09_03_dcex_racc_suivi.py payload AIV-600        # JSON pour le robot de depot
    python 2026_09_03_dcex_racc_suivi.py export                 # JSON pour le dashboard

Alexis Rinaudo / Castignac - 03/09/2026
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Constantes reglementaires et delais observes
# ---------------------------------------------------------------------------

REGISTRE_DEFAUT = "2026_09_03_dcex_racc_registre.json"

# Article 105 de l'arrete du 9 juin 2020 : Prac < min(seuil absolu, K / d)
# d = distance reseau, en km, jusqu'au point de transformation vers le domaine
# superieur le plus proche.
DOMAINES = [
    # (nom, seuil absolu MW, K, tensions usuelles)
    ("HTA", 40, 100, "20 kV"),
    ("HTB1", 100, 1000, "63 / 90 kV"),
    ("HTB2", 400, 10000, "150 / 225 kV"),
    ("HTB3", None, None, "400 kV"),
]

# Delais opposables a RTE (DTR article 1.2.2)
DELAI_RECEVABILITE_JO = 8          # jours ouvres pour signaler une piece manquante
DELAI_ETUDE_SEMAINES = 6           # delai annonce a compter de la recevabilite
DELAI_CONFIRMATION_JOURS = 15      # confirmation de validite d'une etude rendue
DELAI_PTF_MOIS = 3                 # instruction de la PTF apres fiche D2
VALIDITE_PTF_MOIS = 3              # duree de validite de la PTF remise
FORFAIT_PTF_EUR_HT = 42000
MAINTIEN_FILE_EUR_PAR_MW = 1000

# Delai realiste de remise de l'etude, cale sur le corpus d'etudes RTE en notre
# possession : 60 MW -> 4 semaines, 64 MW -> 7, 600-1000 MW -> 8, 600 MW -> 16.
# Le delai contractuel reste 6 semaines, mais la prevision sert a planifier.
def previsionnel_etude_semaines(puissance_mw: float) -> int:
    if puissance_mw < 100:
        return 7
    if puissance_mw < 400:
        return 10
    return 16


# Etapes de la chaine, dans l'ordre. Cle -> (libelle, jalon suivant attendu)
ETAPES = [
    ("brouillon",         "Dossier en preparation"),
    ("pret_validation",   "Formulaire pre-rempli, en attente de validation humaine"),
    ("depose",            "D1 depose, en attente de recevabilite"),
    ("recevable",         "Recevable, etude en cours"),
    ("irrecevable",       "Irrecevable, piece manquante a fournir"),
    ("etude_recue",       "Etude exploratoire recue"),
    ("validite_confirmee","Validite de l'etude confirmee"),
    ("ptf_demandee",      "Fiche D2 deposee, PTF en instruction"),
    ("ptf_recue",         "PTF recue, en cours d'arbitrage"),
    ("file_attente",      "PTF acceptee, en file d'attente"),
    ("abandonne",         "Abandonne"),
]
LIBELLES = dict(ETAPES)


# ---------------------------------------------------------------------------
# Utilitaires de dates
# ---------------------------------------------------------------------------

def parse_date(valeur: Any) -> date | None:
    if not valeur:
        return None
    if isinstance(valeur, date):
        return valeur
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valeur).strip(), fmt).date()
        except ValueError:
            continue
    return None


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def ajoute_jours_ouvres(depart: date, n: int) -> date:
    """Ajoute n jours ouvres (samedi et dimanche exclus, feries non geres)."""
    courant = depart
    restants = n
    while restants > 0:
        courant += timedelta(days=1)
        if courant.weekday() < 5:
            restants -= 1
    return courant


def ajoute_mois(depart: date, n: int) -> date:
    mois = depart.month - 1 + n
    annee = depart.year + mois // 12
    mois = mois % 12 + 1
    jour = min(depart.day, [31, 29 if annee % 4 == 0 and (annee % 100 != 0 or annee % 400 == 0)
                            else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mois - 1])
    return date(annee, mois, jour)


# ---------------------------------------------------------------------------
# Article 105 : domaine de tension de reference
# ---------------------------------------------------------------------------

def domaine_de_reference(puissance_mw: float, d_km: float | None) -> dict:
    """Renvoie le domaine impose et la puissance plafond du domaine inferieur."""
    retenu = "HTB3"
    detail = []
    for nom, seuil, k, tensions in DOMAINES:
        if seuil is None:
            continue
        limite_distance = (k / d_km) if (d_km and d_km > 0) else float("inf")
        limite = min(seuil, limite_distance)
        detail.append({
            "domaine": nom,
            "tensions": tensions,
            "seuil_absolu_mw": seuil,
            "limite_distance_mw": None if limite_distance == float("inf") else round(limite_distance, 1),
            "limite_effective_mw": round(limite, 1),
            "mordant": "distance" if limite_distance < seuil else "seuil absolu",
        })
        if puissance_mw < limite and retenu == "HTB3":
            retenu = nom
    plafond_inferieur = None
    noms = [x[0] for x in DOMAINES]
    if retenu in noms:
        i = noms.index(retenu)
        if i > 0:
            inf = detail[i - 1]
            plafond_inferieur = {"domaine": inf["domaine"], "puissance_max_mw": inf["limite_effective_mw"]}
    return {"domaine": retenu, "detail": detail, "plafond_domaine_inferieur": plafond_inferieur}


# ---------------------------------------------------------------------------
# Modele de donnees
# ---------------------------------------------------------------------------

@dataclass
class Demande:
    id: str
    projet: str = ""
    site: str = ""
    commune: str = ""
    departement: str = ""
    lat: float | None = None
    lon: float | None = None

    # Demandeur / consommateur (rubriques II et III de la fiche D1)
    demandeur_societe: str = ""
    demandeur_siren: str = ""
    demandeur_contact: str = ""
    demandeur_nom: str = ""
    demandeur_prenom: str = ""
    demandeur_fonction: str = ""
    demandeur_adresse: str = ""
    demandeur_cp: str = ""
    demandeur_ville: str = ""
    demandeur_tel: str = ""
    demandeur_mail: str = ""
    demandeur_mandataire: bool = False
    consommateur_societe: str = ""
    consommateur_siren: str = ""
    site_siret: str = ""

    # Rubriques IV et V
    puissance_mw: float = 0.0
    puissance_soutirage_max_mw: float | None = None
    hypothese_secondaire_mw: float | None = None
    date_mise_a_disposition: str | None = None
    alimentation_secours: bool = False
    besoin_pcc_min: bool = False
    d_km: float | None = None
    raccordement_hta_existant: bool = False
    demande_hta_en_cours: bool = False
    alimentations_supplementaires: int = 0
    puissance_mise_en_securite_mw: float | None = None
    complements_techniques: str = ""
    piece_cadastre: str = ""
    piece_plan: str = ""
    nature: str = "Nouveau raccordement HTB"
    commentaire: str = ""

    # Pieces jointes (chemins relatifs au dossier du projet)
    pieces: list[str] = field(default_factory=list)

    # Suivi
    statut: str = "brouillon"
    date_depot: str | None = None
    date_recevabilite: str | None = None
    date_etude_recue: str | None = None
    num_etude: str | None = None
    date_confirmation_demandee: str | None = None
    date_confirmation_recue: str | None = None
    date_ptf_demandee: str | None = None
    date_ptf_recue: str | None = None
    date_ptf_acceptee: str | None = None
    date_relance: str | None = None

    # Resultats de l'etude
    solution: str = ""
    cout_total_keur: float | None = None
    cout_client_keur: float | None = None
    taux_contribution_pct: float | None = None
    delai_mois: int | None = None
    limitations: str = ""
    interlocuteur_rte: str = ""
    notes: str = ""

    # ------------------------------------------------------------------
    def jalons(self, aujourdhui: date | None = None) -> list[dict]:
        """Echeancier calcule de la demande."""
        today = aujourdhui or date.today()
        out: list[dict] = []

        def ajoute(cle, libelle, echeance, fait, base=None):
            if echeance is None:
                return
            out.append({
                "cle": cle,
                "libelle": libelle,
                "echeance": iso(echeance),
                "fait": bool(fait),
                "jours_restants": (echeance - today).days,
                "base": base,
            })

        depot = parse_date(self.date_depot)
        recev = parse_date(self.date_recevabilite)
        etude = parse_date(self.date_etude_recue)
        conf_dem = parse_date(self.date_confirmation_demandee)
        ptf_dem = parse_date(self.date_ptf_demandee)
        ptf_recue = parse_date(self.date_ptf_recue)
        ptf_acc = parse_date(self.date_ptf_acceptee)

        if depot:
            ajoute("recevabilite",
                   f"Recevabilite RTE ({DELAI_RECEVABILITE_JO} jours ouvres)",
                   ajoute_jours_ouvres(depot, DELAI_RECEVABILITE_JO),
                   recev or etude, "depot")
        base_etude = recev or depot
        if base_etude:
            ajoute("etude_contractuelle",
                   f"Remise de l'etude, delai annonce ({DELAI_ETUDE_SEMAINES} semaines)",
                   base_etude + timedelta(weeks=DELAI_ETUDE_SEMAINES), etude, "recevabilite")
            prev = previsionnel_etude_semaines(self.puissance_mw or 0)
            ajoute("etude_previsionnelle",
                   f"Remise de l'etude, previsionnel calibre ({prev} semaines)",
                   base_etude + timedelta(weeks=prev), etude, "recevabilite")
            if not etude:
                ajoute("relance",
                       "Relance ecrite a viser sur l'article 1.2.2",
                       base_etude + timedelta(weeks=DELAI_ETUDE_SEMAINES),
                       parse_date(self.date_relance), "recevabilite")
        if conf_dem:
            ajoute("confirmation",
                   f"Reponse RTE sur la confirmation de validite ({DELAI_CONFIRMATION_JOURS} jours)",
                   conf_dem + timedelta(days=DELAI_CONFIRMATION_JOURS),
                   parse_date(self.date_confirmation_recue), "confirmation")
        if ptf_dem:
            ajoute("ptf_instruction",
                   f"Remise de la PTF ({DELAI_PTF_MOIS} mois)",
                   ajoute_mois(ptf_dem, DELAI_PTF_MOIS), ptf_recue, "ptf")
        if ptf_recue:
            ajoute("ptf_validite",
                   f"Fin de validite de la PTF ({VALIDITE_PTF_MOIS} mois)",
                   ajoute_mois(ptf_recue, VALIDITE_PTF_MOIS), ptf_acc, "ptf")
        if ptf_acc:
            prochain = ptf_acc
            while prochain <= today:
                prochain = ajoute_mois(prochain, 12)
            ajoute("maintien_file",
                   "Maintien en file d'attente : justificatifs ou "
                   f"{MAINTIEN_FILE_EUR_PAR_MW / 1000:.0f} k EUR/MW",
                   prochain, False, "file_attente")
        return out

    def prochaine_echeance(self, aujourdhui: date | None = None) -> dict | None:
        restants = [j for j in self.jalons(aujourdhui) if not j["fait"]]
        if not restants:
            return None
        return sorted(restants, key=lambda j: j["echeance"])[0]

    def alertes(self, aujourdhui: date | None = None) -> list[dict]:
        out = []
        for j in self.jalons(aujourdhui):
            if j["fait"]:
                continue
            if j["jours_restants"] < 0:
                out.append({**j, "niveau": "critique",
                            "message": f"{j['libelle']} : depasse de {-j['jours_restants']} jours"})
            elif j["jours_restants"] <= 14:
                out.append({**j, "niveau": "attention",
                            "message": f"{j['libelle']} : dans {j['jours_restants']} jours"})
        if self.statut == "brouillon" and not self.pieces:
            out.append({"cle": "pieces", "niveau": "attention", "echeance": None,
                        "jours_restants": None, "fait": False,
                        "message": "Aucune piece jointe : l'extrait cadastral est obligatoire"})
        if self.statut == "pret_validation":
            out.append({"cle": "validation", "niveau": "attention", "echeance": None,
                        "jours_restants": None, "fait": False,
                        "message": "Formulaire pre-rempli sur le portail : votre validation d'envoi est attendue"})
        if self.statut == "irrecevable":
            out.append({"cle": "irrecevable", "niveau": "critique", "echeance": None,
                        "jours_restants": None, "fait": False,
                        "message": "Dossier declare irrecevable : piece a completer sans delai"})
        return out

    def to_dict(self, aujourdhui: date | None = None) -> dict:
        d = asdict(self)
        d["libelle_statut"] = LIBELLES.get(self.statut, self.statut)
        d["jalons"] = self.jalons(aujourdhui)
        d["prochaine_echeance"] = self.prochaine_echeance(aujourdhui)
        d["alertes"] = self.alertes(aujourdhui)
        d["article_105"] = domaine_de_reference(self.puissance_mw or 0, self.d_km)
        return d


# ---------------------------------------------------------------------------
# Registre
# ---------------------------------------------------------------------------

class Registre:
    def __init__(self, chemin: str = REGISTRE_DEFAUT):
        self.chemin = chemin
        self.demandes: dict[str, Demande] = {}

    def charger(self) -> "Registre":
        if os.path.exists(self.chemin):
            with open(self.chemin, "r", encoding="utf-8") as f:
                brut = json.load(f)
            champs = {f_.name for f_ in Demande.__dataclass_fields__.values()}
            for item in brut.get("demandes", []):
                propre = {k: v for k, v in item.items() if k in champs}
                self.demandes[propre["id"]] = Demande(**propre)
        return self

    def sauver(self) -> None:
        payload = {
            "genere_le": datetime.now().isoformat(timespec="seconds"),
            "demandes": [asdict(d) for d in self.demandes.values()],
        }
        with open(self.chemin, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def ajouter(self, d: Demande) -> None:
        if d.id in self.demandes:
            raise SystemExit(f"La demande {d.id} existe deja.")
        self.demandes[d.id] = d

    def get(self, id_: str) -> Demande:
        if id_ not in self.demandes:
            raise SystemExit(f"Demande inconnue : {id_}")
        return self.demandes[id_]

    def export(self, aujourdhui: date | None = None) -> dict:
        today = aujourdhui or date.today()
        items = [d.to_dict(today) for d in self.demandes.values()]
        compteurs = {cle: 0 for cle, _ in ETAPES}
        for it in items:
            compteurs[it["statut"]] = compteurs.get(it["statut"], 0) + 1
        return {
            "genere_le": datetime.now().isoformat(timespec="seconds"),
            "date_reference": today.isoformat(),
            "demandes": items,
            "compteurs": compteurs,
            "puissance_totale_mw": sum(d.puissance_mw or 0 for d in self.demandes.values()),
            "alertes": [
                {"id": it["id"], "site": it["site"] or it["projet"], **a}
                for it in items for a in it["alertes"]
            ],
        }


# ---------------------------------------------------------------------------
# Payload pour le robot de depot
# ---------------------------------------------------------------------------

def payload_d1(d: Demande) -> dict:
    """Traduit une demande en cles attendues par le mapping du formulaire reel."""
    a105 = domaine_de_reference(d.puissance_mw or 0, d.d_km)
    hypotheses = [f"{d.puissance_mw:g} MW"]
    if d.hypothese_secondaire_mw:
        hypotheses.append(f"{d.hypothese_secondaire_mw:g} MW")
    nom, prenom = d.demandeur_nom, d.demandeur_prenom
    if not nom and d.demandeur_contact:
        morceaux = d.demandeur_contact.split()
        nom, prenom = morceaux[-1], " ".join(morceaux[:-1])
    return {
        "id": d.id,
        "I_type_demande": d.nature,
        "II_demandeur": {
            "societe": d.demandeur_societe,
            "siren": d.demandeur_siren,
            "nom": nom,
            "prenom": prenom,
            "fonction": d.demandeur_fonction,
            "telephone": d.demandeur_tel,
            "courriel": d.demandeur_mail,
            "mandataire": "Oui" if d.demandeur_mandataire else "Non",
        },
        "IV_site": {
            "nom_site": d.site or d.projet,
            "commune": d.commune,
            "departement": d.departement,
            "latitude": f"{d.lat:.5f}" if d.lat else "",
            "longitude": f"{d.lon:.5f}" if d.lon else "",
            "date_mise_a_disposition": d.date_mise_a_disposition or "",
        },
        "V_technique": {
            "puissance_raccordement_mw": d.puissance_mw,
            "raccordement_hta_existant": "Oui" if d.raccordement_hta_existant else "Non",
            "demande_hta_en_cours": "Oui" if d.demande_hta_en_cours else "Non",
            "alimentations_supplementaires": str(d.alimentations_supplementaires),
            "puissance_court_circuit_min": "Oui" if d.besoin_pcc_min else "Non",
            "puissance_mise_en_securite_mw": d.puissance_mise_en_securite_mw,
        },
        "VI_complements": d.commentaire[:500],
        "VI_complements_techniques": d.complements_techniques[:1000],
        "pieces": {
            "extrait_cadastral": d.piece_cadastre,
            "plan_installation": d.piece_plan,
        },
        "controle_article_105": a105,
        "hypotheses_declarees": hypotheses,
        "checklist_recevabilite": checklist(d),
    }


def checklist(d: Demande) -> list[dict]:
    """Controles bloquants avant depot."""
    def ligne(ok, libelle):
        return {"ok": bool(ok), "libelle": libelle}
    cadastre = bool(d.piece_cadastre) or any("cadastr" in p.lower() for p in d.pieces)
    return [
        ligne(d.demandeur_societe and d.demandeur_siren and len(d.demandeur_siren) == 9,
              "Demandeur identifie, SIREN de 9 caracteres (valide en direct par RTE)"),
        ligne(d.demandeur_nom or d.demandeur_contact, "Nom et prenom de l'interlocuteur"),
        ligne(d.demandeur_mail and d.demandeur_tel, "Coordonnees de contact renseignees"),
        ligne(d.site and d.commune, "Site et commune renseignes"),
        ligne(d.lat and d.lon, "Coordonnees du point de connexion renseignees"),
        ligne(d.puissance_mw and d.puissance_mw > 0, "Puissance de raccordement renseignee"),
        ligne(d.date_mise_a_disposition, "Date de mise a disposition souhaitee renseignee"),
        ligne(cadastre, "Extrait cadastral joint, PDF de moins de 2 Mo "
                        "(facultatif dans le formulaire, bloquant pour la recevabilite)"),
        ligne(not d.demandeur_mandataire or any("mandat" in p.lower() for p in d.pieces),
              "Mandat joint si depot en qualite de mandataire"),
        ligne(d.d_km is not None, "Distance d renseignee pour le controle article 105"),
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_init(args):
    r = Registre(args.registre)
    if os.path.exists(args.registre):
        print(f"Registre deja present : {args.registre}")
        return
    r.sauver()
    print(f"Registre cree : {args.registre}")


def cmd_add(args):
    r = Registre(args.registre).charger()
    champs = {f_.name for f_ in Demande.__dataclass_fields__.values()}
    data = {"id": args.id}
    for paire in args.champ or []:
        if "=" not in paire:
            raise SystemExit(f"Champ mal forme : {paire}")
        cle, val = paire.split("=", 1)
        if cle not in champs:
            raise SystemExit(f"Champ inconnu : {cle}")
        data[cle] = _cast(cle, val)
    r.ajouter(Demande(**data))
    r.sauver()
    print(f"Demande ajoutee : {args.id}")


def _cast(cle: str, val: str):
    typ = Demande.__dataclass_fields__[cle].type
    if "list" in str(typ):
        return [x.strip() for x in val.split(";") if x.strip()]
    if "bool" in str(typ):
        return val.strip().lower() in ("1", "true", "oui", "yes", "o")
    if "float" in str(typ):
        return None if val == "" else float(val.replace(",", "."))
    if "int" in str(typ):
        return None if val == "" else int(val)
    return val


def cmd_set(args):
    r = Registre(args.registre).charger()
    d = r.get(args.id)
    champs = {f_.name for f_ in Demande.__dataclass_fields__.values()}
    for paire in args.champ:
        cle, val = paire.split("=", 1)
        if cle not in champs:
            raise SystemExit(f"Champ inconnu : {cle}")
        setattr(d, cle, _cast(cle, val))
    r.sauver()
    print(f"{args.id} mis a jour : {', '.join(p.split('=')[0] for p in args.champ)}")


def cmd_list(args):
    r = Registre(args.registre).charger()
    if not r.demandes:
        print("Registre vide.")
        return
    largeur = max(len(d.id) for d in r.demandes.values())
    print(f"{'ID'.ljust(largeur)}  {'SITE':<22} {'MW':>7}  {'STATUT':<20} PROCHAINE ECHEANCE")
    print("-" * (largeur + 78))
    for d in r.demandes.values():
        pe = d.prochaine_echeance()
        txt = "-" if not pe else f"{pe['echeance']}  ({pe['jours_restants']:+d} j)  {pe['libelle']}"
        print(f"{d.id.ljust(largeur)}  {(d.site or d.projet)[:22]:<22} "
              f"{d.puissance_mw:>7.0f}  {d.statut:<20} {txt}")


def cmd_alertes(args):
    r = Registre(args.registre).charger()
    export = r.export()
    if not export["alertes"]:
        print("Aucune alerte.")
        return
    ordre = {"critique": 0, "attention": 1}
    for a in sorted(export["alertes"], key=lambda x: (ordre.get(x["niveau"], 2), x["id"])):
        marque = "!!" if a["niveau"] == "critique" else " ~"
        print(f"{marque} [{a['id']}] {a['message']}")


def cmd_payload(args):
    r = Registre(args.registre).charger()
    p = payload_d1(r.get(args.id))
    sortie = args.sortie or f"payload_D1_{args.id}.json"
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    manquants = [c["libelle"] for c in p["checklist_recevabilite"] if not c["ok"]]
    print(f"Payload ecrit : {sortie}")
    print(f"Domaine de tension impose : {p['controle_article_105']['domaine']}")
    if manquants:
        print("\nBLOQUANTS AVANT DEPOT :")
        for m in manquants:
            print(f"  - {m}")
    else:
        print("\nChecklist de recevabilite complete.")


def cmd_export(args):
    r = Registre(args.registre).charger()
    sortie = args.sortie or "2026_09_03_dcex_racc_dashboard_data.json"
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(r.export(), f, ensure_ascii=False, indent=2)
    print(f"Export dashboard ecrit : {sortie}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Suivi de la chaine de raccordement RTE")
    p.add_argument("--registre", default=REGISTRE_DEFAUT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    a = sub.add_parser("add")
    a.add_argument("--id", required=True)
    a.add_argument("--champ", action="append", help="cle=valeur, repetable")
    a.set_defaults(func=cmd_add)

    s = sub.add_parser("set")
    s.add_argument("id")
    s.add_argument("champ", nargs="+", help="cle=valeur")
    s.set_defaults(func=cmd_set)

    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("alertes").set_defaults(func=cmd_alertes)

    pa = sub.add_parser("payload")
    pa.add_argument("id")
    pa.add_argument("--sortie")
    pa.set_defaults(func=cmd_payload)

    e = sub.add_parser("export")
    e.add_argument("--sortie")
    e.set_defaults(func=cmd_export)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
