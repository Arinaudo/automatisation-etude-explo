"""Plan de remplissage du Portail Raccordement Enedis (marche d'affaires), demande HTA « Un site industriel en HTA ».

Tous les sites Castignac passent par ce parcours, chantier compris (branchement provisoire, etape Echeance).

Meme principe que d1.py : une seule source du mapping fiche -> formulaire, lue par le site (apercu) et par le robot
du poste (2026_10_28_amont_robot_enedis.py). Formulaire releve en direct le 28/10/2026 sur
raccordement-entreprise-enedis.fr (commune SOCHAUX, type « Un site industriel en HTA »), sans rien envoyer.

Ce qu'il faut savoir du portail (releve du 28/10) :
  - application Vue 2 : les 4 etapes (Coordonnees, Construction, Documents, Echeance) sont dans la meme page,
    un seul bouton « Suivant » les fait defiler ; les champs conditionnels n'existent qu'apres la reponse qui
    les ouvre ;
  - les attributs name et les valeurs des boutons radio sont stables ; les id sont des GUID tires a chaque
    chargement : le robot cible par name (et par libelle quand deux champs partagent un name, rampe) ;
  - communes : recherche en direct (« SOCHAUX (25600) »), code postal et INSEE remplis par le portail ;
  - date de mise en service : JJ/MM/AAAA tapee, au plus tot demain ;
  - Pracc : liste fermee en kW, de 500 a 19 500 par pas de 500, puis « Plus de 20000 ».
Le robot s'arrete sur l'etape Echeance sans cliquer le dernier « Suivant » : la suite (recapitulatif, envoi)
est humaine.

Types d'action :
  radio     input[type=radio][name=...][value=...], clic sur son libelle
  case      input[type=checkbox][name=...]
  texte     input ou textarea [name=...] : valeur + evenement input (v-model)
  commune   recherche en direct : frappe, puis option dont le libelle commence par le nom et contient le code postal
  liste     v-select a options fixes (Pracc) : option exacte
  date      JJ/MM/AAAA tapee dans input[name=date]
  fichier   input[type=file][name=...], piece telechargee depuis Amont
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

URL_ENEDIS = "https://www.raccordement-entreprise-enedis.fr/DemandeRaccordement/Raccordement?init=True"
TITRES = {1: "Coordonnées", 2: "Construction", 3: "Documents", 4: "Échéance"}
PRACC_OPTIONS = [500, 750] + list(range(1000, 20000, 500))
LIMITE_HTA_KW = 40000


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def nom_portail(commune: str) -> str:
    """« Roissy-en-Brie » -> « ROISSY EN BRIE » : forme des libelles de la recherche de commune."""
    return re.sub(r"\s+", " ", re.sub(r"[-'’]", " ", _sans_accents(commune or "").upper())).strip()


def pracc_option(kw) -> str | None:
    """Plus petite valeur de la liste du portail qui couvre la puissance demandee (kW)."""
    try:
        kw = float(kw)
    except (TypeError, ValueError):
        return None
    if kw <= 0:
        return None
    for o in PRACC_OPTIONS:
        if o >= kw:
            return str(o)
    return "Plus de 20000"


def couper_adresse(adresse: str) -> tuple[str, str]:
    """« 8, rue Lincoln » -> (« 8 », « rue Lincoln »). Numero 4 caracteres au plus, voie 33."""
    m = re.match(r"\s*(\d{1,4}\s*(?:bis|ter)?)\s*,?\s+(.+)$", adresse or "", re.I)
    if m:
        return m.group(1).replace(" ", "")[:4], m.group(2).strip()[:33]
    return "", (adresse or "").strip()[:33]


def couper_cp_ville(t: str) -> tuple[str, str]:
    m = re.match(r"\s*(\d{5})\s+(.+)$", t or "")
    return (m.group(1), m.group(2).strip()) if m else ("", (t or "").strip())


def couper_representant(t: str) -> tuple[str, str, str]:
    """« David TAIEB, Gérant » -> (nom, prenom, fonction). Nom = mots en capitales, sinon dernier mot."""
    t = (t or "").strip()
    personne, _, fonction = t.partition(",")
    mots = personne.split()
    if not mots:
        return "", "", fonction.strip()
    nom = [m for m in mots if m.isupper() and len(m) > 1]
    if nom:
        prenom = [m for m in mots if m not in nom]
    else:
        nom, prenom = mots[-1:], mots[:-1]
    return " ".join(nom), " ".join(prenom), fonction.strip()


def groupes(t: str) -> tuple[int | None, int | None]:
    """« 40 groupes de 3 MW » -> (40, 120000 kW). (None, None) si illisible."""
    m = re.search(r"(\d+)\s*groupes?[^\d]{0,20}?(\d+(?:[.,]\d+)?)\s*(MW|kW|kVA|MVA)", t or "", re.I)
    if not m:
        return None, None
    n, p, u = int(m.group(1)), float(m.group(2).replace(",", ".")), m.group(3).lower()
    kw = p * (1000 if u in ("mw", "mva") else 1)
    return n, int(round(n * kw))


def _tel(t) -> str | None:
    c = re.sub(r"[^0-9+]", "", str(t or ""))
    if c.startswith("+33"):
        c = "0" + c[3:]
    return c or None


def _date_fr(v) -> str | None:
    try:
        d = date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None
    return d.strftime("%d/%m/%Y")


def _premiere_parcelle(parcelles: str) -> tuple[str, str]:
    m = re.search(r"\b(?:\d{3}\s*)?([A-Z]{1,2}|0[A-Z])\s*0*(\d{1,4})\b", (parcelles or "").upper())
    if not m:
        return "", ""
    return m.group(1).lstrip("0") or m.group(1), m.group(2)


def plan(payload: dict, aujourdhui: date | None = None) -> dict:
    """payload : sortie de Registre.payload() d'une demande Enedis."""
    auj = aujourdhui or date.today()
    fi = payload.get("fiche") or {}
    type_enedis = payload.get("type_enedis") or "hta"
    pieces: dict[str, dict] = {}
    for p in sorted(payload.get("pieces") or [], key=lambda x: (x.get("ajoute_le") or "", x.get("id") or 0), reverse=True):
        if p["type"] not in pieces:
            pieces[p["type"]] = {"id": p["id"], "nom": p["nom_fichier"], "taille": p.get("taille_octets")}

    etapes: dict[int, list] = {i: [] for i in range(1, 5)}

    def act(n, question, type_, cible, valeur, requis=True, source="", note="", **extra):
        manque = requis and valeur in (None, "")
        etapes[n].append({"question": question, "type": type_, "cible": cible, "valeur": valeur, "requis": requis,
                          "source": source, "note": note, "manque": manque, **extra})

    # Tous les sites passent par « Un site industriel en HTA » (consigne du 28/10/2026) ; le besoin de chantier se
    # declare dans ce meme formulaire, etape Echeance (branchement provisoire le temps de la construction).

    # ---------------------------------------------------------------- 0 commune et type (ecran d'accueil)
    commune_site = fi.get("commune") or payload.get("commune")
    cp_site = fi.get("code_postal")
    accueil = {"commune": nom_portail(commune_site) if commune_site else None, "code_postal": cp_site,
               "type": "Un site industriel en HTA"}

    # ---------------------------------------------------------------- 1 COORDONNEES
    permis = bool(fi.get("permis_numero")) or "permis" in pieces
    act(1, "Demande", "radio", "raccDefinition", "true" if permis else "false", source="fiche : permis",
        note="définitive : autorisation d'urbanisme obtenue" if permis else
             "anticipée : pas encore de permis ; prestation payante, à transformer en définitive auprès d'Enedis ensuite",
        libelle="Définitive" if permis else "Anticipée")
    if permis:
        act(1, "Travaux sur les ouvrages dédiés", "radio", "IsTravauxEnedis", "true", source="fixe", libelle="réalisés par Enedis")
    act(1, "Statut", "radio", "radioTypeClientBeneficiaire", "Entreprise", source="fixe", libelle="Une entreprise")
    act(1, "N° SIRET", "texte", "SiretEntrepriseBeneficiaire", re.sub(r"\D", "", str(fi.get("demandeur_siret") or "")) or None,
        source="fiche : SIRET", note="14 chiffres")
    act(1, "Raison sociale", "texte", "raisonSocialeEntrepriseBeneficiaire", fi.get("demandeur_societe"), source="fiche")
    civ = str(fi.get("interlocuteur_civilite") or "").strip().lower()
    civ = "Monsieur" if civ.startswith(("m.", "mr", "monsieur")) or civ == "m" else ("Mme" if civ.startswith(("mme", "madame")) else None)
    act(1, "Civilité", "radio", "radioCiviliteBeneficiaire", civ, source="fiche : civilité de l'interlocuteur")
    act(1, "E-mail", "texte", "mailBeneficiaire-0", fi.get("interlocuteur_mail"), source="fiche")
    act(1, "Nom", "texte", "nomBeneficiaire-0", fi.get("interlocuteur_nom"), source="fiche")
    act(1, "Prénom", "texte", "prenomBeneficiaire-0", fi.get("interlocuteur_prenom"), source="fiche")
    num, voie = couper_adresse(fi.get("demandeur_siege_adresse") or fi.get("adresse_facturation") or "")
    act(1, "Numéro", "texte", "NumeroBeneficiaire", num or None, requis=False, source="fiche : siège social")
    act(1, "Adresse", "texte", "adresseBeneficiaire_0", voie or None, source="fiche : siège social", note="33 caractères au plus")
    cp, ville = couper_cp_ville(fi.get("demandeur_siege_cp_ville") or "")
    act(1, "Commune", "commune", "communeBeneficiaire_0", nom_portail(ville) if ville else None, source="fiche : siège social",
        code_postal=cp, note="code postal et INSEE remplis par le portail")
    tel = _tel(fi.get("interlocuteur_tel"))
    port = _tel(fi.get("interlocuteur_portable")) or tel
    act(1, "Téléphone", "texte", "telfixeBeneficiaire", tel, source="fiche")
    act(1, "Téléphone portable", "texte", "telephoneportableBeneficiaire", port, source="fiche",
        note="" if fi.get("interlocuteur_portable") else "pas de portable dans la fiche : téléphone fixe repris")
    act(1, "Notification par mail", "radio", "notifByMail", "true", source="fixe", libelle="Oui")
    act(1, "Notification par SMS", "radio", "notifBySMS", "false", source="fixe", libelle="Non")
    act(1, "Coordonnées du siège social", "radio", "rbCoordonnesSC", "Sont les mêmes que celles du bénéficiaire du raccordement",
        source="fixe", libelle="les mêmes")
    act(1, "Siège : nom", "texte", "scNomSociete", fi.get("demandeur_societe"), source="fiche")
    act(1, "Siège : statut juridique", "texte", "scStatutJuridique", fi.get("demandeur_forme_juridique"), source="fiche")
    act(1, "Siège : SIREN", "texte", "scImmatNumero", re.sub(r"\D", "", str(fi.get("demandeur_siren") or ""))[:9] or None, source="fiche")
    act(1, "Siège : lieu d'immatriculation", "texte", "scImmatLieu", fi.get("demandeur_rcs"), source="fiche")
    act(1, "Siège : capital (€)", "texte", "scCapital", re.sub(r"[^\d]", "", str(fi.get("demandeur_capital") or "")) or None,
        source="fiche : capital social")
    s_nom, s_prenom, s_fonction = couper_representant(fi.get("demandeur_representant") or "")
    act(1, "Signataire de la convention : nom", "texte", "scSignataireNom", s_nom or None, source="fiche : représentant légal")
    act(1, "Signataire : prénom", "texte", "scSignatairePrenom", s_prenom or None, source="fiche : représentant légal")
    act(1, "Signataire : fonction", "texte", "scSignataireFonction", s_fonction or None, source="fiche : représentant légal",
        note="écrire « Prénom NOM, Fonction » dans la fiche")
    act(1, "Tiers mandaté", "radio", "radioTiersMandate", "false", source="fixe", libelle="Non",
        note="le bénéficiaire dépose lui-même ; si Castignac dépose pour la société de projet, joindre le mandat Enedis")
    act(1, "Envoi des documents contractuels", "radio", "radioAdresse", "beneficiaire", source="fixe", libelle="la même adresse")
    act(1, "Interlocuteur technique du chantier", "radio", "radioInterlocuteur", "beneficiaire", source="fixe", libelle="le bénéficiaire")

    # ---------------------------------------------------------------- 2 CONSTRUCTION
    num_s, voie_s = couper_adresse(fi.get("adresse") or "")
    act(2, "Numéro du chantier", "texte", "NumeroConstruction", num_s or None, requis=False, source="fiche : adresse du site")
    act(2, "Adresse du chantier", "texte", "adresseConstruction", voie_s or None, source="fiche : adresse du site",
        note="commune, code postal et INSEE repris de l'écran d'accueil")
    act(2, "Dénomination du site", "texte", "DenominationSite", fi.get("nom_installation") or payload.get("site"), source="fiche")
    zac = fi.get("zac_nom")
    act(2, "Située sur une ZAC", "radio", "rbChantierIsZAC", "true" if zac else "false", source="fiche : ZAC", libelle="Oui" if zac else "Non")
    if zac:
        act(2, "Nom de la ZAC", "texte", "NomZAC", str(zac)[:100], source="fiche")
    act(2, "Votre projet concerne", "radio", "rbTypeRaccHTA", "Nouveau raccordement (principal)", source="fixe", libelle="Un nouveau raccordement")
    act(2, "Usage : centre de données", "case", "UsageDataCenter", True, source="fixe")
    act(2, "IRVE", "radio", "rbAlimentationBorneRechargeVehicule", "false", source="fixe", libelle="Non")
    act(2, "Configuration du raccordement", "radio", "rbTypeRaccordement", "Un raccordement de référence", source="fixe")
    kw = None
    if payload.get("puissance_kva") not in (None, ""):
        kw = float(payload["puissance_kva"])
        src_p = "demande : puissance kVA"
    elif fi.get("puissance_mw") not in (None, ""):
        kw = float(fi["puissance_mw"]) * 1000
        src_p = "fiche : puissance MW × 1000"
    else:
        src_p = "demande ou fiche"
    opt = pracc_option(kw)
    note_p = ""
    if kw and kw > LIMITE_HTA_KW:
        note_p = f"{kw / 1000:g} MW : au-delà de 40 MW le raccordement relève de RTE, pas d'Enedis"
    elif opt and kw and opt != "Plus de 20000" and float(opt) != kw:
        note_p = f"{kw:g} kW arrondis à {opt}, valeur de la liste du portail"
    act(2, "Puissance de raccordement (Pracc), kW", "liste", "puissanceRacc", opt, source=src_p, note=note_p, bloquant=bool(kw and kw > LIMITE_HTA_KW))
    act(2, "Rampe sur 10 ans", "radio", "RampeSur10ans", "false", source="défaut", libelle="Non",
        note=("montée en charge dans la fiche : la rampe Enedis se déclare en 4 paliers de 2 à 3 ans (10 ans au total), à saisir à la main si voulue"
              if fi.get("montee_en_charge") else ""))
    try:
        n_alim = int(float(fi.get("alimentations_secours") or 0))
    except ValueError:
        n_alim = 0
    act(2, "Alimentation de secours", "radio", "AlimSecours", "true" if n_alim else "false", source="fiche : alimentations supplémentaires",
        libelle="Oui" if n_alim else "Non")
    if n_alim:
        act(2, "Puissance de l'alimentation de secours, kW", "texte", "htaPuissanceAlimSecours", str(int(kw)) if kw else None,
            source="Pracc", note="même puissance que l'alimentation principale")
    act(2, "Présence d'autoproduction", "radio", "Autoproduction", "false", source="fixe", libelle="Non")
    secours = str(fi.get("production_secours") or "").strip().lower()
    ge = True if secours in ("oui", "o", "true", "1") else (False if secours in ("non", "n", "false", "0") else None)
    act(2, "Groupes électrogènes", "radio", "GroupesElectrogenesPrevus", None if ge is None else ("true" if ge else "false"),
        source="fiche : production de secours", libelle=None if ge is None else ("Oui" if ge else "Non"))
    if ge:
        n_g, p_g = groupes(fi.get("secours_groupes") or "")
        valeur_n = None if n_g is None else ("1" if n_g == 1 else "2" if n_g == 2 else "Plus de 2")
        act(2, "Nombre de groupes", "radio", "NombreGroupesElectrogenesPrevus", valeur_n, source="fiche : groupes de secours",
            note="écrire « 40 groupes de 3 MW » dans la fiche" if n_g is None else "", libelle=valeur_n)
        if n_g and n_g > 2:
            act(2, "Nombre de groupes électrogènes", "texte", "nombreGroupesElectro", str(n_g), source="fiche")
            act(2, "Puissance totale des groupes, kW", "texte", "PuissanceTotaleGroupesElectro", str(p_g), source="fiche")
        act(2, "Mode de couplage des groupes", "radio", "ModeCouplageGroupesElec", "Normal / Secours", source="défaut",
            note="secours sans couplage permanent au réseau")
    act(2, "Qualité d'alimentation", "radio", "QualiteAlim", "Seuil standard", source="fixe")

    # ---------------------------------------------------------------- 3 DOCUMENTS
    ec = pieces.get("extrait_cadastral")
    act(3, "Extrait de plan cadastral", "fichier", "PlanCadastral", ec["nom"] if ec else None, source="pièce de la demande", piece=ec,
        note="obligatoire ; « Récupérer l'extrait cadastral » sur la demande")
    sec, num_p = _premiere_parcelle(fi.get("parcelles") or "")
    act(3, "Numéro de section", "texte", "Numero de section", sec or None, requis=False, source="fiche : première parcelle")
    act(3, "Numéro de parcelle", "texte", "Numéro de parcelle", num_p or None, requis=False, source="fiche : première parcelle")
    ps = pieces.get("plan_situation")
    act(3, "Plan de situation", "fichier", "PlanSituation", ps["nom"] if ps else None, requis=False, source="pièce de la demande", piece=ps,
        note="facultatif, 1/25 000 ou 1/10 000")
    pm = pieces.get("plan_masse") or pieces.get("plan_implantation")
    act(3, "Plan de masse", "fichier", "PlanMasse", pm["nom"] if pm else None, source="pièce de la demande", piece=pm,
        note="obligatoire : emplacement du poste de livraison, accessible 24 h/24 sans accès contrôlé")
    ph = pieces.get("photo_environnement")
    act(3, "Photographie de l'environnement", "fichier", "PhotoEnvironnementProjet", ph["nom"] if ph else None, requis=False,
        source="pièce de la demande", piece=ph)
    act(3, "Autorisation d'urbanisme nécessaire", "radio", "AutorisationUrbanismeRequired", "true", source="fixe", libelle="Oui",
        note="un datacenter demande un permis de construire")
    pc = pieces.get("permis")
    act(3, "Copie de l'autorisation d'urbanisme", "fichier", "AutorisationUrbanismeFile", pc["nom"] if pc else None, requis=False,
        source="pièce de la demande", piece=pc, note="" if pc else "pas de permis joint : demande anticipée")

    # ---------------------------------------------------------------- 4 ECHEANCE
    d_mes = _date_fr(fi.get("date_mise_a_disposition"))
    note_d = "JJ/MM/AAAA"
    if d_mes and str(fi.get("date_mise_a_disposition"))[:10] <= auj.isoformat():
        d_mes, note_d = None, "date passée : le portail n'accepte qu'une date à partir de demain"
    act(4, "Date souhaitée de mise en service", "date", "date", d_mes, source="fiche : mise à disposition souhaitée", note=note_d)
    chantier = type_enedis == "chantier" or fi.get("puissance_chantier_kva") not in (None, "")
    act(4, "Branchement provisoire le temps de la construction", "radio", "RaccProvisoire", "true" if chantier else "false",
        source="fiche : puissance de chantier" if chantier else "défaut", libelle="Oui" if chantier else "Non",
        note=(f"chantier : {fi.get('puissance_chantier_kva')} kVA, à préciser dans la demande particulière"
              if fi.get("puissance_chantier_kva") not in (None, "") else
              "renseigner la puissance de chantier dans la fiche pour demander le branchement provisoire"))
    ctx = fi.get("contexte") or ""
    if chantier and fi.get("puissance_chantier_kva") not in (None, ""):
        debut = f" à partir du {_date_fr(fi.get('date_debut_chantier'))}" if fi.get("date_debut_chantier") else ""
        ctx = (ctx + "\n\n" if ctx else "") + (f"Branchement provisoire de chantier : {fi['puissance_chantier_kva']} kVA{debut}.")
    act(4, "Demande particulière éventuelle", "texte", "Commentaires", ctx or None, requis=False, source="fiche : contexte et chantier")

    sortie = [{"numero": n, "titre": TITRES[n], "actions": etapes[n]} for n in range(1, 5)]
    sortie[-1]["arret"] = ("Le robot s'arrête sur l'étape Échéance sans cliquer « Suivant ». À vous : relire les 4 étapes, "
                           "poursuivre vers le récapitulatif et envoyer, puis passer la demande à « Déposé » dans Amont.")
    manquants = [f"{TITRES[e['numero']]} : {a['question']}" for e in sortie for a in e["actions"] if a["manque"]]
    if not accueil["commune"]:
        manquants.insert(0, "accueil : commune du site")
    alertes = [f"{TITRES[e['numero']]} : {a['question']} : {a['note']}" for e in sortie for a in e["actions"]
               if a.get("bloquant") or "passée" in (a.get("note") or "") or "arrondis" in (a.get("note") or "")]
    return {"demande": payload.get("id"), "projet": payload.get("projet_code"), "url": URL_ENEDIS, "accueil": accueil,
            "etapes": sortie, "manquants": manquants, "alertes": alertes, "pret": not manquants and not any(a.get("bloquant") for e in sortie for a in e["actions"]),
            "type_enedis": type_enedis}
