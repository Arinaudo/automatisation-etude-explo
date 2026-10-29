"""Teste l'IA locale d'Amont : serveur joignable, modeles presents, vitesse, qualite sur un vrai fichier.

Dans le conteneur du serveur (memes reglages que le site) :
    docker compose exec amont python 2026_10_27_amont_tester_ia.py
    docker compose exec amont python 2026_10_27_amont_tester_ia.py --fichier donnees/sources/SOC/etude.pdf

Sur le poste, en visant un Ollama joignable :
    set AMONT_IA_URL=http://100.116.240.111:11434
    set AMONT_IA_MODELE=qwen3:8b
    set AMONT_IA_MODELE_VISION=gemma3:12b
    python 2026_10_27_amont_tester_ia.py --fichier "..\\Sochaux\\2026-09-23_analysis_Exincourt_fr_interne.pdf"

Trois essais : 1) reponse JSON courte (vitesse) ; 2) extraction sur le fichier donne (valeurs, valeurs ecartees
car introuvables dans le document, duree) ; 3) redaction du commentaire de la D1 sur une fiche type Sochaux.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from amont_core import extraction, ia, redaction  # noqa: E402

FICHE_TYPE = {"nom_installation": "SOC01", "commune": "Sochaux", "communes_secondaires": "Exincourt", "departement": "25",
              "surface_ha": 30.28, "demandeur_societe": "CASTIGNAC", "puissance_mw": 300, "poste_rte": "Étupes",
              "tension_kv": 225, "distance_poste_km": 1.56}


def main() -> int:
    ap = argparse.ArgumentParser(description="Test de l'IA locale d'Amont")
    ap.add_argument("--fichier", help="fichier source à extraire (PDF, Word, image...)")
    ap.add_argument("--sans-redaction", action="store_true")
    args = ap.parse_args()

    print("RÉGLAGES")
    e = ia.etat()
    for k in ("configuree", "api", "url", "modele", "modele_vision", "joignable", "manquants", "erreur"):
        print(f"  {k:<14} {e.get(k)}")
    if e.get("modeles_serveur"):
        print(f"  {'sur le serveur':<14} {', '.join(e['modeles_serveur'])}")
    if not e["configuree"]:
        print("\nIA non configurée : poser AMONT_IA_URL et AMONT_IA_MODELE.")
        return 1
    if e["joignable"] is False or e["manquants"]:
        print("\nÀ corriger avant d'aller plus loin (serveur injoignable ou modèle absent : ollama pull <modèle>).")
        return 1

    print("\n1. RÉPONSE COURTE")
    t = time.time()
    rep, st = ia.demander_json('Reponds en JSON : {"ok": true, "commune": "Sochaux"}',
                               schema={"type": "object", "properties": {"ok": {"type": "boolean"}, "commune": {"type": "string"}}})
    print(f"  {rep}  en {time.time() - t:.1f} s ({st.get('jetons_sortie')} jetons produits)")
    print("  Premier appel souvent plus lent : le modèle se charge en mémoire.")

    if args.fichier:
        f = Path(args.fichier)
        print(f"\n2. EXTRACTION : {f.name}")
        t = time.time()
        r = extraction.extraire(f, f.name, {})
        info = r.get("ia") or {}
        print(f"  méthode {r['methode']}, {info.get('appels', 0)} appel(s) au modèle ({info.get('mode', '')}), {time.time() - t:.0f} s")
        if r["erreur"]:
            print(f"  erreur : {r['erreur']}")
        for p in sorted(r["propositions"], key=lambda x: x["champ"]):
            print(f"  {p['champ']:<26} {str(p['valeur'])[:55]:<55} {p['confiance']:.2f}")
        for x in info.get("ecartees") or []:
            print(f"  écartée (introuvable dans le document) : {x}")

    if not args.sans_redaction:
        print("\n3. RÉDACTION DU COMMENTAIRE D1 (fiche type Sochaux)")
        t = time.time()
        r = redaction.rediger("contexte", FICHE_TYPE)
        print(f"  {r['longueur']} / {r['limite']} caractères, {time.time() - t:.0f} s" + (" (coupé)" if r["coupe"] else ""))
        print("  " + r["texte"])
        if r["nombres_a_verifier"]:
            print(f"  nombres absents de la fiche, à vérifier : {', '.join(r['nombres_a_verifier'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
