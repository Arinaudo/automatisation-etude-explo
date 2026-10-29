"""Import initial du registre Amont.

    python 2026_09_18_amont_import.py                       # charge 2026_09_18_amont_amorce.json
    python 2026_09_18_amont_import.py --fichier autre.json  # meme format
    python 2026_09_18_amont_import.py --registre-0903 "../Suivi/2026_09_03_dcex_racc_registre.json"
    python 2026_09_18_amont_import.py --etudes "../Etudes exploratoires RTE"

Format du fichier d'amorce : {"projets": [...], "demandes": [...]}, une demande aplatie
par entree, avec "projet_code" et "filiere". Les entrees deja presentes sont ignorees,
l'import est donc rejouable. Le registre JSON du 03/09 (robot D1) est importe en filiere
rte_ee. Avec --etudes, les PDF d'etudes RTE du dossier sont copies dans les pieces de la
demande dont le numero d'etude figure dans le nom du fichier.
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from amont_core.stockage import Registre  # noqa: E402


def importer_amorce(registre: Registre, chemin: Path) -> None:
    data = json.loads(chemin.read_text(encoding="utf-8"))
    n_p = n_d = 0
    for p in data.get("projets", []):
        if registre.obtenir_projet(p["code"]):
            continue
        registre.creer_projet(p, auteur="import")
        n_p += 1
    for d in data.get("demandes", []):
        if registre.obtenir_demande(d["id"]):
            continue
        registre.creer_demande(d, auteur="import", origine="import")
        n_d += 1
    print(f"{chemin.name} : {n_p} projet(s) et {n_d} demande(s) importes.")


def importer_registre_0903(registre: Registre, chemin: Path) -> None:
    data = json.loads(chemin.read_text(encoding="utf-8"))
    n = 0
    for d in data.get("demandes", []):
        id_ = d.get("id")
        if not id_ or registre.obtenir_demande(id_):
            continue
        code = id_.split("-")[0]
        if not registre.obtenir_projet(code):
            registre.creer_projet({"code": code, "nom": d.get("projet") or code, "commune": d.get("commune"),
                                   "departement": d.get("departement"), "lat": d.get("lat"), "lon": d.get("lon"),
                                   "puissance_cible_mw": d.get("puissance_mw")}, auteur="import")
        d = dict(d)
        d["projet_code"] = code
        d["filiere"] = "rte_ee"
        registre.creer_demande(d, auteur="import", origine="import")
        n += 1
    print(f"{chemin.name} : {n} demande(s) importee(s) en filiere RTE EE.")


def rattacher_etudes(registre: Registre, dossier: Path, fichiers: Path) -> None:
    demandes = registre.lister_demandes(filiere="rte_ee")
    par_num = {d.get("num_etude"): d for d in demandes if d.get("num_etude")}
    n = 0
    for pdf in sorted(dossier.glob("*.pdf")):
        m = re.search(r"(\d{2}-\d{4})", pdf.name)
        if not m or m.group(1) not in par_num:
            print(f"  ignore : {pdf.name} (aucune demande avec ce numero d'etude)")
            continue
        d = par_num[m.group(1)]
        if any(p["nom_fichier"] == pdf.name for p in registre.lister_pieces(d["id"])):
            continue
        cible = fichiers / d["projet_code"] / "rte_ee" / pdf.name
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, cible)
        registre.ajouter_piece(d["id"], "etude_recue", pdf.name, str(cible.relative_to(fichiers)).replace("\\", "/"),
                               cible.stat().st_size, auteur="import")
        n += 1
        print(f"  {pdf.name} -> {d['id']}")
    print(f"{n} etude(s) rattachee(s).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Import Amont")
    ap.add_argument("--fichier", default=str(RACINE / "2026_09_18_amont_amorce.json"))
    ap.add_argument("--registre-0903", help="registre JSON du robot D1 (03/09/2026)")
    ap.add_argument("--etudes", help="dossier des PDF d'etudes exploratoires RTE")
    args = ap.parse_args()

    registre = Registre(os.environ.get("AMONT_DB", RACINE / "donnees" / "amont.sqlite"))
    fichiers = Path(os.environ.get("AMONT_FICHIERS", RACINE / "donnees" / "raccordement"))

    f = Path(args.fichier)
    if f.exists():
        importer_amorce(registre, f)
    if args.registre_0903:
        importer_registre_0903(registre, Path(args.registre_0903))
    if args.etudes:
        rattacher_etudes(registre, Path(args.etudes), fichiers)
    print("Etat du registre :", registre.compte())


if __name__ == "__main__":
    main()
