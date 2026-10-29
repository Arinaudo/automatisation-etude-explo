"""Courriel du matin d'Amont : composition et regle de renvoi.

Un seul courriel aux deux suiveurs, uniquement s'il y a quelque chose a dire.
Une alerte deja notifiee n'est renvoyee que si elle passe de warn a crit, ou tous les
7 jours tant qu'elle reste depassee (cahier des charges du 17/09/2026, section 6).
"""

from __future__ import annotations

from datetime import date, datetime

from . import regles
from .stockage import Registre


def selectionner(registre: Registre, aujourdhui: date | None = None) -> tuple[list[dict], list[dict]]:
    """Retourne (a_envoyer, toutes) : les alertes qui justifient un envoi ce matin, et l'ensemble."""
    auj = aujourdhui or date.today()
    toutes = registre.a_notifier()
    a_envoyer = []
    for it in toutes:
        if it["dernier_envoi"] is None:
            a_envoyer.append(it)
            continue
        if it["severite"] == "crit" and it["severite_precedente"] != "crit":
            a_envoyer.append(it)
            continue
        if it["severite"] == "crit":
            dernier = datetime.fromisoformat(it["dernier_envoi"]).date()
            if (auj - dernier).days >= 7:
                a_envoyer.append(it)
    return a_envoyer, toutes


def composer(registre: Registre, a_envoyer: list[dict], url_base: str, aujourdhui: date | None = None) -> tuple[str, str]:
    """Retourne (objet, corps texte). Corps vide si rien a envoyer."""
    auj = aujourdhui or date.today()
    jour = auj.strftime("%d/%m/%Y")
    projets = {p["code"]: p["nom"] for p in registre.lister_projets()}
    if not a_envoyer:
        return f"Raccordements, {jour} : rien à signaler", ""
    n = len(a_envoyer)
    objet = f"Raccordements, {jour} : {n} point{'s' if n > 1 else ''} à traiter"
    crit = [a for a in a_envoyer if a["severite"] == "crit"]
    warn = [a for a in a_envoyer if a["severite"] != "crit"]
    lignes = []

    def bloc(titre, items):
        if not items:
            return
        lignes.append(titre)
        for a in items:
            lignes.append(f"  {a['demande_id']}  {projets.get(a['projet'], a['projet'])}  {regles.FILIERES[a['filiere']]['court']}  {a['texte']}")
            lignes.append(f"  {url_base}/#/demande/{a['demande_id']}")
        lignes.append("")

    bloc("Dépassées", crit)
    bloc("À surveiller : sous 14 jours, validation d'envoi, courriels sans réponse", warn)
    lignes.append(f"Registre : {url_base}")
    lignes.append("Ce message est généré par le registre des raccordements. Une échéance déjà signalée n'est renvoyée que si elle passe en dépassement, ou tous les 7 jours tant qu'elle le reste.")
    return objet, "\n".join(lignes)


def apercu(registre: Registre, url_base: str, aujourdhui: date | None = None) -> dict:
    """Ce que donnerait l'envoi de ce matin, sans marquer les notifications."""
    a_envoyer, toutes = selectionner(registre, aujourdhui)
    objet, corps = composer(registre, a_envoyer, url_base, aujourdhui)
    prochaines = []
    if not a_envoyer:
        for d in registre.lister_demandes():
            pe = d.get("prochaine_echeance")
            if pe:
                prochaines.append({"demande_id": d["id"], "projet": d["projet_code"], "date": pe["date"], "libelle": pe["libelle"]})
        prochaines.sort(key=lambda x: x["date"])
        prochaines = prochaines[:5]
    return {"objet": objet, "corps": corps, "envoi": bool(a_envoyer), "nb_alertes": len(toutes),
            "nb_a_envoyer": len(a_envoyer), "prochaines": prochaines}


def envoyer(objet: str, corps: str, destinataires: list[str], smtp: dict) -> None:
    """Envoi SMTP. smtp : hote, port, utilisateur, mot_de_passe, expediteur, tls (bool)."""
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = objet
    msg["From"] = smtp["expediteur"]
    msg["To"] = ", ".join(destinataires)
    msg.set_content(corps)
    with smtplib.SMTP(smtp["hote"], int(smtp.get("port", 587))) as s:
        if smtp.get("tls", True):
            s.starttls()
        if smtp.get("utilisateur"):
            s.login(smtp["utilisateur"], smtp["mot_de_passe"])
        s.send_message(msg)
