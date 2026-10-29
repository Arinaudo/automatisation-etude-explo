# Releve du formulaire D1 RTE pour automatisation Selenium (Sochaux 300 MW, 05/10/2026)

Formulaire rempli dans Chrome jusqu'a l'etape 5, arrete AVANT l'interrupteur de certification.
Rien n'a ete envoye. Ne pas recharger la page : aucun brouillon n'est sauvegarde cote RTE.

## Valeurs saisies (a relire)

| Etape | Champ | Valeur |
|---|---|---|
| 1 | Societe francaise / SIREN | Oui / 880034798 (CASTIGNAC affiche) |
| 1 | Boite aux lettres | Nominative |
| 1 | Interlocuteur | RINAUDO Alexis, "Data Automation and Systems Analyst" |
| 1 | Telephone / mail | 0184258000 / arinaudo@castignac.com |
| 1 | Mandataire | Non |
| 2 | Type / nature / secteur | Nouveau raccordement HTB / Consommation / Datacenter |
| 2 | Commentaire (452/500) | Contexte PSA Sud, 300 MW, poste 225 kV Etupes a 1,6 km |
| 3 | Nom installation | Datacenter Sochaux PSA Sud |
| 3 | Commune / INSEE | Sochaux / 25547 - Sochaux |
| 3 | GPS | 47.50902 / 6.83147 (centroide parcelle AH 367, Sochaux, 11,28 ha) |
| 3 | Date mise a disposition | 30/09/2031 (HYPOTHESE, a valider) |
| 3 | Extrait cadastral | NON JOINT (bloquant pour la recevabilite) |
| 4 | HTA existant / demande HTA | Non / Non |
| 4 | Puissance | 300 MW |
| 4 | Alimentations HTB supplementaires | 0 (a arbitrer : 1 = secours, contribution 85 %) |
| 4 | Scc min / Pmin securite | Non / vide |
| 4 | Elements complementaires (644/1000) | Profil datacenter + 4 questions (transit, renforcements, reactif, limitations temporaires) |
| 4 | Plan de l'installation | NON JOINT |

## Nouveaux enseignements pour l'automatisation

1. **Session** : l'URL du formulaire redirige vers `home.html?login=true` si non connecte. Avec Selenium, reutiliser
   un profil Chrome deja connecte (`--user-data-dir`) plutot que d'automatiser le login.
2. **Identifiants positionnels confirmes** : cette fois mat-radio-13 a 34, mat-input-0 a 14, mat-select-0 et 2,
   mat-slide-toggle-1 (le releve du 04/09 avait d'autres numeros). Cibler par libelle de question.
3. **Champs texte simples** : `value` + evenement `input` + `blur` SUFFIT (nom, prenom, fonction, tel, mail,
   nom installation, GPS, puissance, textareas). Pas besoin de frappes clavier pour eux.
4. **Champ Fonction** : regex cachee. Refuse virgule, `&`, `/`, chiffres. Accepte lettres, accents, espace,
   tiret, apostrophe. Message : "Le champ n'est pas dans le bon format". Nettoyer la valeur avant saisie.
5. **SIREN** : vraies frappes + Tab. Appel `GET /api/identifiers/siren/{siren}`, le nom CASTIGNAC s'affiche.
6. **Cases Consommation/Production...** : le libelle n'est PAS dans `mat-checkbox` mais dans le parent
   `cortex-checkbox`. Selecteur : `cortex-checkbox` dont le texte = "Consommation", puis `label.mat-checkbox-layout`.
7. **Secteur d'activite** : clic sur `mat-select`, puis `mat-option` de texte "Datacenter" (15 options, overlay CDK).
8. **Commune** : vraies frappes. L'autocompletion appelle `geo.api.gouv.fr/communes?nom=...` (API publique),
   puis il faut cliquer l'option. Le Code INSEE se remplit tout seul ("25547 - Sochaux").
9. **PIEGE NOUVEAU : choisir la commune EFFACE latitude et longitude.** Ordre impose : commune d'abord, GPS ensuite.
10. **GPS** : `maxlength=8`, donc 5 decimales max pour la latitude (47.50902). Le champ affiche la virgule (47,50902).
11. **Date** : lecture seule, `min` = lendemain. Le clic doit etre un `dispatchEvent(MouseEvent('click'))` sur
    `cortex-datepicker-icon` (pas d'element enfant cliquable). Puis `button.mat-calendar-period-button`, puis
    cellules par `aria-label` : "2031", "septembre 2031", "30 septembre 2031". Affichage : "mardi, 30 septembre 2031".
12. **Pieces jointes** : `input[type=file]` CACHE, `accept=.pdf`, un seul fichier. Avec Selenium, `send_keys(chemin)`
    directement sur l'input (le rendre visible par JS si besoin), ne jamais cliquer "Ajouter une piece jointe".
13. **Radios** : cliquer `label[for=<id input>]` apres avoir trouve le bloc dont le texte commence par la question.
14. **Validation** : `mat-slide-toggle` non coche, bouton "Envoyer" desactive. Le robot doit s'arreter ici.
15. Les etapes precedentes restent ouvertes (accordeon cumulatif) : prendre le bouton "Suivant" VISIBLE.
16. Pas d'appel API de soumission observable avant l'envoi : pas de raccourci HTTP possible, le navigateur reste necessaire.

## Recettes Selenium (Python)

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

URL = "https://www.services-rte.com/fr/realiser-une-demande-detude-exploratoire.html"


def ouvrir(profil_chrome):
    opts = webdriver.ChromeOptions()
    opts.add_argument(f"--user-data-dir={profil_chrome}")  # profil deja connecte au portail
    d = webdriver.Chrome(options=opts)
    d.get(URL)
    if "login=true" in d.current_url:
        input("Connecte-toi dans la fenetre puis appuie sur Entree...")
        d.get(URL)
    WebDriverWait(d, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "mat-radio-button")))
    return d


JS_BLOC_QUESTION = """
const q = arguments[0];
const els = [...document.querySelectorAll('input,textarea,mat-select')];
for (const e of els) {
  let p = e;
  for (let k = 0; k < 8; k++) { p = p.parentElement; if (p.innerText.trim().length > 15) break; }
  if (p.innerText.trim().startsWith(q)) return e;
}
return null;
"""


def champ(d, question):
    e = d.execute_script(JS_BLOC_QUESTION, question)
    if e is None:
        raise LookupError(question)
    return e


def texte(d, question, valeur):
    e = champ(d, question)
    d.execute_script(
        "arguments[0].value=arguments[1];"
        "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
        "arguments[0].dispatchEvent(new Event('blur',{bubbles:true}));", e, valeur)


def frappe(d, question, valeur):
    e = champ(d, question)
    e.click()
    e.send_keys(valeur)


def radio(d, question, option):
    ok = d.execute_script("""
      const [q, opt] = arguments;
      for (const e of document.querySelectorAll('input[type=radio]')) {
        let p = e;
        for (let k = 0; k < 8; k++) { p = p.parentElement; if (p.innerText.trim().length > 15) break; }
        const l = document.querySelector(`label[for="${e.id}"]`);
        if (p.innerText.trim().startsWith(q) && l && l.innerText.trim() === opt) { l.click(); return true; }
      }
      return false;""", question, option)
    if not ok:
        raise LookupError(f"{question} -> {option}")
    time.sleep(0.5)


def case(d, libelle):
    d.execute_script("""
      const c = [...document.querySelectorAll('cortex-checkbox')].find(c => c.innerText.trim() === arguments[0]);
      c.querySelector('label.mat-checkbox-layout').click();""", libelle)


def select(d, question, option):
    champ(d, question).click()
    WebDriverWait(d, 10).until(EC.element_to_be_clickable(
        (By.XPATH, f"//mat-option[normalize-space()='{option}']"))).click()


def commune(d, nom):
    frappe(d, "Nom de la commune", nom)
    WebDriverWait(d, 10).until(EC.element_to_be_clickable(
        (By.XPATH, f"//mat-option[normalize-space()='{nom}']"))).click()
    time.sleep(1.5)  # le Code INSEE se peuple, et le GPS est remis a zero


def date(d, annee, mois_fr, jour):
    d.execute_script("document.querySelector('cortex-datepicker-icon')"
                     ".dispatchEvent(new MouseEvent('click',{bubbles:true}))")
    WebDriverWait(d, 10).until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, "button.mat-calendar-period-button"))).click()
    for lbl in (str(annee), f"{mois_fr} {annee}", f"{jour} {mois_fr} {annee}"):
        for _ in range(5):
            cells = d.find_elements(By.CSS_SELECTOR, f".mat-calendar-body-cell[aria-label='{lbl}']")
            if cells:
                cells[0].click()
                time.sleep(0.5)
                break
            d.find_element(By.CSS_SELECTOR, ".mat-calendar-next-button").click()
            time.sleep(0.4)
        else:
            raise LookupError(lbl)


def piece_jointe(d, index, chemin_pdf):
    inputs = d.find_elements(By.CSS_SELECTOR, "input[type=file]")
    d.execute_script("arguments[0].style.display='block'", inputs[index])
    inputs[index].send_keys(chemin_pdf)


def suivant(d):
    b = [b for b in d.find_elements(By.XPATH, "//button[normalize-space()='Suivant']") if b.is_displayed()][-1]
    WebDriverWait(d, 10).until(lambda _: b.is_enabled())
    b.click()
    time.sleep(1.5)
```

Fonction de nettoyage du champ Fonction : `re.sub(r"[^A-Za-zÀ-ÿ' -]", " ", fonction)`.

## Complements apres rechargement accidentel (2e remplissage, 05/10/2026)

17. **Rechargement = tout est perdu**, confirme. Le robot doit pouvoir rejouer la saisie complete de bout en bout.
18. **La mise en page depend de la largeur de fenetre** : fenetre etroite = accordeon vertical ou les etapes restent
    ouvertes ; fenetre large = stepper horizontal ou seule l'etape courante est visible. Fixer la taille de fenetre
    dans Selenium (`driver.set_window_size(1600, 900)`) pour avoir un comportement stable.
19. **Les identifiants etaient identiques au 1er passage de la meme session** (mat-radio-13 a 21, mat-input-0...), mais
    differents du releve du 04/09 : toujours cibler par libelle.
20. **Autocompletion commune lente** : "Aucun resultat" s'affiche pendant 3 a 5 s avant la liste. Attendre l'option
    explicitement (WebDriverWait jusqu'a 10 s), jamais un sleep fixe court.
21. **Recherche de la question d'un radio** : remonter depuis le `mat-radio-group` et non depuis l'input, sinon pour
    les options longues ("Nouveau raccordement HTB", "Nominative ex: ...") on recupere le libelle de l'option au lieu
    de la question. Pour ces cas, cibler directement l'input par `value` (`input[type=radio][value='Nominative']`).
22. Les contacts (nom, prenom, fonction, tel, mail) n'apparaissent qu'APRES le choix Generique/Nominative.
