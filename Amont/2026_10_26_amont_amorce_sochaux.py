# -*- coding: utf-8 -*-
"""
Charge le site de Sochaux dans Amont pour les premiers tests du robot D1.

Reprend la demande preparee le 08/10/2026 (Sochaux/2026_10_08_demande_etude_exploratoire_RTE_Sochaux_300MW.md) :
  - cree le projet SOC (s'il n'existe pas) ;
  - importe les valeurs dans la fiche identite, en « a verifier » (sauf le nom SOC01 et l'interlocuteur, saisis
    comme dans la note) ;
  - lit les deux textes (commentaire de la demande, elements complementaires) directement dans la note ;
  - cree la demande SOC-EE (RTE etude exploratoire) ;
  - recupere l'extrait du plan cadastral officiel sur cadastre.gouv.fr (10 parcelles, Sochaux et Exincourt) et le
    joint comme extrait cadastral ; a defaut, joint Sochaux/Plan_cadastre_sochaux.pdf.
Rejouable : ce qui existe deja est laisse en place.

Usage, depuis le dossier Amont du poste (Tailscale connecte) :
    python 2026_10_26_amont_amorce_sochaux.py
    python 2026_10_26_amont_amorce_sochaux.py --amont http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
NOTE = ICI.parent / "Sochaux" / "2026_10_08_demande_etude_exploratoire_RTE_Sochaux_300MW.md"
EXTRAIT = ICI.parent / "Sochaux" / "Plan_cadastre_sochaux.pdf"

VALEURS = {
    "commune": "Sochaux",
    "communes_secondaires": "Exincourt",
    # etude de faisabilite du 23/09 : 4 parcelles sur Sochaux (14,19 ha), 5 sur Exincourt (16,09 ha), plus AH 382
    "parcelles": "Sochaux : AH 367, AH 381, AH 382, AI 6, AI 8 ; Exincourt : AD 45, AD 46, AE 27, AE 30, AE 31",
    "code_insee": "25547",
    "departement": "25",
    "region": "Bourgogne-Franche-Comté",
    "lat": 47.510701,
    "lon": 6.832006,
    "surface_ha": 30.28,
    "puissance_mw": 300,
    "date_mise_a_disposition": "2031-12-31",
    "alimentations_secours": 1,
    "poste_rte": "Étupes",
    "tension_kv": 225,
    "distance_poste_km": 1.56,
}
INTERLOCUTEUR = {
    "nom_installation": "SOC01",
    "interlocuteur_nom": "Obadia",
    "interlocuteur_prenom": "Brayane",
    "interlocuteur_fonction": "VP head of leasing and tenant relationship",
    "interlocuteur_tel": "0675727272",
    "interlocuteur_mail": "bobadia@castignac.com",
}


def appel(base: str, chemin: str, methode: str = "GET", corps=None, multipart: tuple | None = None):
    en_tetes = {"X-Amont-Auteur": urllib.parse.quote("amorce Sochaux")}
    donnees = None
    if corps is not None:
        donnees = json.dumps(corps).encode("utf-8")
        en_tetes["Content-Type"] = "application/json"
    if multipart:
        champs, (nom_champ, chemin_fichier) = multipart
        borne = uuid.uuid4().hex
        morceaux = []
        for k, v in champs.items():
            morceaux.append(f'--{borne}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        morceaux.append(f'--{borne}\r\nContent-Disposition: form-data; name="{nom_champ}"; filename="{chemin_fichier.name}"\r\n'
                        f"Content-Type: application/pdf\r\n\r\n".encode() + chemin_fichier.read_bytes() + b"\r\n")
        morceaux.append(f"--{borne}--\r\n".encode())
        donnees = b"".join(morceaux)
        en_tetes["Content-Type"] = f"multipart/form-data; boundary={borne}"
    req = urllib.request.Request(base + "/api" + chemin, data=donnees, method=methode, headers=en_tetes)
    try:
        with urllib.request.urlopen(req, timeout=240 if "extrait-cadastral" in chemin else 30) as r:
            txt = r.read()
            return r.status, json.loads(txt or b"null")
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, {"erreur": txt}


def textes_de_la_note() -> tuple[str, str]:
    if not NOTE.exists():
        print(f"Note introuvable ({NOTE}) : contexte et éléments complémentaires laissés vides.")
        return "", ""
    blocs = re.findall(r"```\s*\n(.*?)\n```", NOTE.read_text(encoding="utf-8"), re.S)
    blocs = [b.strip() for b in blocs]
    return (blocs[0] if blocs else ""), (blocs[1] if len(blocs) > 1 else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amont", default=os.environ.get("AMONT_URL", "https://amont.arinaudo.fr"))
    base = ap.parse_args().amont.rstrip("/")

    code, r = appel(base, "/sante")
    if code != 200:
        print(f"Amont injoignable : {r}")
        return 1
    print(f"Amont {r['version']} : {r['projets']} projets.")

    code, r = appel(base, "/projets/SOC")
    if code == 404:
        code, r = appel(base, "/projets", "POST", {"code": "SOC", "nom": "Datacenter Sochaux PSA Sud", "commune": "Sochaux",
                                                   "departement": "25", "puissance_cible_mw": 300,
                                                   "notes": "Site PSA Sud, à cheval sur Sochaux et Exincourt. Poste 225 kV d'Étupes à 1,6 km."})
        print("Projet SOC créé." if code == 201 else f"Création du projet refusée : {r}")
    else:
        print("Projet SOC déjà présent.")

    contexte, complements = textes_de_la_note()
    valeurs = dict(VALEURS)
    if contexte:
        valeurs["contexte"] = contexte
    if complements:
        valeurs["complements_techniques"] = complements
    code, r = appel(base, "/sites/SOC/fiche/import", "POST", {"origine": "note du 08/10", "valeurs": valeurs})
    print(f"Fiche : {r.get('remplis', 0)} champs remplis à vérifier, {r.get('en_attente', 0)} valeurs divergentes." if code == 200 else f"Import refusé : {r}")
    code, r = appel(base, "/sites/SOC/fiche", "PATCH", INTERLOCUTEUR)
    print("Nom de l'installation (SOC01) et interlocuteur de la note du 08/10 (Brayane Obadia) saisis." if code == 200 else f"Interlocuteur refusé : {r}")

    code, r = appel(base, "/sites/SOC/preparer", "POST", {"filieres": ["rte_ee"]})
    if code == 200 and r:
        print(f"Demande créée : {r[0]['id']}.")
    code, d = appel(base, "/demandes/SOC-EE")
    if code != 200:
        print("Demande SOC-EE introuvable : vérifier dans le site.")
        return 1
    if not any(p["type"] == "extrait_cadastral" for p in d.get("pieces", [])):
        print("Extrait du plan cadastral : récupération sur cadastre.gouv.fr (30 s à 1 min)…", flush=True)
        code, r = appel(base, "/sites/SOC/extrait-cadastral", "POST", {})
        if code == 200:
            print("  " + r["bilan"])
            for a in r["avertissements"]:
                print("  attention : " + a)
        else:
            print(f"  échec : {r.get('erreur', r)}")
    code, d = appel(base, "/demandes/SOC-EE")
    if not any(p["type"] == "extrait_cadastral" for p in d.get("pieces", [])):
        if EXTRAIT.exists():
            code, r = appel(base, "/demandes/SOC-EE/pieces", "POST", multipart=({"type": "extrait_cadastral"}, ("fichier", EXTRAIT)))
            print("Extrait cadastral joint (Plan_cadastre_sochaux.pdf, à confirmer comme extrait officiel)." if code == 201 else f"Pièce refusée : {r}")
        else:
            print(f"Pas d'extrait cadastral trouvé ({EXTRAIT}).")
    else:
        print("Extrait cadastral déjà joint.")

    code, plan = appel(base, "/demandes/SOC-EE/d1")
    if code == 200:
        print("\nPlan D1 : " + ("prêt pour le robot." if plan["pret"] else "manque " + " ; ".join(plan["manquants"])))
        for a in plan["alertes"]:
            print("  attention : " + a)
    print(f"\nSuite : ouvrir {base}/#/site/SOC pour relire la fiche, puis :")
    print("  python 2026_10_26_amont_robot_d1.py --demande SOC-EE --simulation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
