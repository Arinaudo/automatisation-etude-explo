"""Depose en une fois tous les fichiers d'un dossier dans les sources d'un site, et les lit.

    python 2026_10_07_amont_sources_import.py --site SOC --dossier "..\\Sochaux"
    python 2026_10_07_amont_sources_import.py --site SOC --dossier "..\\Sochaux" --recursif
    python 2026_10_07_amont_sources_import.py --site SOC --nom "Datacenter Sochaux PSA Sud" --dossier "..\\Sochaux"

Le site est cree s'il n'existe pas (avec --nom). Les fichiers sont copies dans donnees/sources/<site>/,
deja presents (meme nom et meme taille) ignores. L'extraction utilise l'IA si ANTHROPIC_API_KEY est posee,
les regles sinon. Peut tourner pendant que le serveur est lance.
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from amont_core import extraction  # noqa: E402
from amont_core.api import DOSSIER_SOURCES, EXTENSIONS_SOURCES, registre  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Import des fichiers sources d'un site dans Amont")
    ap.add_argument("--site", required=True, help="code du site (projet), ex. SOC")
    ap.add_argument("--dossier", required=True, help="dossier contenant les fichiers du site")
    ap.add_argument("--nom", help="nom du site, pour le creer s'il n'existe pas")
    ap.add_argument("--recursif", action="store_true", help="inclure les sous-dossiers")
    args = ap.parse_args()

    code = args.site.upper()
    if not registre.obtenir_projet(code):
        if not args.nom:
            sys.exit(f"Le site {code} n'existe pas : ajoutez --nom pour le creer.")
        registre.creer_projet({"code": code, "nom": args.nom}, "import")
        print(f"Site {code} cree.")

    source = Path(args.dossier)
    fichiers = sorted(source.rglob("*") if args.recursif else source.glob("*"))
    fichiers = [f for f in fichiers if f.is_file() and f.suffix.lower() in EXTENSIONS_SOURCES]
    deja = {(s["nom_fichier"], s["taille_octets"]) for s in registre.lister_sources(code)}
    cible_dossier = DOSSIER_SOURCES / code
    cible_dossier.mkdir(parents=True, exist_ok=True)

    for f in fichiers:
        taille = f.stat().st_size
        if (f.name, taille) in deja:
            print(f"  deja present  {f.name}")
            continue
        cible = cible_dossier / f.name
        i = 1
        while cible.exists():
            cible = cible_dossier / f"{f.stem}_{i}{f.suffix}"
            i += 1
        shutil.copy2(f, cible)
        s = registre.ajouter_source(code, cible.name, str(cible.relative_to(DOSSIER_SOURCES)).replace("\\", "/"), taille, "import")
        res = extraction.extraire(cible, cible.name, registre.valeurs_fiche(code))
        bilan = registre.enregistrer_extraction(s["id"], res, "import")
        print(f"  {res['type_source']:<12} {res['methode']:<7} {len(res['propositions']):>2} valeurs, "
              f"{bilan['remplis']} remplies, {bilan['en_attente']} divergentes  {f.name}"
              + (f"\n               ! {res['erreur']}" if res["erreur"] else ""))

    site = registre.obtenir_site(code)
    print(f"\nFiche {code} : {sum(1 for v in site['fiche'].values() if v['valeur'] not in (None, ''))} champs remplis, "
          f"{len(site['propositions'])} valeurs divergentes a arbitrer.")
    for f, c in site["completude"].items():
        print(f"  {f:<8} {c['taux']:>3} %  manque : {', '.join(c['manquants']) or 'rien'}")


if __name__ == "__main__":
    main()
