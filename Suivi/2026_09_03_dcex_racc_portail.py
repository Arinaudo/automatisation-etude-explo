# -*- coding: utf-8 -*-
"""
DCEX-PORTAIL : robot de pre-remplissage du formulaire D1 dematerialise du
Portail Services RTE (services-rte.com).

REGLE ABSOLUE, NON CONTOURNABLE
------------------------------
Le robot remplit les 4 premieres etapes, ouvre l'ecran 5 VALIDATION, puis
S'ARRETE. Il ne touche jamais a l'interrupteur de certification, et il n'existe
aucune fonction d'envoi dans ce fichier. Deux gestes restent humains : activer
la certification, puis cliquer sur le bouton d'envoi.

Verrous, a trois niveaux :
  1. aucune fonction d'envoi n'existe ici ;
  2. le mapping est refuse au chargement si un CHAMP a remplir porte un libelle
     d'envoi (les notes documentaires, elles, peuvent citer le mot) ;
  3. la liste des controles interdits est verifiee avant chaque clic.

Structure reelle du formulaire, relevee le 04/09/2026 : application Angular
Material, accordeon de 5 etapes, champs reveles progressivement, identifiants
generes positionnellement. La resolution se fait donc par LIBELLE de question,
via un marquage data-dcex pose en une passe a chaque etape.

Installation, sur le poste Windows :
    pip install playwright
    playwright install chromium

Usage :
    python 2026_09_03_dcex_racc_portail.py login
    python 2026_09_03_dcex_racc_portail.py remplir --id AIV-600

Alexis Rinaudo / Castignac - 03/09/2026, revise le 04/09/2026
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

def _playwright():
    """Import differe : la commande verifier tourne sans navigateur."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        sys.exit("Playwright absent. Installer avec :  pip install playwright  "
                 "puis  playwright install chromium")

# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------

ENVOI_AUTOMATIQUE_INTERDIT = True   # ne jamais passer a False

CONTROLES_INTERDITS = [
    "envoyer", "soumettre", "submit", "transmettre", "valider la demande",
    "je certifie", "certification",
]

BASE = Path(__file__).resolve().parent
PROFIL = BASE / "profil_navigateur_rte"
MAPPING = BASE / "2026_09_03_dcex_racc_selecteurs.json"
PREUVES = BASE / "preuves"
URL_PORTAIL = "https://www.services-rte.com/fr/home.html"

# Libelles des mois tels que RTE les expose dans l'attribut aria-label des
# cellules du calendrier. Verifies en direct le 04/09/2026.
MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin",
        "juillet", "aout", "septembre", "octobre", "novembre", "decembre"]
MOIS_ARIA = ["janvier", "f\u00e9vrier", "mars", "avril", "mai", "juin",
             "juillet", "ao\u00fbt", "septembre", "octobre", "novembre", "d\u00e9cembre"]


def horodatage() -> str:
    return datetime.now().strftime("%Y_%m_%d_%Hh%M")


def charge_json(chemin: Path) -> dict:
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def valide_mapping(mapping: dict) -> None:
    """Refuse un mapping dont un CHAMP A REMPLIR porte un libelle d'envoi."""
    for etape in mapping.get("etapes", []):
        for champ in etape.get("champs", []):
            if champ.get("action_robot") == "NE PAS TOUCHER":
                continue
            lib = (champ.get("label") or "").lower()
            for mot in CONTROLES_INTERDITS:
                if mot in lib:
                    raise SystemExit(
                        f"Mapping refuse : le champ '{champ.get('label')}' de l'etape "
                        f"{etape.get('numero')} porte le terme '{mot}'.\n"
                        "Ce robot ne pilote aucun controle d'envoi ni de certification."
                    )


# ---------------------------------------------------------------------------
# Marquage des controles par libelle de question
# ---------------------------------------------------------------------------

JS_MARQUAGE = r"""
() => {
  const n = s => (s || '').replace(/\s+/g, ' ').trim();
  const labelDe = el => {
    let node = el.closest('mat-form-field') || el.closest('mat-radio-group') || el;
    for (let up = 0; up < 7; up++) {
      const p = node.parentElement; if (!p) break;
      let sib = node.previousElementSibling;
      while (sib) {
        const t = n(sib.innerText);
        if (t && t.length < 150 && !/^\*?$/.test(t)) return t;
        sib = sib.previousElementSibling;
      }
      node = p;
    }
    return '';
  };
  const cible = 'input, textarea, mat-select, mat-radio-group, mat-checkbox, mat-slide-toggle';
  let n_ = 0;
  document.querySelectorAll(cible).forEach(el => {
    if (el.type === 'hidden') return;
    const l = labelDe(el);
    if (l) { el.setAttribute('data-dcex', l); n_++; }
  });
  return n_;
}
"""


def norm(s: str) -> str:
    """Normalise un libelle pour la comparaison : minuscules, sans accents."""
    s = (s or "").lower()
    for a, b in [("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("â", "a"),
                 ("î", "i"), ("ï", "i"), ("ô", "o"), ("û", "u"), ("ù", "u"),
                 ("ç", "c"), ("’", "'")]:
        s = s.replace(a, b)
    return " ".join(s.split())


def localise(page, libelle: str, balise: str):
    """Renvoie le locator du controle dont le libelle contient `libelle`."""
    page.evaluate(JS_MARQUAGE)
    cible = norm(libelle)
    elements = page.locator(f"{balise}[data-dcex]")
    for i in range(elements.count()):
        el = elements.nth(i)
        try:
            if cible in norm(el.get_attribute("data-dcex") or ""):
                return el
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Actions elementaires
# ---------------------------------------------------------------------------

def saisir_texte(page, libelle, valeur, lent=False):
    el = localise(page, libelle, "input") or localise(page, libelle, "textarea")
    if el is None:
        return f"champ introuvable : {libelle}"
    if el.get_attribute("readonly") is not None:
        return (f"champ en lecture seule, la saisie clavier est impossible : {libelle}. "
                "Ce champ se renseigne par son widget, pas au clavier.")
    el.scroll_into_view_if_needed()
    el.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    el.type(str(valeur), delay=60 if lent else 15)   # vraies frappes clavier
    page.wait_for_timeout(2500 if lent else 200)
    return None


def choisir_radio(page, libelle, option):
    grp = localise(page, libelle, "mat-radio-group")
    if grp is None:
        return f"groupe introuvable : {libelle}"
    btn = grp.locator("mat-radio-button", has_text=str(option)).first
    btn.scroll_into_view_if_needed()
    btn.click()
    page.wait_for_timeout(700)
    return None


def cocher(page, options):
    for opt in options:
        c = page.locator("mat-checkbox", has_text=str(opt)).first
        c.scroll_into_view_if_needed()
        c.click()
        page.wait_for_timeout(700)
    return None


def choisir_liste(page, libelle, option=None):
    sel = localise(page, libelle, "mat-select")
    if sel is None:
        return f"liste introuvable : {libelle}"
    sel.scroll_into_view_if_needed()
    sel.click()
    page.wait_for_timeout(1200)
    if option:
        page.locator("mat-option", has_text=str(option)).first.click()
    else:
        page.locator("mat-option").first.click()   # ex. code INSEE
    page.wait_for_timeout(700)
    return None


def choisir_date(page, libelle, jjmmaaaa):
    """Selectionne la date dans le calendrier.

    Verifie en direct sur le formulaire RTE le 04/09/2026 :
      - le champ porte readonly="true", AUCUNE saisie clavier n'est possible ;
      - le declencheur n'est pas un mat-datepicker-toggle mais un composant
        maison <cortex-datepicker-icon> ;
      - les cellules du calendrier sont des button.mat-calendar-body-cell dont
        l'attribut aria-label porte la date en toutes lettres : "2035" en vue
        annees, "septembre 2035" en vue mois, "30 septembre 2035" en vue jours.
        C'est le seul ancrage fiable : le texte visible d'une cellule jour est
        le seul numero, donc "5" correspondrait aussi a 15 et 25.
      - le champ porte un attribut min : une date anterieure est refusee.
    """
    try:
        jour, mois, annee = [int(x) for x in str(jjmmaaaa).split("/")]
        aria_annee = str(annee)
        aria_mois = f"{MOIS_ARIA[mois - 1]} {annee}"
        aria_jour = f"{jour} {MOIS_ARIA[mois - 1]} {annee}"
    except (ValueError, IndexError):
        return f"date mal formee, attendu JJ/MM/AAAA : {jjmmaaaa}"

    champ = localise(page, libelle, "input")
    if champ is None:
        return f"champ date introuvable : {libelle}"
    champ.scroll_into_view_if_needed()

    mini = champ.get_attribute("min")
    if mini:
        try:
            borne = datetime.fromisoformat(mini).date()
            if datetime(annee, mois, jour).date() < borne:
                return f"date anterieure au minimum impose par RTE ({borne:%d/%m/%Y})"
        except ValueError:
            pass

    icone = champ.locator(
        "xpath=ancestor::mat-form-field[1]/following-sibling::*//cortex-datepicker-icon "
        "| xpath=ancestor::div[1]//cortex-datepicker-icon")
    if icone.count() == 0:
        icone = page.locator("cortex-datepicker-icon")
    if icone.count() == 0:
        return "declencheur du calendrier introuvable (cortex-datepicker-icon)"
    icone.first.click()
    page.wait_for_timeout(1500)
    if page.locator("mat-calendar").count() == 0:
        return "le calendrier ne s'est pas ouvert"

    # vue mois courant -> vue multi-annees
    page.locator("button.mat-calendar-period-button").click()
    page.wait_for_timeout(900)

    cellule = lambda aria: page.locator(
        f'button.mat-calendar-body-cell[aria-label="{aria}"]')

    # la vue multi-annees affiche 24 annees, le bouton suivant avance d'une page
    for _ in range(10):
        if cellule(aria_annee).count():
            break
        page.locator("button.mat-calendar-next-button").click()
        page.wait_for_timeout(700)
    if not cellule(aria_annee).count():
        return f"annee {annee} hors des plages proposees par le calendrier"
    cellule(aria_annee).first.click()
    page.wait_for_timeout(900)

    if not cellule(aria_mois).count():
        return f"mois introuvable dans le calendrier : {aria_mois}"
    cellule(aria_mois).first.click()
    page.wait_for_timeout(900)

    if not cellule(aria_jour).count():
        return f"jour introuvable ou desactive dans le calendrier : {aria_jour}"
    cellule(aria_jour).first.click()
    page.wait_for_timeout(1200)

    valeur = champ.input_value()
    if not valeur:
        return "le calendrier s'est ferme sans renseigner le champ"
    return None


def joindre(page, index, chemin):
    inputs = page.locator("input[type=file]")
    if inputs.count() <= index:
        return f"emplacement de piece jointe {index} absent"
    taille = os.path.getsize(chemin) / (1024 * 1024)
    if taille > 2:
        return f"{Path(chemin).name} fait {taille:.1f} Mo, la limite RTE est de 2 Mo"
    inputs.nth(index).set_input_files(chemin)
    page.wait_for_timeout(1500)
    return None


def etape_suivante(page):
    btn = page.locator("button", has_text="Suivant").last
    btn.scroll_into_view_if_needed()
    if btn.is_disabled():
        return "bouton Suivant desactive : un champ obligatoire reste invalide"
    btn.click()
    page.wait_for_timeout(3000)
    return None


# ---------------------------------------------------------------------------
# Commandes
# ---------------------------------------------------------------------------

def cmd_login(args):
    PROFIL.mkdir(parents=True, exist_ok=True)
    with _playwright()() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFIL), headless=False, viewport={"width": 1500, "height": 950},
            locale="fr-FR", accept_downloads=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(args.url or URL_PORTAIL, wait_until="domcontentloaded")
        print("\nConnectez-vous dans la fenetre ouverte, code par e-mail compris.")
        input("Entree une fois connecte pour enregistrer la session... ")
        ctx.close()
    print(f"Session enregistree dans {PROFIL}.")


def cmd_remplir(args):
    if not ENVOI_AUTOMATIQUE_INTERDIT:
        raise SystemExit("Garde-fou desactive : execution refusee.")
    if not MAPPING.exists():
        raise SystemExit(f"Mapping absent : {MAPPING.name}")
    mapping = charge_json(MAPPING)
    valide_mapping(mapping)

    payload_path = Path(args.payload) if args.payload else BASE / f"payload_D1_{args.id}.json"
    if not payload_path.exists():
        raise SystemExit(f"Payload absent : {payload_path}. Generez-le avec :\n"
                         f"  python 2026_09_03_dcex_racc_suivi.py payload {args.id}")
    payload = charge_json(payload_path)

    def val(chemin):
        cur = payload
        for seg in (chemin or "").split("."):
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                return None
        return cur

    PREUVES.mkdir(exist_ok=True)
    stamp = horodatage()
    journal = {"demande": payload["id"], "horodatage": stamp,
               "remplis": [], "ignores": [], "anomalies": []}

    with _playwright()() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFIL), headless=False, viewport={"width": 1500, "height": 950},
            locale="fr-FR", slow_mo=args.lenteur)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(mapping["url_formulaire"], wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        if not page.locator("text=Déconnexion").count():
            print("Session expiree. Connectez-vous dans la fenetre.")
            input("Entree une fois le formulaire affiche... ")

        for etape in mapping["etapes"]:
            numero, titre = etape["numero"], etape["titre"]
            if numero == 5:
                break                      # ecran de validation : on ne touche a rien
            print(f"\n--- Etape {numero} : {titre}")
            for champ in etape["champs"]:
                lib, typ = champ["label"], champ["type"]
                v = val(champ.get("source_payload")) if champ.get("source_payload") else None
                if v in (None, "", []):
                    v = champ.get("defaut")
                if v in (None, "", []) and typ != "select":
                    journal["ignores"].append(f"[{numero}] {lib}")
                    continue
                try:
                    if typ == "text":
                        err = saisir_texte(page, lib, v)
                    elif typ == "textarea":
                        err = saisir_texte(page, lib, str(v)[:champ.get("maxlength", 500)])
                    elif typ == "autocomplete":
                        err = saisir_texte(page, lib, v, lent=True)
                    elif typ == "radio":
                        err = choisir_radio(page, lib, v)
                    elif typ == "checkbox_multiple":
                        err = cocher(page, v if isinstance(v, list) else [v])
                    elif typ == "select":
                        err = choisir_liste(page, lib, v)
                    elif typ == "datepicker":
                        err = choisir_date(page, lib, v)
                    elif typ == "file":
                        idx = 0 if numero == 3 else 1
                        err = joindre(page, idx, v) if v else None
                    else:
                        err = f"type non gere : {typ}"
                except Exception as e:
                    err = str(e)[:180]
                if err:
                    journal["anomalies"].append({"etape": numero, "champ": lib, "erreur": err})
                    print(f"    ! {lib} : {err}")
                else:
                    journal["remplis"].append({"etape": numero, "champ": lib,
                                               "valeur": str(v)[:100]})
                    print(f"    . {lib}")
            err = etape_suivante(page)
            if err:
                journal["anomalies"].append({"etape": numero, "champ": "navigation", "erreur": err})
                print(f"    ! {err}")
                break

        capture = PREUVES / f"{stamp}_{payload['id']}_arret_validation.png"
        page.screenshot(path=str(capture), full_page=True)
        (PREUVES / f"{stamp}_{payload['id']}_formulaire.html").write_text(
            page.content(), encoding="utf-8")
        with open(PREUVES / f"{stamp}_{payload['id']}_journal.json", "w", encoding="utf-8") as f:
            json.dump(journal, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 74)
        print(f"  DEMANDE {payload['id']} : PRE-REMPLI, ARRET AVANT CERTIFICATION")
        print("=" * 74)
        print(f"  {len(journal['remplis'])} champs renseignes, "
              f"{len(journal['ignores'])} laisses vides")
        if journal["anomalies"]:
            print(f"\n  {len(journal['anomalies'])} ANOMALIES A CORRIGER A LA MAIN :")
            for a in journal["anomalies"]:
                print(f"    etape {a['etape']} · {a['champ']} : {a['erreur'][:100]}")
        print(f"\n  Domaine de tension impose (article 105) : "
              f"{payload['controle_article_105']['domaine']}")
        print(f"  Capture : {capture.name}")
        print("\n  LE ROBOT S'ARRETE ICI. Relisez les 4 etapes, puis, sur l'ecran 5,")
        print("  activez vous-meme la certification et cliquez sur le bouton d'envoi.")
        print("=" * 74)
        input("\nEntree pour fermer le navigateur... ")
        ctx.close()

    print(f"\nPensez a enregistrer la date de depot :")
    print(f"  python 2026_09_03_dcex_racc_suivi.py set {payload['id']} "
          f"statut=depose date_depot={datetime.now():%Y-%m-%d}")


def cmd_verifier(args):
    """Controle de coherence mapping / payload, sans ouvrir de navigateur."""
    mapping = charge_json(MAPPING)
    valide_mapping(mapping)
    payload_path = Path(args.payload) if args.payload else BASE / f"payload_D1_{args.id}.json"
    payload = charge_json(payload_path)

    def val(chemin):
        cur = payload
        for seg in (chemin or "").split("."):
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                return None
        return cur

    types_geres = {"text", "textarea", "autocomplete", "radio", "checkbox_multiple",
                   "select", "datepicker", "file"}
    pret, manquants, alertes = [], [], []
    for etape in mapping["etapes"]:
        if etape["numero"] == 5:
            continue
        for champ in etape["champs"]:
            lib, typ = champ["label"], champ["type"]
            if typ not in types_geres:
                alertes.append(f"etape {etape['numero']} · {lib} : type non gere ({typ})")
                continue
            src = champ.get("source_payload")
            v = val(src) if src else None
            if v in (None, "", []):
                v = champ.get("defaut")
            if v in (None, "", []):
                if typ == "select" and not src:
                    pret.append(f"etape {etape['numero']} · {lib} : premiere option")
                elif champ.get("requis"):
                    manquants.append(f"etape {etape['numero']} · {lib}"
                                     + (f"  (cle attendue : {src})" if src else ""))
                continue
            if typ == "datepicker":
                try:
                    j, m, a = [int(x) for x in str(v).split("/")]
                    d_ = datetime(a, m, j).date()
                except (ValueError, IndexError):
                    alertes.append(f"etape {etape['numero']} · {lib} : date mal formee "
                                   f"'{v}', attendu JJ/MM/AAAA")
                    continue
                # RTE impose un attribut min sur ce champ, cale sur le lendemain.
                # Controle approche hors ligne, le controle exact a lieu au runtime.
                if d_ <= datetime.now().date():
                    alertes.append(f"etape {etape['numero']} · {lib} : date passee ou du jour "
                                   f"({v}), RTE n'accepte qu'une date future")
                    continue
            if typ == "file":
                chemin = Path(v) if Path(v).is_absolute() else BASE.parent / v
                if not chemin.exists():
                    alertes.append(f"etape {etape['numero']} · {lib} : fichier introuvable "
                                   f"({chemin})")
                    continue
                if chemin.stat().st_size > 2 * 1024 * 1024:
                    alertes.append(f"etape {etape['numero']} · {lib} : depasse 2 Mo")
                    continue
            if typ in ("radio", "checkbox_multiple", "select") and champ.get("options"):
                voulues = v if isinstance(v, list) else [v]
                for w in voulues:
                    if not any(norm(str(w)) in norm(o) for o in champ["options"]):
                        alertes.append(f"etape {etape['numero']} · {lib} : valeur '{w}' "
                                       f"absente des options {champ['options']}")
            pret.append(f"etape {etape['numero']} · {lib} = {str(v)[:60]}")

    print(f"\nVERIFICATION DE LA DEMANDE {payload['id']}")
    print("=" * 70)
    print(f"{len(pret)} champs prets a etre remplis")
    for x in pret:
        print(f"  . {x}")
    if manquants:
        print(f"\n{len(manquants)} CHAMPS OBLIGATOIRES SANS VALEUR :")
        for x in manquants:
            print(f"  ! {x}")
    if alertes:
        print(f"\n{len(alertes)} ANOMALIES :")
        for x in alertes:
            print(f"  ! {x}")
    if not manquants and not alertes:
        print("\nAucune anomalie. Le parcours peut etre lance.")
    else:
        print("\nCorrigez le registre avant de lancer le parcours.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Robot de pre-remplissage du formulaire D1 RTE")
    sub = p.add_subparsers(dest="cmd", required=True)
    lo = sub.add_parser("login", help="ouvre le portail et memorise la session")
    lo.add_argument("--url", default=URL_PORTAIL)
    lo.set_defaults(func=cmd_login)
    re = sub.add_parser("remplir", help="pre-remplit les 4 premieres etapes, sans jamais envoyer")
    re.add_argument("--id", required=True)
    re.add_argument("--payload")
    re.add_argument("--lenteur", type=int, default=60, help="ms entre actions")
    re.set_defaults(func=cmd_remplir)
    ve = sub.add_parser("verifier", help="controle mapping / payload sans navigateur")
    ve.add_argument("--id", required=True)
    ve.add_argument("--payload")
    ve.set_defaults(func=cmd_verifier)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
