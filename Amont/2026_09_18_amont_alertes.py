"""Courriel du matin d'Amont.

    python 2026_09_18_amont_alertes.py --apercu     # affiche ce qui partirait, n'envoie rien
    python 2026_09_18_amont_alertes.py              # envoie si necessaire et marque les alertes

Configuration SMTP dans un fichier `.env` a cote de ce script (jamais versionne) :

    AMONT_SMTP_HOTE=smtp.office365.com
    AMONT_SMTP_PORT=587
    AMONT_SMTP_UTILISATEUR=registre@castignac.fr
    AMONT_SMTP_MOT_DE_PASSE=...
    AMONT_SMTP_EXPEDITEUR=registre@castignac.fr
    AMONT_DESTINATAIRES=a.rinaudo@castignac.fr,responsable@castignac.fr
    AMONT_URL=https://amont.castignac.fr

A planifier chaque matin a 8 h (cron sur le serveur, Planificateur de taches sous Windows).
"""

import argparse
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))


def charger_env() -> None:
    f = RACINE / ".env"
    if not f.exists():
        return
    for ligne in f.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        k, v = ligne.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description="Courriel du matin Amont")
    ap.add_argument("--apercu", action="store_true", help="n'envoie rien, n'enregistre rien")
    args = ap.parse_args()
    charger_env()

    from amont_core import alertes
    from amont_core.stockage import Registre

    registre = Registre(os.environ.get("AMONT_DB", RACINE / "donnees" / "amont.sqlite"))
    url = os.environ.get("AMONT_URL", "http://localhost:8000").rstrip("/")
    a_envoyer, toutes = alertes.selectionner(registre)
    objet, corps = alertes.composer(registre, a_envoyer, url)

    print(f"{len(toutes)} alerte(s) en cours, {len(a_envoyer)} a envoyer ce matin.")
    if not a_envoyer:
        print("Rien a envoyer.")
        return
    print("Objet :", objet)
    print(corps)
    if args.apercu:
        return

    destinataires = [d.strip() for d in os.environ.get("AMONT_DESTINATAIRES", "").split(",") if d.strip()]
    if not destinataires or not os.environ.get("AMONT_SMTP_HOTE"):
        print("SMTP ou destinataires non configures dans .env : envoi impossible, alertes non marquees.")
        sys.exit(2)
    alertes.envoyer(objet, corps, destinataires, {
        "hote": os.environ["AMONT_SMTP_HOTE"],
        "port": os.environ.get("AMONT_SMTP_PORT", 587),
        "utilisateur": os.environ.get("AMONT_SMTP_UTILISATEUR"),
        "mot_de_passe": os.environ.get("AMONT_SMTP_MOT_DE_PASSE", ""),
        "expediteur": os.environ.get("AMONT_SMTP_EXPEDITEUR", os.environ.get("AMONT_SMTP_UTILISATEUR")),
        "tls": os.environ.get("AMONT_SMTP_TLS", "1") != "0",
    })
    registre.marquer_notifie(a_envoyer)
    print(f"Envoye a {', '.join(destinataires)}.")


if __name__ == "__main__":
    main()
