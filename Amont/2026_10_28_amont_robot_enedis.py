# -*- coding: utf-8 -*-
"""
Robot Enedis d'Amont : pre-remplit une demande de raccordement HTA sur le Portail Raccordement Enedis
(raccordement-entreprise-enedis.fr, « Un site industriel en HTA ») a partir d'une demande Amont, puis S'ARRETE.

REGLE ABSOLUE : le dernier clic est humain.
  - aucune fonction d'envoi n'existe dans ce fichier ;
  - tout clic passe par cliquer(), qui refuse un controle dont le texte evoque un envoi ou une validation ;
  - le robot remplit les etapes Coordonnees, Construction, Documents et Echeance, et s'arrete sur Echeance SANS
    cliquer le dernier « Suivant » : le recapitulatif et l'envoi sont faits par vous.
  Le robot peut passer la demande a « pret pour validation » dans Amont, jamais a « depose ».

Le mapping fiche -> formulaire est calcule par Amont (GET /api/demandes/{id}/enedis), formulaire releve en direct
le 28/10/2026 (note 2026_10_28_amont_releve_enedis.md).

Attention, difference avec le portail RTE : le portail Enedis cree un brouillon de demande des l'ecran d'accueil
(« Continuer » apres le choix du type). Un essai laisse donc un brouillon dans « Mon suivi de dossier », sans
aucun envoi a Enedis ; il se supprime depuis le portail.

Installation, une fois, sur le poste Windows :
    pip install selenium

Usage :
    python 2026_10_28_amont_robot_enedis.py --demande SOC-ENE --simulation   # plan de saisie, sans navigateur
    python 2026_10_28_amont_robot_enedis.py --demande SOC-ENE --jusqua 1     # remplit Coordonnees seulement
    python 2026_10_28_amont_robot_enedis.py --demande SOC-ENE --pause        # pause entre chaque etape
    python 2026_10_28_amont_robot_enedis.py --demande SOC-ENE                # remplit les 4 etapes, s'arrete

Options : --amont URL (defaut : variable AMONT_URL, sinon https://amont.arinaudo.fr), --profil DOSSIER (profil
Chrome dedie, garde la session Enedis), --sans-statut, --non-interactif (lance par l'agent du poste).

Alexis Rinaudo / Castignac, 28/10/2026
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

AMONT_DEFAUT = os.environ.get("AMONT_URL", "https://amont.arinaudo.fr").rstrip("/")
PROFIL_DEFAUT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AmontRobot" / "profil-chrome-enedis"
CAPTURES = Path(__file__).resolve().parent / "robot_captures"
AUTEUR = "robot Enedis"
TAILLE_ALERTE = 10 * 1024 * 1024

ENVOI_AUTOMATIQUE_INTERDIT = True  # ne jamais passer a False
CONTROLES_INTERDITS = ["envoyer", "soumettre", "submit", "transmettre", "valider", "déposer", "deposer", "confirmer",
                       "signer", "payer", "terminer"]


class ArretRobot(Exception):
    pass


# ---------------------------------------------------------------------------
# Amont
# ---------------------------------------------------------------------------

def amont(url_base: str, chemin: str, methode: str = "GET", corps: dict | None = None, brut: bool = False):
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    req = urllib.request.Request(url_base + "/api" + chemin, data=donnees, method=methode)
    req.add_header("X-Amont-Auteur", urllib.parse.quote(AUTEUR))
    req.add_header("X-Amont-Origine", "robot")
    if donnees is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
            contenu = r.read()
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(msg).get("erreur", msg)
        except ValueError:
            pass
        raise ArretRobot(f"Amont a répondu {e.code} sur {chemin} : {msg}") from None
    except urllib.error.URLError as e:
        raise ArretRobot(f"Amont injoignable ({url_base}) : {e.reason}. Tailscale est-il connecté ?") from None
    return contenu if brut else json.loads(contenu or b"null")


def telecharger_piece(url_base: str, piece: dict, dossier: Path) -> Path:
    contenu = amont(url_base, f"/pieces/{piece['id']}/fichier", brut=True)
    if len(contenu) > TAILLE_ALERTE:
        print(f"   attention : {piece['nom']} fait {len(contenu) // (1024 * 1024)} Mo, le portail peut le refuser")
    chemin = dossier / piece["nom"]
    chemin.write_bytes(contenu)
    return chemin


def afficher_plan(plan: dict) -> None:
    print(f"\nDemande {plan['demande']} · {plan['url']}")
    acc = plan.get("accueil") or {}
    print(f"Accueil : commune {acc.get('commune') or 'MANQUANTE'} ({acc.get('code_postal') or '?'}), type « {acc.get('type')} »\n")
    for e in plan["etapes"]:
        print(f"ÉTAPE {e['numero']} · {e['titre'].upper()}")
        for a in e["actions"]:
            v = a["valeur"]
            v = ("MANQUANT" if a["requis"] else "(vide, ignoré)") if v in (None, "") else str(a.get("libelle") or v)
            if len(v) > 60:
                v = v[:57] + "..."
            print(f"   {a['type']:<8} {a['question'][:50]:<50} {v}")
            if a.get("note"):
                print(f"   {'':<8} {'':<50} ↳ {a['note']}")
        if e.get("arret"):
            print(f"   {e['arret']}")
        print()
    for titre, liste in (("MANQUANT, à compléter dans la fiche du site ou les pièces :", plan["manquants"]),
                         ("À SURVEILLER :", plan["alertes"])):
        if liste:
            print(titre)
            for m in liste:
                print(f"   - {m}")
    print("\nPrêt pour le robot." if plan["pret"] else "\nPas encore prêt.")


# ---------------------------------------------------------------------------
# Navigateur (Selenium)
# ---------------------------------------------------------------------------

JS_VISIBLE = "const e=arguments[0]; return !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));"

JS_OPTION = r"""
const debut = arguments[0], cp = arguments[1] || '';
const norm = s => (s||'').normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[-'’]/g,' ').replace(/\s+/g,' ').trim().toUpperCase();
for (const li of document.querySelectorAll('li.vs__dropdown-option, li[role=option]')) {
  if (!(li.offsetWidth || li.offsetHeight)) continue;
  const t = norm(li.textContent);
  if (t.startsWith(norm(debut)) && (!cp || t.includes(cp))) return li;
}
return null;
"""

JS_OPTION_EXACTE = r"""
const v = (arguments[0]||'').trim();
for (const li of document.querySelectorAll('li.vs__dropdown-option, li[role=option]')) {
  if ((li.offsetWidth || li.offsetHeight) && li.textContent.trim() === v) return li;
}
return null;
"""


class Portail:
    def __init__(self, profil: Path, captures: Path, chrome: str | None = None):
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError:
            raise ArretRobot("Selenium absent. Installer avec :  pip install selenium") from None
        self.By, self.Keys, self.EC, self.Wait = By, Keys, EC, WebDriverWait
        profil.mkdir(parents=True, exist_ok=True)
        opts = webdriver.ChromeOptions()
        opts.add_argument(f"--user-data-dir={profil}")
        opts.add_argument("--lang=fr-FR")
        opts.add_experimental_option("detach", True)
        if chrome:
            opts.binary_location = chrome
        if os.environ.get("AMONT_ROBOT_HEADLESS"):
            opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
        pilote = os.environ.get("AMONT_CHROMEDRIVER")
        try:
            if pilote:
                from selenium.webdriver.chrome.service import Service
                self.d = webdriver.Chrome(options=opts, service=Service(pilote, service_args=["--disable-build-check"]))
            else:
                self.d = webdriver.Chrome(options=opts)
        except Exception as e:  # noqa: BLE001
            raise ArretRobot("Chrome n'a pas démarré. Si une fenêtre Chrome d'un passage précédent du robot est encore ouverte, "
                             f"la fermer, puis relancer. Détail : {str(e).splitlines()[0][:160]}") from None
        self.d.set_window_size(1400, 1000)
        self.captures = captures
        captures.mkdir(parents=True, exist_ok=True)

    # -- garde-fous
    def cliquer(self, el) -> None:
        texte = " ".join(filter(None, [el.text, el.get_attribute("aria-label") or "", el.get_attribute("value") or "",
                                       el.get_attribute("title") or ""])).lower()
        if (el.tag_name or "").lower() in ("button", "a") or (el.get_attribute("type") or "") in ("submit", "button"):
            if ENVOI_AUTOMATIQUE_INTERDIT and any(m in texte for m in CONTROLES_INTERDITS):
                raise ArretRobot(f"clic refusé, contrôle d'envoi ou de validation : « {texte.strip()[:60]} »")
        self.d.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
        try:
            el.click()
        except Exception:
            self.d.execute_script("arguments[0].click()", el)

    def capture(self, nom: str) -> Path:
        p = self.captures / f"{datetime.now():%H%M%S}_{nom}.png"
        self.d.save_screenshot(str(p))
        return p

    def visible(self, el) -> bool:
        return bool(self.d.execute_script(JS_VISIBLE, el))

    def attendre(self, fonction, delai: float = 15, message: str = ""):
        fin = time.time() + delai
        while time.time() < fin:
            try:
                r = fonction()
            except Exception:  # noqa: BLE001 : element en cours de rendu
                r = None
            if r:
                return r
            time.sleep(0.4)
        raise ArretRobot(message or "délai dépassé")

    def bouton(self, texte: str):
        xp = f"//button[normalize-space()='{texte}'] | //a[normalize-space()='{texte}']"
        return self.attendre(lambda: next((b for b in self.d.find_elements(self.By.XPATH, xp) if self.visible(b)), None),
                             message=f"bouton « {texte} » introuvable")

    def fermer_fenetres(self) -> None:
        for b in self.d.find_elements(self.By.XPATH, "//button[normalize-space()='Fermer']"):
            if self.visible(b):
                self.cliquer(b)
                time.sleep(0.5)

    # -- session et ecran d'accueil
    def _connexion(self) -> bool:
        u = self.d.current_url.lower()
        return "mon-compte.enedis.fr" in u or "/login" in u or "/account/login" in u

    def ouvrir(self, url: str, interactif: bool) -> None:
        self.d.get(url)
        time.sleep(2.5)
        if self._connexion():
            if interactif:
                input("\n>>> Connectez-vous à votre compte Enedis dans la fenêtre Chrome du robot, puis Entrée ici... ")
            else:
                print(">>> CONNEXION REQUISE : connectez-vous à votre compte Enedis dans la fenêtre Chrome du robot. "
                      "Le robot reprend seul une fois connecté (10 minutes au plus).", flush=True)
                debut = time.time()
                while self._connexion() and time.time() - debut < 600:
                    time.sleep(3)
                if self._connexion():
                    raise ArretRobot("connexion au portail Enedis non faite dans les 10 minutes")
                print("Connexion faite, reprise.", flush=True)
            self.d.get(url)
            time.sleep(2.5)

    def accueil(self, commune: str, code_postal: str | None, type_raccordement: str) -> None:
        champ = self.attendre(lambda: next((e for e in self.d.find_elements(self.By.CSS_SELECTOR, "main input[type=search]")
                                            if self.visible(e)), None), message="champ commune de l'accueil introuvable")
        self.cliquer(champ)
        champ.send_keys(commune)
        li = self.attendre(lambda: self.d.execute_script(JS_OPTION, commune, code_postal or ""), 15,
                           f"commune « {commune} » absente de la liste du portail")
        self.cliquer(li)
        time.sleep(0.8)
        self.cliquer(self.bouton("Commencer"))
        time.sleep(3)
        self.fermer_fenetres()
        tuile = self.attendre(lambda: next((e for e in self.d.find_elements(self.By.XPATH, f"//*[normalize-space()='{type_raccordement}']")
                                            if self.visible(e)), None), message=f"type « {type_raccordement} » introuvable")
        self.cliquer(tuile)
        time.sleep(1.5)
        self.cliquer(self.bouton("Continuer"))
        self.attendre(lambda: self.d.find_elements(self.By.CSS_SELECTOR, "input[name=raccDefinition]"), 30,
                      "le formulaire de demande ne s'est pas ouvert")
        time.sleep(1.5)
        print(f"   ok accueil : {commune}, {type_raccordement}  (brouillon créé : {self.d.current_url.rsplit('/', 1)[-1]})")

    # -- actions
    def _par_nom(self, nom: str, selecteur: str = "input,textarea"):
        css = ",".join(f"{s}[name={json.dumps(nom)}]" for s in selecteur.split(","))
        return self.attendre(lambda: next((e for e in self.d.find_elements(self.By.CSS_SELECTOR, css) if self.visible(e)), None),
                             message=f"champ « {nom} » introuvable ou masqué")

    def radio(self, nom: str, valeur: str) -> None:
        css = f"input[type=radio][name={json.dumps(nom)}][value={json.dumps(valeur)}]"
        el = self.attendre(lambda: self.d.find_elements(self.By.CSS_SELECTOR, css), message=f"choix « {nom} = {valeur} » introuvable")[0]
        if el.is_selected():
            return
        lab = self.d.find_elements(self.By.CSS_SELECTOR, f"label[for={json.dumps(el.get_attribute('id') or '')}]")
        if lab and self.visible(lab[0]):
            self.cliquer(lab[0])
        else:
            self.d.execute_script("arguments[0].click()", el)
        time.sleep(0.5)
        if not el.is_selected():
            self.d.execute_script("arguments[0].click()", el)
            time.sleep(0.3)

    def case(self, nom: str) -> None:
        el = self.attendre(lambda: self.d.find_elements(self.By.CSS_SELECTOR, f"input[type=checkbox][name={json.dumps(nom)}]"),
                           message=f"case « {nom} » introuvable")[0]
        if not el.is_selected():
            lab = self.d.find_elements(self.By.CSS_SELECTOR, f"label[for={json.dumps(el.get_attribute('id') or '')}]")
            self.cliquer(lab[0]) if lab and self.visible(lab[0]) else self.d.execute_script("arguments[0].click()", el)
            time.sleep(0.4)

    def texte(self, nom: str, valeur: str) -> None:
        el = self._par_nom(nom)
        self.cliquer(el)
        el.send_keys(self.Keys.CONTROL, "a")
        el.send_keys(self.Keys.DELETE)
        el.send_keys(str(valeur))
        el.send_keys(self.Keys.TAB)
        time.sleep(0.3)

    def commune(self, nom: str, valeur: str, code_postal: str | None) -> None:
        el = self._par_nom(nom, "input")
        self.cliquer(el)
        el.send_keys(valeur)
        li = self.attendre(lambda: self.d.execute_script(JS_OPTION, valeur, code_postal or ""), 15,
                           f"commune « {valeur} {code_postal or ''} » absente de la liste du portail")
        self.cliquer(li)
        time.sleep(1.2)

    def liste(self, nom: str, option: str) -> None:
        el = self._par_nom(nom, "input")
        self.cliquer(el)
        li = self.attendre(lambda: self.d.execute_script(JS_OPTION_EXACTE, option), 10, f"valeur « {option} » absente de la liste « {nom} »")
        self.cliquer(li)
        time.sleep(0.6)

    def date(self, nom: str, valeur: str) -> None:
        el = self._par_nom(nom, "input")
        self.cliquer(el)
        el.send_keys(self.Keys.CONTROL, "a")
        el.send_keys(valeur)
        el.send_keys(self.Keys.ENTER)
        el.send_keys(self.Keys.TAB)
        time.sleep(0.5)
        if (el.get_attribute("value") or "").strip() != valeur:
            raise ArretRobot(f"date refusée par le portail : {valeur} (affiché : {el.get_attribute('value')!r})")

    def fichier(self, nom: str, chemin: Path) -> None:
        css = f"input[type=file][name={json.dumps(nom)}]"
        el = self.attendre(lambda: self.d.find_elements(self.By.CSS_SELECTOR, css), message=f"emplacement « {nom} » introuvable")[0]
        self.d.execute_script("arguments[0].style.display='block'; arguments[0].style.visibility='visible';", el)
        el.send_keys(str(chemin))
        time.sleep(2.5)

    def suivant(self) -> None:
        b = self.bouton("Suivant")
        self.cliquer(b)
        time.sleep(2.5)
        erreurs = [e.text.strip() for e in self.d.find_elements(self.By.CSS_SELECTOR, ".invalid-feedback, .error, .text-danger, [role=alert]")
                   if self.visible(e) and e.text.strip()]
        if erreurs:
            raise ArretRobot("le portail signale des erreurs : " + " ; ".join(dict.fromkeys(erreurs))[:400])


def executer(portail: Portail, plan: dict, pieces: dict, jusqua: int, pause: bool) -> int:
    acc = plan["accueil"]
    portail.accueil(acc["commune"], acc.get("code_postal"), acc["type"])
    faite = 0
    for e in plan["etapes"]:
        n = e["numero"]
        if n > jusqua:
            break
        print(f"\nÉTAPE {n} · {e['titre']}")
        for a in e["actions"]:
            v = a["valeur"]
            if v in (None, ""):
                if a["requis"]:
                    raise ArretRobot(f"valeur manquante : {a['question']}")
                print(f"   -  {a['question']} (vide, ignoré)")
                continue
            t, c = a["type"], a["cible"]
            if t == "radio":
                portail.radio(c, v)
            elif t == "case":
                portail.case(c)
            elif t == "texte":
                portail.texte(c, v)
            elif t == "commune":
                portail.commune(c, v, a.get("code_postal"))
            elif t == "liste":
                portail.liste(c, v)
            elif t == "date":
                portail.date(c, v)
            elif t == "fichier":
                chemin = pieces.get(a["piece"]["id"]) if a.get("piece") else None
                if not chemin:
                    print(f"   -  {a['question']} : pièce non disponible, ignorée")
                    continue
                portail.fichier(c, chemin)
            print(f"   ok {a['question'][:48]} = {str(a.get('libelle') or v)[:48]}")
        portail.capture(f"etape{n}")
        faite = n
        if pause and n < min(4, jusqua):
            input(f">>> Étape {n} remplie. Vérifiez la fenêtre puis Entrée pour passer à l'étape {n + 1}... ")
        if n < 4 and n < jusqua:
            portail.suivant()
    return faite


def main() -> int:
    ap = argparse.ArgumentParser(description="Robot Enedis Amont : pré-remplit une demande HTA, sans jamais envoyer.")
    ap.add_argument("--demande", help="code de la demande Enedis dans Amont, ex. SOC-ENE")
    ap.add_argument("--amont", default=AMONT_DEFAUT)
    ap.add_argument("--profil", default=str(PROFIL_DEFAUT))
    ap.add_argument("--simulation", action="store_true", help="affiche le plan de saisie sans ouvrir de navigateur")
    ap.add_argument("--pause", action="store_true", help="attend Entrée entre chaque étape")
    ap.add_argument("--jusqua", type=int, default=4, help="s'arrête après l'étape N (1 à 4)")
    ap.add_argument("--sans-statut", action="store_true", help="ne modifie pas la demande dans Amont")
    ap.add_argument("--chrome", default=os.environ.get("AMONT_CHROME"))
    ap.add_argument("--non-interactif", action="store_true", help="lancé par l'agent du poste")
    args = ap.parse_args()
    url = args.amont.rstrip("/")
    if not args.demande:
        ap.error("--demande est obligatoire")
    try:
        plan = amont(url, f"/demandes/{urllib.parse.quote(args.demande)}/enedis")
        afficher_plan(plan)
        val = (amont(url, f"/demandes/{urllib.parse.quote(args.demande)}") or {}).get("validation") or {}
        libelle_val = {"aucune": "pas encore demandée", "demandee": "demandée, en attente du responsable",
                       "validee": f"donnée par {val.get('traite_par')} le {(val.get('traite_le') or '')[:10]}",
                       "perimee": "périmée : le dossier a changé depuis", "refusee": "refusée"}.get(val.get("etat"), "inconnue")
        print(f"\nValidation du responsable : {libelle_val}")
        if args.simulation:
            return 0 if plan["pret"] else 1
        if val.get("requise") and val.get("etat") != "validee" and args.jusqua >= 3:
            raise ArretRobot("validation du responsable " + libelle_val + ". La demander depuis la demande dans Amont, "
                             "ou tester les premières étapes avec --jusqua 2")
        if not plan["pret"] and args.jusqua >= 4:
            raise ArretRobot("plan incomplet : compléter la fiche du site et les pièces (voir MANQUANT), ou tester avec --jusqua 1 à 3")
        tmp = Path(tempfile.mkdtemp(prefix="amont_enedis_"))
        pieces = {}
        for e in plan["etapes"]:
            if e["numero"] > args.jusqua:
                continue
            for a in e["actions"]:
                if a["type"] == "fichier" and a.get("piece"):
                    pieces[a["piece"]["id"]] = telecharger_piece(url, a["piece"], tmp)
                    print(f"Pièce téléchargée : {a['piece']['nom']}")
        dossier = CAPTURES / f"{args.demande}_{datetime.now():%Y_%m_%d_%H%M}"
        portail = Portail(Path(args.profil), dossier, args.chrome)
        print("\nOuverture du portail Enedis...")
        portail.ouvrir(plan["url"], not args.non_interactif)
        faite = executer(portail, plan, pieces, args.jusqua, args.pause and not args.non_interactif)
        print(f"\nCaptures : {dossier}")
        if faite >= 4:
            print("\n" + "=" * 78)
            print("FORMULAIRE PRÉ-REMPLI. Le robot s'est arrêté sur l'étape Échéance, rien n'a été envoyé.")
            print("À vous : relire les 4 étapes, cliquer « Suivant » vers le récapitulatif, envoyer,")
            print(f"puis passer {args.demande} à « Déposé » dans Amont avec la date du jour.")
            print("=" * 78)
            if not args.sans_statut:
                amont(url, f"/demandes/{urllib.parse.quote(args.demande)}", "PATCH", {"statut": "pret_validation"})
                amont(url, "/echanges", "POST", {"demande_id": args.demande, "sens": "note", "canal": "portail",
                                                 "objet": "Demande Enedis pré-remplie par le robot",
                                                 "resume": "Arrêt sur l'étape Échéance. Relecture et envoi à faire à la main.",
                                                 "attend_reponse": False})
                print(f"Amont : {args.demande} passée à « prêt pour validation ».")
        else:
            print(f"\nTest arrêté après l'étape {faite} comme demandé (--jusqua {args.jusqua}). Amont n'est pas modifié.")
            print("Le portail garde le brouillon : à supprimer depuis « Mon suivi de dossier » s'il ne sert pas.")
        print("La fenêtre Chrome reste ouverte.")
        return 0
    except ArretRobot as e:
        print(f"\nARRÊT DU ROBOT : {e}")
        print("Rien n'a été envoyé à Enedis. La fenêtre Chrome, si elle est ouverte, reste en l'état.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
