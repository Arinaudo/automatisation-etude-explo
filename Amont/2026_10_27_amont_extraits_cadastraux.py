"""Recupere l'extrait du plan cadastral officiel (cadastre.gouv.fr) de chaque site d'Amont.

Deux usages :

1. Par Amont (defaut) : pour chaque site, demande au serveur de recuperer l'extrait a partir des
   parcelles de la fiche. Le PDF est range dans les sources du site et joint comme « extrait
   cadastral » aux demandes RTE etude exploratoire. Meme chose que le bouton du site.

    python 2026_10_27_amont_extraits_cadastraux.py                      # tous les sites sans extrait
    python 2026_10_27_amont_extraits_cadastraux.py --site SOC           # un site (option repetable)
    python 2026_10_27_amont_extraits_cadastraux.py --forcer             # tous, meme ceux deja faits
    python 2026_10_27_amont_extraits_cadastraux.py --site SOC --centrer "AH 367" --echelle 2500
    python 2026_10_27_amont_extraits_cadastraux.py --liste              # etat des sites, sans rien recuperer

2. Hors Amont : directement depuis cadastre.gouv.fr, PDF ecrit dans un dossier.

    python 2026_10_27_amont_extraits_cadastraux.py --parcelles "AH 367, AH 381" --commune Sochaux
        --departement 25 --sortie .

Adresse d'Amont : --amont, sinon la variable AMONT_URL, sinon https://amont.arinaudo.fr (Tailscale actif).
Bibliotheque standard seulement (le mode hors Amont utilise amont_core, a cote de ce script).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AMONT_DEFAUT = os.environ.get("AMONT_URL", "https://amont.arinaudo.fr")
DELAI = 240  # une recuperation prend 20 s a 1 min ; marge pour les sites a nombreuses parcelles
PAUSE_ENTRE_SITES = 3


def appel(base: str, chemin: str, corps: dict | None = None, delai: int = 30):
    url = base.rstrip("/") + "/api" + chemin
    donnees = json.dumps(corps).encode() if corps is not None else None
    req = urllib.request.Request(url, data=donnees, method="POST" if corps is not None else "GET",
                                 headers={"Content-Type": "application/json",
                                          "X-Amont-Auteur": urllib.parse.quote("script extraits cadastraux")})
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("erreur") or str(e)
        except ValueError:
            msg = str(e)
        raise RuntimeError(msg) from None
    except OSError as e:
        raise RuntimeError(f"Amont injoignable à {base} ({e}). Tailscale est-il connecté ?") from None


def par_amont(args) -> int:
    base = args.amont
    sante = appel(base, "/sante")
    print(f"Amont {sante['version']} : {sante['projets']} sites, {base}\n")
    codes = args.site or [s["code"] for s in appel(base, "/sites")]
    faits = erreurs = ignores = 0
    for i, code in enumerate(codes):
        try:
            site = appel(base, f"/sites/{urllib.parse.quote(code)}")
        except RuntimeError as e:
            print(f"{code:<6} introuvable : {e}")
            erreurs += 1
            continue
        nom = site["projet"]["nom"]
        parc = (site["fiche"].get("parcelles") or {}).get("valeur") or ""
        ex = site.get("extrait_cadastral")
        etat = f"extrait du {ex['le'][:10]}" if ex else "pas d'extrait"
        if args.liste:
            print(f"{code:<6} {nom[:38]:<38} {etat:<22} {parc[:60] or '(parcelles à renseigner)'}")
            continue
        if not parc:
            print(f"{code:<6} {nom[:38]:<38} ignoré : parcelles à renseigner dans la fiche du site")
            ignores += 1
            continue
        if ex and not args.forcer and not args.centrer:
            print(f"{code:<6} {nom[:38]:<38} déjà fait ({etat}), --forcer pour refaire")
            ignores += 1
            continue
        print(f"{code:<6} {nom[:38]:<38} récupération ({parc[:50]}) …", flush=True)
        corps = {"joindre": not args.sans_joindre}
        if args.centrer:
            corps["centrer_sur"] = args.centrer
        if args.echelle:
            corps["echelle"] = args.echelle
        try:
            r = appel(base, f"/sites/{urllib.parse.quote(code)}/extrait-cadastral", corps, delai=DELAI)
        except RuntimeError as e:
            print(f"       ÉCHEC : {e}")
            erreurs += 1
            continue
        faits += 1
        print(f"       {r['bilan']}")
        if r["pieces"]:
            print(f"       joint à : {', '.join(p['demande_id'] for p in r['pieces'])}")
        else:
            print("       aucune demande RTE étude exploratoire : rangé dans les sources du site seulement")
        for a in r["avertissements"]:
            print(f"       ⚠ {a}")
        if r.get("point_a_verifier"):
            print("       ⚑ point signalé à vérifier sur la fiche du site")
        if i < len(codes) - 1:
            time.sleep(PAUSE_ENTRE_SITES)
    if not args.liste:
        print(f"\n{faits} extrait(s) récupéré(s), {ignores} ignoré(s), {erreurs} échec(s).")
    return 1 if erreurs else 0


def hors_amont(args) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from amont_core import cadastre
    try:
        r = cadastre.extrait_site(args.parcelles, args.commune, args.departement, args.insee, args.autres_communes or "",
                                  centrer_sur=args.centrer, echelle=args.echelle, nom_site=args.nom or args.commune)
    except cadastre.ErreurCadastre as e:
        print(f"ÉCHEC : {e}")
        return 1
    dossier = Path(args.sortie)
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / r.nom_fichier
    cible.write_bytes(r.pdf)
    print(r.bilan())
    for a in r.avertissements:
        print(f"⚠ {a}")
    print(f"Écrit : {cible.resolve()}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Extraits du plan cadastral (cadastre.gouv.fr) des sites d'Amont")
    ap.add_argument("--amont", default=AMONT_DEFAUT, help="adresse d'Amont")
    ap.add_argument("--site", action="append", help="code du site, ex. SOC (répétable) ; tous par défaut")
    ap.add_argument("--forcer", action="store_true", help="refait aussi les sites qui ont déjà un extrait")
    ap.add_argument("--liste", action="store_true", help="affiche l'état des sites sans rien récupérer")
    ap.add_argument("--centrer", help="parcelle sur laquelle centrer l'extrait, ex. « AH 367 »")
    ap.add_argument("--echelle", type=int, choices=[500, 1000, 1250, 1500, 2000, 2500, 4000, 5000])
    ap.add_argument("--sans-joindre", action="store_true", help="range l'extrait dans les sources sans le joindre aux demandes")
    g = ap.add_argument_group("hors Amont")
    g.add_argument("--parcelles", help="ex. « AH 367, AH 381 » ou « Exincourt : AD 45 ; Sochaux : AH 367 »")
    g.add_argument("--commune")
    g.add_argument("--departement")
    g.add_argument("--insee")
    g.add_argument("--autres-communes", help="communes où chercher aussi les parcelles, ex. « Exincourt »")
    g.add_argument("--nom", help="nom du site pour le nom du fichier")
    g.add_argument("--sortie", default=".", help="dossier du PDF (défaut : dossier courant)")
    args = ap.parse_args()
    if args.parcelles:
        if not args.commune:
            ap.error("--commune est obligatoire avec --parcelles")
        return hors_amont(args)
    return par_amont(args)


if __name__ == "__main__":
    sys.exit(main())
