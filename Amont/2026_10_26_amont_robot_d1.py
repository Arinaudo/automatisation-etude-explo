# -*- coding: utf-8 -*-
"""
Robot D1 d'Amont : pre-remplit le formulaire d'etude exploratoire du Portail Services RTE
a partir d'une demande du registre Amont, puis S'ARRETE avant l'envoi.

REGLE ABSOLUE : le dernier clic est humain.
  - aucune fonction d'envoi n'existe dans ce fichier ;
  - tout clic passe par cliquer(), qui refuse un controle dont le texte evoque un envoi ;
  - l'interrupteur de certification (etape 5) n'est jamais touche : sans lui, le bouton
    Envoyer reste desactive cote RTE.
  Le robot peut passer la demande a « pret pour validation » dans Amont, jamais a « depose ».

Le mapping fiche -> formulaire n'est pas ici : il est calcule par Amont (GET /api/demandes/{id}/d1),
une seule source de verite pour le site et le robot. Recettes Selenium : notes du 05/10/2026
(Suivi/2026_10_05_dcex_racc_notes_selenium_sochaux.md).

Installation, une fois, sur le poste Windows :
    pip install selenium
(Selenium 4.10+ telecharge lui-meme le pilote de Chrome.)

Usage :
    python 2026_10_26_amont_robot_d1.py --verifier                      # Amont joignable ? Selenium ? Chrome ?
    python 2026_10_26_amont_robot_d1.py --demande SOC-EE --simulation   # plan de saisie, sans navigateur
    python 2026_10_26_amont_robot_d1.py --demande SOC-EE --banc         # repetition sur le banc d'essai local
    python 2026_10_26_amont_robot_d1.py --demande SOC-EE --pause        # remplit, pause entre chaque etape
    python 2026_10_26_amont_robot_d1.py --demande SOC-EE --jusqua 2     # s'arrete apres l'etape 2
    python 2026_10_26_amont_robot_d1.py --demande SOC-EE                # remplit les 4 etapes, s'arrete a la 5

Options : --amont URL (defaut : variable AMONT_URL, sinon https://amont.arinaudo.fr),
--profil DOSSIER (profil Chrome dedie, garde la session RTE), --sans-statut (ne pas toucher a Amont).

Rien n'est envoye a RTE tant que l'humain n'a pas certifie et clique : un test complet sur le vrai
portail est sans risque. Le portail ne garde pas de brouillon : recharger la page efface tout.

Alexis Rinaudo / Castignac, 26/10/2026
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
PROFIL_DEFAUT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AmontRobot" / "profil-chrome"
CAPTURES = Path(__file__).resolve().parent / "robot_captures"
BANC = Path(__file__).resolve().parent / "robot_banc" / "2026_10_26_banc_d1.html"
AUTEUR = "robot D1"

ENVOI_AUTOMATIQUE_INTERDIT = True  # ne jamais passer a False
CONTROLES_INTERDITS = ["envoyer", "soumettre", "submit", "transmettre", "valider la demande", "deposer",
                       "déposer", "confirmer l'envoi", "certifi"]


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
    if len(contenu) > 2 * 1024 * 1024:
        raise ArretRobot(f"{piece['nom']} fait {len(contenu) // 1024} ko : le portail refuse au-delà de 2 Mo")
    chemin = dossier / piece["nom"]
    chemin.write_bytes(contenu)
    return chemin


# ---------------------------------------------------------------------------
# Simulation : affichage du plan
# ---------------------------------------------------------------------------

def afficher_plan(plan: dict) -> None:
    print(f"\nDemande {plan['demande']} · {plan['url']}\n")
    for e in plan["etapes"]:
        print(f"ÉTAPE {e['numero']} · {e['titre'].upper()}")
        if not e["actions"]:
            print(f"   {e.get('arret', '')}")
        for a in e["actions"]:
            v = a["valeur"]
            v = ("MANQUANT" if a["requis"] else "(vide, ignoré)") if v in (None, "") else str(v)
            if len(v) > 70:
                v = v[:67] + "..."
            print(f"   {a['type']:<8} {a['question'][:52]:<52} {v}")
            if a.get("note"):
                print(f"   {'':<8} {'':<52} ↳ {a['note']}")
        print()
    if plan["manquants"]:
        print("MANQUANT, à compléter dans la fiche du site avant de lancer le robot :")
        for m in plan["manquants"]:
            print(f"   - {m}")
    if plan["alertes"]:
        print("À SURVEILLER :")
        for m in plan["alertes"]:
            print(f"   - {m}")
    print("\nPrêt pour le robot." if plan["pret"] else "\nPas encore prêt.")


# ---------------------------------------------------------------------------
# Navigateur (Selenium)
# ---------------------------------------------------------------------------

JS_NORM = r"""
const norm = s => (s||'').normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[’`]/g,"'")
                  .replace(/\s+/g,' ').trim().toLowerCase();
const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
"""

JS_CHAMP = JS_NORM + r"""
// Remonte depuis chaque champ jusqu'au bloc dont le texte commence par la question ;
// s'arrete des que le bloc contient un autre champ (on serait sorti de la question).
// Repli : methode du 05/10 (premier ancetre de plus de 15 caracteres).
const q = norm(arguments[0]);
const champs = [...document.querySelectorAll('input:not([type=radio]):not([type=checkbox]):not([type=file]):not([type=hidden]),textarea,mat-select')].filter(visible);
const nChamps = p => [...p.querySelectorAll('input:not([type=radio]):not([type=checkbox]):not([type=file]):not([type=hidden]),textarea,mat-select')].filter(visible).length;
for (const e of champs) {
  let p = e;
  for (let k = 0; k < 10 && p.parentElement; k++) {
    p = p.parentElement;
    if (nChamps(p) > 1 || p.querySelector('mat-radio-group')) break;
    if (norm(p.innerText).startsWith(q)) return e;
  }
}
for (const e of champs) {
  let p = e;
  for (let k = 0; k < 8 && p.parentElement; k++) { p = p.parentElement; if (p.innerText.trim().length > 15) break; }
  if (norm(p.innerText).startsWith(q)) return e;
}
return null;
"""

JS_RADIO = JS_NORM + r"""
const q = norm(arguments[0]), opt = norm(arguments[1]);
const choisir = g => {
  for (const b of g.querySelectorAll('mat-radio-button')) {
    if (norm(b.innerText) === opt || norm(b.innerText).startsWith(opt)) {
      const inp = b.querySelector('input');
      if (inp && inp.checked) return 'deja';
      return b.querySelector('label') || b;
    }
  }
  return null;
};
const groupes = [...document.querySelectorAll('mat-radio-group')].filter(visible);
for (const g of groupes) {
  let p = g;
  for (let k = 0; k < 10 && p.parentElement; k++) {
    p = p.parentElement;
    if (p.querySelectorAll('mat-radio-group').length > 1) break;
    if (norm(p.innerText).startsWith(q)) { const c = choisir(g); if (c) return c; break; }
  }
}
for (const g of groupes) {
  const lg = g.innerText.trim().length;
  let p = g;
  for (let k = 0; k < 8 && p.parentElement; k++) { p = p.parentElement; if (p.innerText.trim().length > lg + 10) break; }
  if (norm(p.innerText).startsWith(q)) { const c = choisir(g); if (c) return c; }
}
return null;
"""

JS_RADIO_VALEUR = JS_NORM + r"""
const v = arguments[0];
for (const i of document.querySelectorAll('input[type=radio]')) {
  if (i.value === v && visible(i.closest('mat-radio-button') || i)) {
    if (i.checked) return 'deja';
    return document.querySelector('label[for="' + i.id + '"]') || i.closest('mat-radio-button');
  }
}
return null;
"""

JS_CASE = JS_NORM + r"""
const l = norm(arguments[0]);
for (const c of document.querySelectorAll('cortex-checkbox')) {
  if (!visible(c) || norm(c.innerText) !== l) continue;
  const inp = c.querySelector('input[type=checkbox]');
  if (inp && inp.checked) return 'deja';
  return c.querySelector('label.mat-checkbox-layout') || c.querySelector('label') || c;
}
return null;
"""

JS_TEXTE = r"""
const e = arguments[0];
e.focus();
e.value = arguments[1];
e.dispatchEvent(new Event('input', {bubbles: true}));
e.dispatchEvent(new Event('change', {bubbles: true}));
e.dispatchEvent(new Event('blur', {bubbles: true}));
"""


def _xpath_litteral(s: str) -> str:
    if "'" not in s:
        return f"'{s}'"
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in s.split("'")) + ")"


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
        opts.add_experimental_option("detach", True)  # la fenetre reste ouverte pour la relecture et l'envoi
        if chrome:
            opts.binary_location = chrome
        if os.environ.get("AMONT_ROBOT_HEADLESS"):  # tests automatiques uniquement
            opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
        pilote = os.environ.get("AMONT_CHROMEDRIVER")  # tests automatiques : pilote impose
        try:
            if pilote:
                from selenium.webdriver.chrome.service import Service
                self.d = webdriver.Chrome(options=opts, service=Service(pilote, service_args=["--disable-build-check"]))
            else:
                self.d = webdriver.Chrome(options=opts)
        except Exception as e:  # noqa: BLE001
            raise ArretRobot("Chrome n'a pas démarré. Cause la plus fréquente : la fenêtre Chrome d'un passage précédent du robot "
                             "est encore ouverte et verrouille son profil. La fermer, puis relancer. "
                             f"Détail : {str(e).splitlines()[0][:160]}") from None
        self.d.set_window_size(1600, 950)  # stepper horizontal : seule l'etape courante est visible (note 18)
        self.captures = captures
        captures.mkdir(parents=True, exist_ok=True)

    # -- garde-fous
    def cliquer(self, el) -> None:
        texte = " ".join(filter(None, [el.text, el.get_attribute("aria-label") or "", el.get_attribute("value") or ""])).lower()
        if ENVOI_AUTOMATIQUE_INTERDIT and any(m in texte for m in CONTROLES_INTERDITS):
            raise ArretRobot(f"clic refusé, contrôle d'envoi : « {texte.strip()[:60]} »")
        tag = (el.tag_name or "").lower()
        if "slide-toggle" in tag or (el.get_attribute("class") or "").find("slide-toggle") >= 0:
            raise ArretRobot("clic refusé sur l'interrupteur de certification")
        self.d.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
        try:
            el.click()
        except Exception:
            self.d.execute_script("arguments[0].click()", el)

    def capture(self, nom: str) -> Path:
        p = self.captures / f"{datetime.now():%H%M%S}_{nom}.png"
        self.d.save_screenshot(str(p))
        return p

    # -- session
    def ouvrir(self, url: str, interactif: bool = True) -> None:
        self.d.get(url)
        time.sleep(2)
        if self._page_connexion():
            if interactif:
                input("\n>>> Connectez-vous au Portail Services RTE dans la fenêtre Chrome du robot, puis appuyez sur Entrée ici... ")
            else:  # lance par l'agent du poste : pas de terminal, on attend que la connexion soit faite dans Chrome
                print(">>> CONNEXION REQUISE : connectez-vous au Portail Services RTE dans la fenêtre Chrome du robot. "
                      "Le robot reprend seul une fois connecté (10 minutes au plus).", flush=True)
                debut = time.time()
                while self._page_connexion() and time.time() - debut < 600:
                    time.sleep(3)
                if self._page_connexion():
                    raise ArretRobot("connexion au portail RTE non faite dans les 10 minutes")
                print("Connexion faite, reprise.", flush=True)
            self.d.get(url)
        self.Wait(self.d, 40).until(self.EC.presence_of_element_located((self.By.CSS_SELECTOR, "mat-radio-button")))
        time.sleep(1)

    def _page_connexion(self) -> bool:
        u = self.d.current_url.lower()
        return "login=true" in u or ("login" in u and "realiser" not in u)

    # -- actions
    def champ(self, question: str):
        for _ in range(20):
            e = self.d.execute_script(JS_CHAMP, question)
            if e is not None:
                return e
            time.sleep(0.5)
        raise ArretRobot(f"champ introuvable : « {question} »")

    def radio(self, question: str, option: str, par_valeur: bool = False) -> None:
        for _ in range(20):
            cible = self.d.execute_script(JS_RADIO, question, option)
            if cible is None and par_valeur:
                cible = self.d.execute_script(JS_RADIO_VALEUR, option)
            if cible == "deja":
                return
            if cible is not None:
                self.cliquer(cible)
                time.sleep(0.6)
                return
            time.sleep(0.5)
        raise ArretRobot(f"bouton radio introuvable : « {question} » → « {option} »")

    def texte(self, question: str, valeur: str) -> None:
        self.d.execute_script(JS_TEXTE, self.champ(question), str(valeur))
        time.sleep(0.2)

    def frappe(self, question: str, valeur: str, tab: bool = True) -> None:
        e = self.champ(question)
        self.cliquer(e)
        e.send_keys(self.Keys.CONTROL, "a")
        e.send_keys(self.Keys.DELETE)
        e.send_keys(str(valeur))
        if tab:
            e.send_keys(self.Keys.TAB)
        time.sleep(1.5)

    def case(self, libelle: str) -> None:
        for _ in range(20):
            c = self.d.execute_script(JS_CASE, libelle)
            if c == "deja":
                return
            if c is not None:
                self.cliquer(c)
                time.sleep(0.4)
                return
            time.sleep(0.5)
        raise ArretRobot(f"case introuvable : « {libelle} »")

    def liste(self, question: str, option: str) -> None:
        self.cliquer(self.champ(question))
        xp = f"//mat-option[normalize-space()={_xpath_litteral(option)}]"
        self.cliquer(self.Wait(self.d, 10).until(self.EC.element_to_be_clickable((self.By.XPATH, xp))))
        time.sleep(0.6)

    def commune(self, question: str, nom: str) -> None:
        self.frappe(question, nom, tab=False)
        # « Aucun resultat » s'affiche 3 a 5 s avant la liste (note 20) : attente explicite
        xp = f"//mat-option[starts-with(normalize-space(), {_xpath_litteral(nom)})]"
        self.cliquer(self.Wait(self.d, 15).until(self.EC.element_to_be_clickable((self.By.XPATH, xp))))
        time.sleep(2)  # le code INSEE se peuple, le GPS est remis a zero (note 9)

    def date(self, cal: dict) -> None:
        self.d.execute_script("const i=[...document.querySelectorAll('cortex-datepicker-icon')].find(x=>x.offsetParent);"
                              "(i||document.querySelector('cortex-datepicker-icon')).dispatchEvent(new MouseEvent('click',{bubbles:true}))")
        self.cliquer(self.Wait(self.d, 10).until(self.EC.element_to_be_clickable((self.By.CSS_SELECTOR, "button.mat-calendar-period-button"))))
        time.sleep(0.5)
        for lbl in (cal["annee"], cal["mois"], cal["jour"]):
            for _ in range(6):
                cells = self.d.find_elements(self.By.CSS_SELECTOR, f".mat-calendar-body-cell[aria-label={json.dumps(lbl, ensure_ascii=False)}]")
                if cells:
                    self.cliquer(cells[0])
                    time.sleep(0.5)
                    break
                self.cliquer(self.d.find_element(self.By.CSS_SELECTOR, ".mat-calendar-next-button"))
                time.sleep(0.4)
            else:
                raise ArretRobot(f"date introuvable dans le calendrier : {lbl}")

    def fichier(self, index: int, chemin: Path) -> None:
        inputs = self.d.find_elements(self.By.CSS_SELECTOR, "input[type=file]")
        if len(inputs) <= index:
            raise ArretRobot(f"emplacement de pièce jointe n° {index + 1} introuvable")
        self.d.execute_script("arguments[0].style.display='block'", inputs[index])
        inputs[index].send_keys(str(chemin))
        time.sleep(1.5)

    def suivant(self) -> None:
        boutons = [b for b in self.d.find_elements(self.By.XPATH, "//button[normalize-space()='Suivant']") if b.is_displayed()]
        if not boutons:
            raise ArretRobot("bouton « Suivant » introuvable")
        b = boutons[-1]
        self.Wait(self.d, 15).until(lambda _: b.is_enabled())
        self.cliquer(b)
        time.sleep(2)


def executer(portail: Portail, plan: dict, pieces: dict, jusqua: int, pause: bool) -> int:
    """Remplit les etapes 1 a min(4, jusqua). Retourne la derniere etape remplie."""
    faite = 0
    for e in plan["etapes"]:
        n = e["numero"]
        if n > 4 or n > jusqua:
            break
        print(f"\nÉTAPE {n} · {e['titre']}")
        for a in e["actions"]:
            v = a["valeur"]
            if v in (None, ""):
                if a["requis"]:
                    raise ArretRobot(f"valeur manquante : {a['question']}")
                print(f"   -  {a['question']} (vide, ignoré)")
                continue
            t = a["type"]
            if t == "radio":
                portail.radio(a["question"], v, a.get("par_valeur", False))
            elif t == "texte":
                portail.texte(a["question"], v)
            elif t == "frappe":
                portail.frappe(a["question"], v)
            elif t == "case":
                portail.case(v)
            elif t == "liste":
                portail.liste(a["question"], v)
            elif t == "commune":
                portail.commune(a["question"], v)
            elif t == "date":
                portail.date(a["calendrier"])
            elif t == "fichier":
                chemin = pieces.get(a["piece"]["id"]) if a.get("piece") else None
                if not chemin:
                    print(f"   -  {a['question']} : pièce non disponible, ignorée")
                    continue
                portail.fichier(a["index_fichier"], chemin)
            print(f"   ok {a['question'][:50]} = {str(v)[:50]}")
        portail.capture(f"etape{n}")
        faite = n
        if pause and n < min(4, jusqua):
            input(f">>> Étape {n} remplie. Vérifiez la fenêtre puis Entrée pour passer à l'étape {n + 1}... ")
        if n < 4 and n < jusqua:
            portail.suivant()
        elif n == 4:
            portail.suivant()  # ouvre l'etape 5 VALIDATION, sans rien y toucher
            portail.capture("etape5_validation")
    return faite


def main() -> int:
    ap = argparse.ArgumentParser(description="Robot D1 Amont : pré-remplit l'étude exploratoire RTE, sans jamais envoyer.")
    ap.add_argument("--demande", help="code de la demande dans Amont, ex. SOC-EE")
    ap.add_argument("--amont", default=AMONT_DEFAUT)
    ap.add_argument("--profil", default=str(PROFIL_DEFAUT))
    ap.add_argument("--simulation", action="store_true", help="affiche le plan de saisie sans ouvrir de navigateur")
    ap.add_argument("--pause", action="store_true", help="attend Entrée entre chaque étape")
    ap.add_argument("--jusqua", type=int, default=5, help="s'arrête après l'étape N (1 à 4)")
    ap.add_argument("--sans-statut", action="store_true", help="ne modifie pas la demande dans Amont")
    ap.add_argument("--banc", nargs="?", const=str(BANC), default=None,
                    help="répétition sur le banc d'essai local (imitation du formulaire) au lieu du portail RTE ; Amont n'est pas modifié")
    ap.add_argument("--chrome", default=os.environ.get("AMONT_CHROME"), help="chemin d'un Chrome particulier (facultatif)")
    ap.add_argument("--verifier", action="store_true", help="contrôle Amont, Selenium et Chrome, puis sort")
    ap.add_argument("--non-interactif", action="store_true",
                    help="lancé par l'agent du poste : pas de saisie clavier, attente de la connexion dans Chrome, pas de pause")
    args = ap.parse_args()
    url = args.amont.rstrip("/")

    try:
        if args.verifier:
            s = amont(url, "/sante")
            print(f"Amont {s['version']} joignable : {s['projets']} projets, {s['demandes']} demandes.")
            try:
                import selenium
                print(f"Selenium {selenium.__version__} installé.")
            except ImportError:
                print("Selenium absent :  pip install selenium")
                return 1
            print(f"Profil Chrome du robot : {args.profil}")
            return 0
        if not args.demande:
            ap.error("--demande est obligatoire (sauf avec --verifier)")

        plan = amont(url, f"/demandes/{urllib.parse.quote(args.demande)}/d1")
        afficher_plan(plan)
        val = (amont(url, f"/demandes/{urllib.parse.quote(args.demande)}") or {}).get("validation") or {}
        libelle_val = {"aucune": "pas encore demandée", "demandee": "demandée, en attente du responsable",
                       "validee": f"donnée par {val.get('traite_par')} le {(val.get('traite_le') or '')[:10]}",
                       "perimee": "périmée : le dossier a changé depuis", "refusee": "refusée"}.get(val.get("etat"), "inconnue")
        print(f"\nValidation du responsable : {libelle_val}")
        if args.simulation:
            return 0 if plan["pret"] else 1
        # deux cles : le portail complet n'est rempli que sur un dossier valide tel quel par le responsable.
        # Le banc d'essai et les essais partiels (--jusqua 1 a 3) restent possibles pour la mise au point.
        if val.get("requise") and val.get("etat") != "validee" and not args.banc and args.jusqua >= 4:
            raise ArretRobot("validation du responsable " + libelle_val + ". La demander depuis la fiche de la demande dans Amont, "
                             "ou tester avec --banc ou --jusqua 3")
        if not plan["pret"] and args.jusqua >= 3:
            raise ArretRobot("plan incomplet : compléter la fiche du site (voir MANQUANT ci-dessus), ou tester les premières étapes avec --jusqua 2")

        tmp = Path(tempfile.mkdtemp(prefix="amont_d1_"))
        pieces = {}
        for e in plan["etapes"]:
            for a in e["actions"]:
                if a["type"] == "fichier" and a.get("piece"):
                    pieces[a["piece"]["id"]] = telecharger_piece(url, a["piece"], tmp)
                    print(f"Pièce téléchargée : {a['piece']['nom']}")

        dossier = CAPTURES / f"{args.demande}_{datetime.now():%Y_%m_%d_%H%M}"
        portail = Portail(Path(args.profil), dossier, args.chrome)
        if args.banc:
            args.sans_statut = True
            print(f"\nBANC D'ESSAI : {args.banc} (le portail RTE n'est pas ouvert, Amont n'est pas modifié)")
            portail.ouvrir(Path(args.banc).resolve().as_uri(), not args.non_interactif)
        else:
            print("\nOuverture du portail RTE...")
            portail.ouvrir(plan["url"], not args.non_interactif)
        faite = executer(portail, plan, pieces, args.jusqua, args.pause and not args.non_interactif)

        print(f"\nCaptures : {dossier}")
        if faite >= 4:
            print("\n" + "=" * 78)
            print("FORMULAIRE PRÉ-REMPLI. Le robot s'est arrêté à l'étape 5, rien n'a été envoyé.")
            print("À vous : relire les 4 étapes, activer la certification, cliquer sur Envoyer,")
            print(f"puis passer {args.demande} à « Déposé » dans Amont avec la date du jour.")
            print("Ne rechargez pas la page : le portail ne garde aucun brouillon.")
            print("=" * 78)
            if not args.sans_statut:
                amont(url, f"/demandes/{urllib.parse.quote(args.demande)}", "PATCH", {"statut": "pret_validation"})
                amont(url, "/echanges", "POST", {"demande_id": args.demande, "sens": "note", "canal": "portail",
                                                 "objet": "Formulaire D1 pré-rempli par le robot",
                                                 "resume": "Arrêt avant la certification. Relecture et envoi à faire à la main.",
                                                 "attend_reponse": False})
                print(f"Amont : {args.demande} passée à « prêt pour validation ».")
        else:
            print(f"\nTest arrêté après l'étape {faite} comme demandé (--jusqua {args.jusqua}). Amont n'est pas modifié.")
        print("La fenêtre Chrome reste ouverte.")
        return 0
    except ArretRobot as e:
        print(f"\nARRÊT DU ROBOT : {e}")
        print("Rien n'a été envoyé à RTE. La fenêtre Chrome, si elle est ouverte, reste en l'état.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
