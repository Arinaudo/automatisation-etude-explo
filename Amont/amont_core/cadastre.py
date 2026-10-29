"""Extrait du plan cadastral officiel (DGFiP) d'un site, recupere sur cadastre.gouv.fr.

Sans compte ni navigateur : le service public de consultation du plan cadastral expose ses
formulaires en HTTP simple. Parcours releve le 27/10/2026 :

  1. accueil.do                              ouvre la session, donne le jeton CSRF
  2. rechercherParReferenceCadastrale.do     commune + departement + section + numero
                                             -> references internes parcelle et feuille
                                                (ex. CA547000AH0367 et CA547000AH01)
  3. afficherCarteParcelle.do                emprise de la parcelle (GeoBox), point d'etiquette
                                             (pastille) et projection (ex. RGF93CC47)
  4. imprimerExtraitCadastral.do             « Extrait du plan cadastral » normalise en PDF
                                             (cartouche DGFiP, echelle, date d'edition)

C'est le meme document que le bouton « Imprimer > Extrait de plan » du site. Gratuit.
Format A4 ou A3, echelles 1/500 a 1/5000 ; le cadre est choisi pour contenir toutes les
parcelles du site avec une marge. Le PDF fait environ 150 ko (limite RTE : 2 Mo).

Bibliotheque standard seulement : le module tourne dans le conteneur du serveur comme sur le poste.
"""

from __future__ import annotations

import html
import http.cookiejar
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date

BASE = "https://www.cadastre.gouv.fr/scpc/"
AGENT = "Amont/0.5 (registre des raccordements Castignac ; extrait cadastral)"
DELAI_RESEAU = 45
PAUSE = 1.0  # entre deux requetes : service public, on reste discret
ECHELLES = [500, 1000, 1250, 1500, 2000, 2500, 4000, 5000]
# Dimensions utiles du cadre en centiemes de millimetre, reprises du site (WorkerPrint.TAILLES_CMM) :
# {format: {orientation: (largeur, hauteur, bordure)}}
CADRES = {
    "A4": {"Paysage": (21070, 19700, 500), "Portrait": (19550, 21100, 500)},
    "A3": {"Paysage": (31600, 28300, 500), "Portrait": (28150, 30100, 500)},
}
ORDRE_FORMATS = [("A4", "Paysage"), ("A4", "Portrait"), ("A3", "Paysage"), ("A3", "Portrait")]
MARGE = 0.12          # part de l'emprise ajoutee de chaque cote
MARGE_MIN_M = 40      # au moins 40 m autour des parcelles
TAILLE_MAX_RTE = 2 * 1024 * 1024


class ErreurCadastre(Exception):
    """Message lisible, affiche tel quel sur le site."""


@dataclass
class Parcelle:
    section: str
    numero: str
    prefixe: str = "000"
    commune: str = ""            # commune demandee ; vide = commune principale du site
    trouvee_dans: str = ""
    ref: str = ""                # ex. CA547000AH0367
    feuille: str = ""            # ex. CA547000AH01
    emprise: tuple | None = None  # (minx, miny, maxx, maxy) dans la projection du site
    pastille: tuple | None = None
    projection: str = ""

    @property
    def libelle(self) -> str:
        return f"{self.section} {int(self.numero)}" if self.numero.isdigit() else f"{self.section} {self.numero}"


@dataclass
class Resultat:
    pdf: bytes
    nom_fichier: str
    parcelles: list[Parcelle]
    absentes: list[str] = field(default_factory=list)
    echelle: int = 0
    format: str = ""
    orientation: str = ""
    projection: str = ""
    communes: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)  # une page par commune : commune, echelle, format, orientation, parcelles
    titre: str = "Extrait du plan cadastral"

    def bilan(self) -> str:
        pages = "; ".join(f"{pg['commune']} : {pg['format']} {pg['orientation'].lower()} au 1/{pg['echelle']}, "
                          + ", ".join(pg["parcelles"]) for pg in self.pages)
        t = f"{self.titre}, {len(self.pages)} page{'s' if len(self.pages) > 1 else ''} ({pages}), {len(self.pdf) // 1024} ko"
        if self.absentes:
            t += ". Introuvables : " + ", ".join(self.absentes)
        return t


# --------------------------------------------------------------------------- lecture des parcelles
def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def nom_cadastre(commune: str) -> str:
    """« Roissy-en-Brie » -> « ROISSY EN BRIE », « L'Isle-d'Abeau » -> « L ISLE D ABEAU »."""
    t = _sans_accents(commune or "").upper()
    t = re.sub(r"[-'’]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def lire_parcelles(texte: str) -> list[Parcelle]:
    """« AH 367, AH 368 » ; « 000 AH 367 » ; « AH0367 » ; « Exincourt : AD 45, AD 46 ; Sochaux : AH 367 ».
    Un nom de commune suivi de deux-points s'applique aux parcelles qui suivent, jusqu'au prochain."""
    out: list[Parcelle] = []
    vues = set()
    commune = ""
    for morceau in re.split(r"[;\n]", texte or ""):
        m = re.match(r"\s*([A-Za-zÀ-ÿ' \-]{3,}?)\s*:\s*(.*)$", morceau)
        if m and not re.fullmatch(r"\s*(?:section|parcelles?|cadastre)\s*", m.group(1), re.I):
            commune, morceau = m.group(1).strip(), m.group(2)
        for p in re.finditer(r"\b(?:(\d{3})\s*)?([A-Z]{1,2}|0[A-Z])\s*(?:N[°O]\.?\s*)?0*(\d{1,4})\b", morceau.upper()):
            prefixe, section, numero = p.group(1) or "000", p.group(2), p.group(3)
            if len(section) == 1:
                section = "0" + section  # section a une lettre : « A » s'ecrit « 0A » dans les references
            cle = (commune.lower(), prefixe, section, numero)
            if cle in vues:
                continue
            vues.add(cle)
            out.append(Parcelle(section=section, numero=numero, prefixe=prefixe, commune=commune))
    return out


def code_departement(departement: str | None, code_insee: str | None) -> str:
    """Code a trois caracteres du formulaire : 25 -> 025, 2A -> 02A, 971 -> 971."""
    d = (departement or "").strip().upper()
    if not re.fullmatch(r"\d{2,3}|2[AB]", d):
        insee = (code_insee or "").strip().upper()
        d = insee[:3] if insee.startswith("97") else insee[:2]
    if not re.fullmatch(r"\d{2,3}|2[AB]", d):
        raise ErreurCadastre("département inconnu : renseigner le département ou le code INSEE dans la fiche du site")
    return d if len(d) == 3 else "0" + d


# --------------------------------------------------------------------------- session HTTP
class Session:
    def __init__(self, delai: int = DELAI_RESEAU):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.op.addheaders = [("User-Agent", AGENT), ("Accept-Language", "fr-FR,fr;q=0.9")]
        self.delai = delai
        self.jeton = ""

    def _lire(self, chemin: str, donnees: dict | None = None) -> tuple[bytes, str]:
        """Requete avec cinq essais espaces (3, 8, 20 puis 40 s) sur les erreurs passageres (429, 5xx, coupure).
        Le service renvoie par intermittence des 503 (environ une requete sur trois le 27/10/2026)."""
        url = BASE + chemin
        corps = urllib.parse.urlencode(donnees).encode() if donnees is not None else None
        derniere = None
        for attente in (0, 3, 8, 20, 40):
            if attente:
                time.sleep(attente)
            try:
                with self.op.open(url, data=corps, timeout=self.delai) as r:
                    contenu = r.read()
                    time.sleep(PAUSE)
                    return contenu, r.headers.get("Content-Type", "")
            except urllib.error.HTTPError as e:
                derniere = e
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except OSError as e:
                derniere = e
        detail = f"HTTP {derniere.code}" if isinstance(derniere, urllib.error.HTTPError) else f"{type(derniere).__name__} : {derniere}"
        raise ErreurCadastre(f"cadastre.gouv.fr ne répond pas ({detail}). Le service est parfois indisponible : réessayer plus tard.")

    def ouvrir(self) -> None:
        contenu, _ = self._lire("accueil.do")
        m = re.search(rb"CSRF_TOKEN=([A-Z0-9-]{10,})", contenu)
        if not m:
            raise ErreurCadastre("cadastre.gouv.fr a changé sa page d'accueil (jeton de session introuvable)")
        self.jeton = m.group(1).decode()

    def chercher(self, p: Parcelle, ville: str, departement: str) -> bool:
        """Remplit p.ref et p.feuille si la parcelle existe sur cette commune. Le service ne trouve rien avec les
        tirets et apostrophes des noms de communes (« Roissy-en-Brie ») : on cherche « ROISSY EN BRIE »."""
        forme = nom_cadastre(ville)
        if self._chercher(p, forme, departement):
            return True
        return forme != ville and self._chercher(p, ville, departement)

    def _chercher(self, p: Parcelle, ville: str, departement: str) -> bool:
        contenu, _ = self._lire("rechercherParReferenceCadastrale.do", {
            "CSRF_TOKEN": self.jeton, "ville": ville, "codePostal": "", "codeDepartement": departement,
            "rechercheType": "1", "prefixeParcelle": p.prefixe, "sectionLibelle": p.section,
            "numeroParcelle": p.numero, "nbResultatParPage": "10"})
        h = contenu.decode("latin-1", "replace")
        liens = re.findall(r"afficherCarteParcelle\.do\?[^\"']*?p=([A-Z0-9]+)&(?:amp;)?f=([A-Z0-9]+)", h)
        if not liens:
            if re.search(r"plusieurs communes|choisir la commune|listerCommunes", h, re.I):
                raise ErreurCadastre(f"commune ambiguë sur cadastre.gouv.fr : « {ville} ». Préciser le code postal ou le nom exact")
            return False
        p.ref, p.feuille = liens[0]
        m = re.search(r"commune suivante\s*:\s*([^<(]+)", html.unescape(h))
        p.trouvee_dans = (m.group(1).strip() if m else ville).title()
        return True

    def situer(self, p: Parcelle) -> None:
        """Emprise, pastille et projection de la parcelle, lues dans la page de la carte."""
        contenu, _ = self._lire(f"afficherCarteParcelle.do?CSRF_TOKEN={self.jeton}&p={p.ref}&f={p.feuille}")
        h = contenu.decode("latin-1", "replace")
        boites = re.findall(r"new GeoBox\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\)", h)
        proj = re.search(r'"(RGF93CC\d{2}|RGF93LAMB93|[A-Z0-9]+CC\d{2}|LAMB\w*)"', h)
        pastille = re.search(r"tabPastilles\.push\(new Point\(([\d.]+),([\d.]+)\)\)", h)
        if not boites:
            raise ErreurCadastre(f"carte de la parcelle {p.libelle} illisible sur cadastre.gouv.fr")
        p.emprise = tuple(float(v) for v in boites[0])
        p.pastille = (float(pastille.group(1)), float(pastille.group(2))) if pastille else (
            (p.emprise[0] + p.emprise[2]) / 2, (p.emprise[1] + p.emprise[3]) / 2)
        p.projection = proj.group(1) if proj else ""

    def imprimer(self, cadre: tuple, reference: tuple, echelle: int, format_: str, orientation: str,
                 document: str = "imprimerExtraitCadastral.do") -> bytes:
        """document : imprimerExtraitCadastral.do (extrait) ou imprimerPlanSituation.do (plan de situation)."""
        contenu, type_ = self._lire(f"{document}?CSRF_TOKEN={self.jeton}", {
            "MAPBBOX": ",".join(f"{v:.2f}" for v in cadre), "MAPROTATION": "0", "TAILLEPAGE": format_,
            "ORIENTPAGE": orientation, "RFV_REF": "", "RFV_X": f"{reference[0]:.2f}", "RFV_Y": f"{reference[1]:.2f}",
            "ECHELLE": str(echelle), "NATURE": "V", "RESOLUTION": "", "DRAPEAU": "false",
            **({"SLD_BODY": ""} if "PlanSituation" in document else {})})  # champ exige, meme vide, par le plan de situation
        if not contenu.startswith(b"%PDF"):
            try:
                brut = contenu.decode("utf-8")
            except UnicodeDecodeError:
                brut = contenu.decode("latin-1", "replace")
            t = re.sub(r"<[^>]+>", " ", brut)
            t = re.sub(r"\s+", " ", html.unescape(t)).strip()
            m = re.search(r"Attention\.*\s*(.{0,200})", t)
            raise ErreurCadastre("cadastre.gouv.fr n'a pas renvoyé de PDF : " + (m.group(1).strip() if m else (t[:200] or type_ or "réponse vide")))
        return contenu


# --------------------------------------------------------------------------- mise en page
def choisir_cadre(emprise: tuple, echelle_imposee: int | None = None, format_impose: str | None = None) -> tuple[int, str, str]:
    """Plus grande echelle (plan le plus detaille) dont le cadre contient l'emprise et sa marge."""
    larg = emprise[2] - emprise[0]
    haut = emprise[3] - emprise[1]
    besoin_l = larg + 2 * max(larg * MARGE, MARGE_MIN_M)
    besoin_h = haut + 2 * max(haut * MARGE, MARGE_MIN_M)
    echelles = [echelle_imposee] if echelle_imposee else ECHELLES
    formats = [f for f in ORDRE_FORMATS if not format_impose or f[0] == format_impose]
    for e in echelles:
        for fmt, ori in formats:
            w, h, b = CADRES[fmt][ori]
            if (w - 2 * b) * 1e-5 * e >= besoin_l and (h - 2 * b) * 1e-5 * e >= besoin_h:
                return e, fmt, ori
    fmt, ori = ("A3", "Paysage") if larg >= haut else ("A3", "Portrait")
    if format_impose:
        fmt = format_impose
    return echelles[-1], fmt, ori


def cadre_impression(centre: tuple, echelle: int, format_: str, orientation: str) -> tuple:
    w, h, _ = CADRES[format_][orientation]
    dl, dh = w * 1e-5 * echelle / 2, h * 1e-5 * echelle / 2
    return (centre[0] - dl, centre[1] - dh, centre[0] + dl, centre[1] + dh)


# --------------------------------------------------------------------------- point d'entree
def _resoudre(parcelles: str, commune: str, departement: str | None, code_insee: str | None,
              communes_secondaires: str, journal) -> tuple:
    """Parcelles de la fiche -> parcelles cadastre.gouv.fr (references, emprises), doublons tranches."""
    liste = lire_parcelles(parcelles)
    if not liste:
        raise ErreurCadastre("aucune parcelle dans la fiche du site : renseigner le champ « Parcelles cadastrales » (ex. AH 367, AH 368)")
    if not commune:
        raise ErreurCadastre("commune du site absente de la fiche")
    dep = code_departement(departement, code_insee)
    autres = [c.strip() for c in re.split(r"[,;/]| et ", communes_secondaires or "") if c.strip() and c.strip().lower() != commune.lower()]
    s = Session()
    s.ouvrir()
    # 1. chaque parcelle est cherchee dans toutes les communes candidates : une meme reference
    #    (AD 46) peut exister dans deux communes voisines.
    candidats: list[list[Parcelle]] = []
    absentes: list[str] = []
    for p in liste:
        villes = [p.commune] if p.commune else [commune] + autres
        trouves = []
        for ville in villes:
            q = Parcelle(section=p.section, numero=p.numero, prefixe=p.prefixe, commune=p.commune)
            if s.chercher(q, ville, dep):
                s.situer(q)
                trouves.append(q)
        if trouves:
            candidats.append(trouves)
        else:
            absentes.append(p.libelle + (f" ({p.commune})" if p.commune else ""))
            journal(f"   introuvable : {p.libelle} dans {', '.join(villes)}")
    # 2. doublons : on garde la parcelle la plus proche des parcelles sans ambiguite
    #    (a defaut, de celles de la commune principale).
    if not candidats:
        raise ErreurCadastre("aucune parcelle trouvée sur cadastre.gouv.fr : " + ", ".join(absentes)
                             + f" (commune cherchée : {', '.join([commune] + autres)}, département {dep})")
    surs = [c[0] for c in candidats if len(c) == 1]
    repere = surs or [c[0] for c in candidats]
    cx = sum(p.pastille[0] for p in repere) / len(repere)
    cy = sum(p.pastille[1] for p in repere) / len(repere)
    trouvees: list[Parcelle] = []
    avert: list[str] = []
    for c in candidats:
        choix = min(c, key=lambda p: (p.pastille[0] - cx) ** 2 + (p.pastille[1] - cy) ** 2)
        if len(c) > 1:
            avert.append(f"{choix.libelle} existe à {' et à '.join(p.trouvee_dans for p in c)} : retenue à {choix.trouvee_dans}, "
                         "voisine des autres parcelles. Pour imposer la commune, écrire « Commune : parcelles » dans la fiche")
        trouvees.append(choix)
        journal(f"   {choix.libelle} : {choix.trouvee_dans}, {choix.ref}" + (" (doublon tranché)" if len(c) > 1 else ""))
    if not trouvees:
        raise ErreurCadastre("aucune parcelle trouvée sur cadastre.gouv.fr : " + ", ".join(absentes))
    projections = {p.projection for p in trouvees if p.projection}
    if len(projections) > 1:
        raise ErreurCadastre("parcelles dans deux projections différentes (" + ", ".join(sorted(projections))
                             + ") : faire un extrait par commune avec « centrer sur »")
    return s, dep, trouvees, absentes, avert, projections


def extrait_site(parcelles: str, commune: str, departement: str | None = None, code_insee: str | None = None,
                 communes_secondaires: str = "", centrer_sur: str | None = None, echelle: int | None = None,
                 format_: str | None = None, nom_site: str = "", journal=print) -> Resultat:
    """Recupere l'extrait du plan cadastral couvrant les parcelles du site.

    parcelles : texte de la fiche (« AH 367, AH 368 » ou avec communes « Exincourt : AD 45 »).
    commune : commune principale ; communes_secondaires : autres communes ou chercher les parcelles absentes.
    centrer_sur : une parcelle (« AH 367 ») pour un extrait centre sur elle au lieu du site entier.
    """
    s, dep, trouvees, absentes, avert, projections = _resoudre(parcelles, commune, departement, code_insee,
                                                               communes_secondaires, journal)
    if centrer_sur:
        cible = [p for p in trouvees if p.libelle.replace(" ", "") == centrer_sur.upper().replace(" ", "")
                 or f"{p.section}{int(p.numero)}" == centrer_sur.upper().replace(" ", "")]
        if not cible:
            raise ErreurCadastre(f"parcelle {centrer_sur} absente de la liste du site")
        trouvees = cible
    # 3. une page par commune : le service ne dessine que la commune de la parcelle de reference.
    #    Commune principale (point de raccordement) en premiere page.
    groupes: dict[str, list[Parcelle]] = {}
    for p in trouvees:
        groupes.setdefault(p.trouvee_dans, []).append(p)
    ordre = sorted(groupes, key=lambda c: (_sans_accents(c).lower() != _sans_accents(commune).lower(), c))
    pdfs, pages = [], []
    for nom_commune in ordre:
        base = groupes[nom_commune]
        emprise = (min(p.emprise[0] for p in base), min(p.emprise[1] for p in base),
                   max(p.emprise[2] for p in base), max(p.emprise[3] for p in base))
        e, fmt, ori = choisir_cadre(emprise, echelle, format_)
        centre = ((emprise[0] + emprise[2]) / 2, (emprise[1] + emprise[3]) / 2)
        cadre = cadre_impression(centre, e, fmt, ori)
        # parcelle de reference du cartouche : la pastille la plus proche du centre, comme le site
        ref = min(base, key=lambda p: (p.pastille[0] - centre[0]) ** 2 + (p.pastille[1] - centre[1]) ** 2)
        # le site imprime dans le contexte de la derniere carte ouverte, et n'ouvre une carte qu'apres une
        # recherche qui la contient : recherche puis carte de la parcelle de reference, juste avant l'impression
        if not s.chercher(ref, ref.trouvee_dans, dep):
            raise ErreurCadastre(f"parcelle {ref.libelle} de {ref.trouvee_dans} introuvable au moment de l'impression")
        s.situer(ref)
        pdfs.append(s.imprimer(cadre, ref.pastille, e, fmt, ori))
        w, h, b_ = CADRES[fmt][ori]
        if (w - 2 * b_) * 1e-5 * e < emprise[2] - emprise[0] or (h - 2 * b_) * 1e-5 * e < emprise[3] - emprise[1]:
            avert.append(f"{nom_commune} : les parcelles débordent du cadre au 1/{e}, faire un extrait par parcelle (« centrer sur »)")
        pages.append({"commune": nom_commune, "echelle": e, "format": fmt, "orientation": ori,
                      "parcelles": [p.libelle for p in base], "reference": ref.libelle})
        journal(f"   page {len(pages)} : {nom_commune}, {fmt} {ori.lower()} au 1/{e}")
    pdf = pdfs[0] if len(pdfs) == 1 else assembler(pdfs)
    if len(pdf) > TAILLE_MAX_RTE:
        avert.append(f"PDF de {len(pdf) // 1024} ko, au-delà des 2 Mo acceptés par le portail RTE")
    communes = list(ordre)
    if _sans_accents(ordre[0]).lower() != _sans_accents(commune).lower():
        avert.append(f"aucune parcelle trouvée sur la commune principale ({commune}) : vérifier la commune du point de raccordement")
    cle = _sans_accents(nom_site or commune).replace(" ", "_")
    cle = re.sub(r"[^A-Za-z0-9_\-]", "", cle)[:40] or "site"
    nom = f"{date.today().strftime('%Y_%m_%d')}_extrait_cadastral_{cle}" + (f"_{centrer_sur.replace(' ', '')}" if centrer_sur else "") + ".pdf"
    return Resultat(pdf=pdf, nom_fichier=nom, parcelles=trouvees, absentes=absentes, echelle=pages[0]["echelle"],
                    format=pages[0]["format"], orientation=pages[0]["orientation"], projection=next(iter(projections), ""),
                    communes=communes, avertissements=avert, pages=pages)


MARGE_SITUATION = 0.45  # le plan de situation montre les abords : 45 % de l'emprise de chaque cote
ECHELLES_SITUATION = [2000, 2500, 4000, 5000]


def plan_situation_site(parcelles: str, commune: str, departement: str | None = None, code_insee: str | None = None,
                        communes_secondaires: str = "", nom_site: str = "", journal=print) -> Resultat:
    """« Plan de situation » DGFiP du site entier, une page A4 portrait : contrairement a l'extrait, il dessine
    toutes les communes (limites, sections, cours d'eau). Echelle 1/5000 au plus : le service ne va pas au-dela,
    un plan de situation au 1/25 000 (carte IGN) reste a joindre a part si l'operateur le demande."""
    s, dep, trouvees, absentes, avert, projections = _resoudre(parcelles, commune, departement, code_insee,
                                                               communes_secondaires, journal)
    emprise = (min(p.emprise[0] for p in trouvees), min(p.emprise[1] for p in trouvees),
               max(p.emprise[2] for p in trouvees), max(p.emprise[3] for p in trouvees))
    larg, haut = emprise[2] - emprise[0], emprise[3] - emprise[1]
    besoin_l, besoin_h = larg * (1 + 2 * MARGE_SITUATION), haut * (1 + 2 * MARGE_SITUATION)
    choix = None
    for e in ECHELLES_SITUATION:
        for fmt, ori in (("A4", "Portrait"), ("A4", "Paysage")):
            w, h, b = CADRES[fmt][ori]
            if (w - 2 * b) * 1e-5 * e >= besoin_l and (h - 2 * b) * 1e-5 * e >= besoin_h:
                choix = (e, fmt, ori)
                break
        if choix:
            break
    if not choix:
        choix = (5000, "A3", "Paysage" if larg >= haut else "Portrait")
        w, h, b_ = CADRES["A3"][choix[2]]
        if (w - 2 * b_) * 5e-2 < larg or (h - 2 * b_) * 5e-2 < haut:
            avert.append("site plus étendu que le plan de situation au 1/5000 (limite du service) : une partie déborde")
    e, fmt, ori = choix
    centre = ((emprise[0] + emprise[2]) / 2, (emprise[1] + emprise[3]) / 2)
    principales = [p for p in trouvees if _sans_accents(p.trouvee_dans).lower() == _sans_accents(commune).lower()] or trouvees
    ref = min(principales, key=lambda p: (p.pastille[0] - centre[0]) ** 2 + (p.pastille[1] - centre[1]) ** 2)
    if not s.chercher(ref, ref.trouvee_dans, dep):
        raise ErreurCadastre(f"parcelle {ref.libelle} de {ref.trouvee_dans} introuvable au moment de l'impression")
    s.situer(ref)
    pdf = s.imprimer(cadre_impression(centre, e, fmt, ori), ref.pastille, e, fmt, ori, "imprimerPlanSituation.do")
    journal(f"   plan de situation : {fmt} {ori.lower()} au 1/{e}, centré sur le site")
    cle = re.sub(r"[^A-Za-z0-9_\-]", "", _sans_accents(nom_site or commune).replace(" ", "_"))[:40] or "site"
    pages = [{"commune": ref.trouvee_dans, "echelle": e, "format": fmt, "orientation": ori,
              "parcelles": [p.libelle for p in trouvees], "reference": ref.libelle}]
    return Resultat(pdf=pdf, nom_fichier=f"{date.today().strftime('%Y_%m_%d')}_plan_situation_{cle}.pdf", parcelles=trouvees,
                    absentes=absentes, echelle=e, format=fmt, orientation=ori, projection=next(iter(projections), ""),
                    communes=sorted({p.trouvee_dans for p in trouvees}), avertissements=avert, pages=pages,
                    titre="Plan de situation")


def assembler(pdfs: list[bytes]) -> bytes:
    """Un seul PDF a plusieurs pages (le portail RTE n'accepte qu'un fichier). Necessite pypdf."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        raise ErreurCadastre("site sur plusieurs communes : pypdf manque pour assembler les pages (pip install pypdf)") from None
    import io
    w = PdfWriter()
    for b in pdfs:
        for page in PdfReader(io.BytesIO(b)).pages:
            w.add_page(page)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()
