"""Stockage d'Amont : base SQLite. Registre des demandes (projets, demandes, pieces, journal,
notifications) et, depuis le 07/10/2026, sources et fiche identite des sites (sources, fiche,
propositions). Un site est un projet : meme code, meme ligne dans la table projets.
Depuis le 26/10/2026 (0.3) : suivi des dossiers et des courriels (contacts, echanges,
filieres sans objet, prochaine action saisie a la main). 0.4 : commentaires et points a faire
verifier (par projet, par demande ou par champ de la fiche), documents et liens par etape.

Les demandes ont des colonnes fixes (communes a toutes les filieres) et une colonne JSON
"donnees" pour les champs propres a la filiere. Vers l'exterieur, une demande circule
toujours aplatie : un seul dict, colonnes et donnees confondues.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

from . import fiche as fiche_site
from . import regles
from . import ressources as ressources_defaut

COLONNES_DEMANDE = [
    "id", "projet_code", "filiere", "statut", "site", "commune", "departement",
    "date_depot", "interlocuteur", "notes", "prochaine_action",
]
COLONNES_PROJET = [
    "code", "nom", "commune", "departement", "lat", "lon", "puissance_cible_mw",
    "statut_projet", "notes",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS projets (
    code TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    commune TEXT, departement TEXT, lat REAL, lon REAL,
    puissance_cible_mw REAL,
    statut_projet TEXT DEFAULT 'en_etude',
    notes TEXT DEFAULT '',
    cree_le TEXT, modifie_le TEXT
);
CREATE TABLE IF NOT EXISTS demandes (
    id TEXT PRIMARY KEY,
    projet_code TEXT NOT NULL REFERENCES projets(code),
    filiere TEXT NOT NULL,
    statut TEXT NOT NULL DEFAULT 'brouillon',
    site TEXT, commune TEXT, departement TEXT,
    date_depot TEXT, interlocuteur TEXT, notes TEXT DEFAULT '',
    donnees TEXT DEFAULT '{}',
    cree_le TEXT, modifie_le TEXT, modifie_par TEXT
);
CREATE TABLE IF NOT EXISTS pieces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demande_id TEXT NOT NULL REFERENCES demandes(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    nom_fichier TEXT NOT NULL,
    chemin TEXT NOT NULL,
    taille_octets INTEGER,
    ajoute_le TEXT, ajoute_par TEXT
);
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demande_id TEXT,
    horodatage TEXT NOT NULL,
    auteur TEXT,
    champ TEXT NOT NULL,
    avant TEXT, apres TEXT,
    origine TEXT DEFAULT 'dashboard'
);
CREATE TABLE IF NOT EXISTS notifications (
    demande_id TEXT NOT NULL,
    cle TEXT NOT NULL,
    severite TEXT,
    dernier_envoi TEXT,
    PRIMARY KEY (demande_id, cle)
);
CREATE INDEX IF NOT EXISTS journal_demande ON journal(demande_id, horodatage);
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_code TEXT NOT NULL REFERENCES projets(code) ON DELETE CASCADE,
    nom_fichier TEXT NOT NULL,
    chemin TEXT NOT NULL,
    taille_octets INTEGER,
    type_source TEXT DEFAULT 'autre',
    statut TEXT DEFAULT 'en_attente',
    methode TEXT, nb_caracteres INTEGER, nb_propositions INTEGER DEFAULT 0,
    erreur TEXT, extrait_le TEXT,
    ajoute_le TEXT, ajoute_par TEXT
);
CREATE TABLE IF NOT EXISTS fiche (
    projet_code TEXT NOT NULL REFERENCES projets(code) ON DELETE CASCADE,
    champ TEXT NOT NULL,
    valeur TEXT,
    origine TEXT,
    source_id INTEGER,
    extrait TEXT,
    valide INTEGER DEFAULT 0,
    modifie_le TEXT, modifie_par TEXT,
    PRIMARY KEY (projet_code, champ)
);
CREATE TABLE IF NOT EXISTS propositions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_code TEXT NOT NULL REFERENCES projets(code) ON DELETE CASCADE,
    champ TEXT NOT NULL,
    valeur TEXT NOT NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    extrait TEXT, confiance REAL, methode TEXT,
    statut TEXT DEFAULT 'en_attente',
    cree_le TEXT
);
CREATE INDEX IF NOT EXISTS propositions_projet ON propositions(projet_code, statut);
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    organisation TEXT, role TEXT, email TEXT, telephone TEXT, filiere TEXT,
    notes TEXT DEFAULT '',
    cree_le TEXT, modifie_le TEXT
);
CREATE TABLE IF NOT EXISTS echanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_code TEXT NOT NULL REFERENCES projets(code) ON DELETE CASCADE,
    demande_id TEXT REFERENCES demandes(id) ON DELETE SET NULL,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    date TEXT NOT NULL,
    sens TEXT NOT NULL,
    canal TEXT DEFAULT 'mail',
    expediteur TEXT, destinataires TEXT, objet TEXT, resume TEXT,
    attend_reponse INTEGER DEFAULT 0,
    relance_le TEXT, repondu_le TEXT,
    fichier TEXT, nom_fichier TEXT,
    message_id TEXT,
    origine TEXT DEFAULT 'manuel',
    cree_le TEXT, cree_par TEXT
);
CREATE INDEX IF NOT EXISTS echanges_demande ON echanges(demande_id, date);
CREATE INDEX IF NOT EXISTS echanges_projet ON echanges(projet_code, date);
CREATE UNIQUE INDEX IF NOT EXISTS echanges_message ON echanges(message_id) WHERE message_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS commentaires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_code TEXT NOT NULL REFERENCES projets(code) ON DELETE CASCADE,
    demande_id TEXT REFERENCES demandes(id) ON DELETE SET NULL,
    cible TEXT,
    texte TEXT NOT NULL,
    a_verifier INTEGER DEFAULT 0,
    statut TEXT DEFAULT 'ouvert',
    reponse TEXT,
    auteur TEXT, cree_le TEXT,
    traite_par TEXT, traite_le TEXT
);
CREATE INDEX IF NOT EXISTS commentaires_projet ON commentaires(projet_code, cree_le);
CREATE TABLE IF NOT EXISTS ressources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filiere TEXT NOT NULL,
    etape TEXT DEFAULT '',
    type TEXT DEFAULT 'formulaire',
    libelle TEXT NOT NULL,
    url TEXT, notes TEXT DEFAULT '',
    fichier TEXT, nom_fichier TEXT,
    verifie_le TEXT, ordre INTEGER DEFAULT 0,
    cree_le TEXT, modifie_le TEXT
);
CREATE TABLE IF NOT EXISTS parametres (
    cle TEXT PRIMARY KEY,
    valeur TEXT
);
CREATE TABLE IF NOT EXISTS filieres_projet (
    projet_code TEXT NOT NULL REFERENCES projets(code) ON DELETE CASCADE,
    filiere TEXT NOT NULL,
    etat TEXT NOT NULL,
    motif TEXT DEFAULT '',
    modifie_le TEXT,
    PRIMARY KEY (projet_code, filiere)
);
"""

COLONNES_RESSOURCE = ["filiere", "etape", "type", "libelle", "url", "notes", "verifie_le", "ordre"]

SCHEMA_07 = """
CREATE TABLE IF NOT EXISTS validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demande_id TEXT NOT NULL REFERENCES demandes(id) ON DELETE CASCADE,
    statut TEXT NOT NULL,
    empreinte TEXT,
    demande_par TEXT, demande_le TEXT, message TEXT,
    traite_par TEXT, traite_le TEXT, commentaire TEXT,
    commentaire_id INTEGER
);
CREATE INDEX IF NOT EXISTS validations_demande ON validations(demande_id, id);
CREATE TABLE IF NOT EXISTS taches_robot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demande_id TEXT NOT NULL REFERENCES demandes(id) ON DELETE CASCADE,
    robot TEXT NOT NULL DEFAULT 'd1',
    mode TEXT NOT NULL,
    jusqua INTEGER DEFAULT 5,
    statut TEXT NOT NULL DEFAULT 'en_attente',
    demandee_par TEXT, demandee_le TEXT,
    agent TEXT, prise_le TEXT, fin_le TEXT,
    journal TEXT DEFAULT '',
    resultat TEXT
);
CREATE INDEX IF NOT EXISTS taches_robot_statut ON taches_robot(statut, id);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    demande_id TEXT NOT NULL REFERENCES demandes(id) ON DELETE CASCADE,
    piece_id INTEGER REFERENCES pieces(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    donnees TEXT NOT NULL,
    cree_le TEXT, cree_par TEXT,
    reportee_le TEXT, reportee_par TEXT, solution_reportee INTEGER
);
CREATE TABLE IF NOT EXISTS agents (
    nom TEXT PRIMARY KEY,
    vu_le TEXT, version TEXT, info TEXT
);
"""

COLONNES_ECHANGE = ["projet_code", "demande_id", "contact_id", "date", "sens", "canal", "expediteur",
                    "destinataires", "objet", "resume", "attend_reponse", "relance_le", "repondu_le"]
COLONNES_CONTACT = ["nom", "organisation", "role", "email", "telephone", "filiere", "notes"]


def maintenant() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


class Registre:
    """Acces a la base. Une instance par processus, connexion partagee (check_same_thread off)."""

    def __init__(self, chemin: str | Path):
        self.chemin = Path(chemin)
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.cx.execute("PRAGMA journal_mode = WAL")
        self.cx.executescript(SCHEMA)
        self.cx.executescript(SCHEMA_07)
        self._migrer()
        self.verrou = threading.RLock()  # extractions en tache de fond
        regles.appliquer_optionnelles(self.filieres_optionnelles())

    @property
    def cx(self) -> sqlite3.Connection:
        """Une connexion par thread : FastAPI sert les routes en parallele (pool de threads),
        une connexion partagee melange les curseurs des requetes simultanees."""
        c = getattr(self._local, "cx", None)
        if c is None:
            c = sqlite3.connect(str(self.chemin), timeout=15)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            self._local.cx = c
        return c

    def _migrer(self) -> None:
        """Colonnes ajoutees apres coup sur une base existante."""
        cols = {r["name"] for r in self.cx.execute("PRAGMA table_info(demandes)")}
        if "prochaine_action" not in cols:
            self.cx.execute("ALTER TABLE demandes ADD COLUMN prochaine_action TEXT")
            self.cx.commit()
        if not self.cx.execute("SELECT 1 FROM ressources LIMIT 1").fetchone():
            t = maintenant()
            for i, (f, e, ty, lib, url, notes, verif) in enumerate(ressources_defaut.DEFAUT):
                self.cx.execute("INSERT INTO ressources (filiere, etape, type, libelle, url, notes, verifie_le, ordre, cree_le, modifie_le)"
                                " VALUES (?,?,?,?,?,?,?,?,?,?)", (f, e, ty, lib, url, notes, verif or None, i, t, t))
            self.cx.commit()

    # ------------------------------------------------------------------ projets
    def lister_projets(self) -> list[dict]:
        rows = self.cx.execute("SELECT * FROM projets ORDER BY nom").fetchall()
        return [dict(r) for r in rows]

    def obtenir_projet(self, code: str) -> dict | None:
        r = self.cx.execute("SELECT * FROM projets WHERE code = ?", (code,)).fetchone()
        return dict(r) if r else None

    def creer_projet(self, p: dict, auteur: str = "") -> dict:
        code = _code(p.get("code") or p.get("nom") or "")
        if not code:
            raise ValueError("code de projet vide")
        if self.obtenir_projet(code):
            raise ValueError(f"le projet {code} existe déjà")
        t = maintenant()
        self.cx.execute(
            "INSERT INTO projets (code, nom, commune, departement, lat, lon, puissance_cible_mw, statut_projet, notes, cree_le, modifie_le)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (code, p.get("nom") or code, p.get("commune"), p.get("departement"), p.get("lat"), p.get("lon"),
             p.get("puissance_cible_mw"), p.get("statut_projet") or "en_etude", p.get("notes") or "", t, t),
        )
        self._journal(None, auteur, "projet", "", f"création du projet {code}", "dashboard")
        self.cx.commit()
        self.initialiser_fiche(code, auteur)
        return self.obtenir_projet(code)

    def modifier_projet(self, code: str, champs: dict, auteur: str = "") -> dict:
        p = self.obtenir_projet(code)
        if not p:
            raise KeyError(code)
        modifs = {k: v for k, v in champs.items() if k in COLONNES_PROJET and k != "code" and p.get(k) != v}
        if modifs:
            sets = ", ".join(f"{k} = ?" for k in modifs)
            self.cx.execute(f"UPDATE projets SET {sets}, modifie_le = ? WHERE code = ?", (*modifs.values(), maintenant(), code))
            for k, v in modifs.items():
                self._journal(None, auteur, f"projet {code} : {k}", p.get(k), v, "dashboard")
            self.cx.commit()
        return self.obtenir_projet(code)

    def synthese_projet(self, code: str) -> dict:
        """Projet + une entree par filiere (demande ou None), pour la matrice et la fiche projet."""
        p = self.obtenir_projet(code)
        if not p:
            raise KeyError(code)
        demandes = self.lister_demandes(projet=code)
        p["demandes"] = demandes
        p["par_filiere"] = {f: [d for d in demandes if d["filiere"] == f] for f in regles.ORDRE_FILIERES}
        p["filieres_etat"] = self.filieres_etat(code)
        p["echanges_resume"] = self.resume_echanges(projet=code)
        p["a_verifier"] = self.cx.execute("SELECT COUNT(*) FROM commentaires WHERE projet_code = ? AND a_verifier = 1 AND statut = 'ouvert'",
                                          (code,)).fetchone()[0]
        return p

    # ----------------------------------------------------------------- demandes
    def _aplatir(self, r: sqlite3.Row) -> dict:
        d = dict(r)
        donnees = json.loads(d.pop("donnees") or "{}")
        d.update(donnees)
        d["projet"] = d["projet_code"]
        return d

    def _enrichir(self, d: dict) -> dict:
        d["echeances"] = regles.echeances(d)
        d["prochaine_echeance"] = regles.prochaine_echeance(d)
        d["alertes"] = regles.alertes(d)
        d["libelle_statut"] = regles.libelle_statut(d["filiere"], d["statut"])
        d["dimension"] = regles.dimension(d)
        if d["filiere"] in ("rte_ee", "rte_ptf"):
            d["domaine"] = regles.article_105(regles._nombre(d.get("puissance_mw")) or None, regles._nombre(d.get("d_km")) or None)
        resume = self.resume_echanges(demande=d["id"])
        d["echanges_resume"] = resume
        attente = resume["attente"]
        if attente:
            if attente["jours"] >= regles.DELAI_RELANCE_JOURS:
                d["alertes"].append({"severite": "warn", "cle": f"attente-{attente['id']}",
                                     "texte": f"Sans réponse depuis {attente['jours']} jours : {attente['objet'] or 'courriel'}"
                                              + (f" ({attente['contact']})" if attente.get("contact") else "")})
            if attente.get("relance_le") and attente["relance_le"] <= date.today().isoformat():
                d["alertes"].append({"severite": "warn", "cle": f"relance-{attente['id']}",
                                     "texte": f"Relance prévue le {attente['relance_le']} : {attente['objet'] or 'courriel'}"})
        manquantes = self.pieces_manquantes(d["id"], d["filiere"]) if d["statut"] in ("brouillon", "irrecevable") else []
        d["validation"] = self.etat_validation(d)
        v = d["validation"]
        if regles.VALIDATION_REQUISE and d["statut"] in regles.ETAPES_AVANT_ENVOI:
            if v["etat"] == "demandee":
                d["alertes"].append({"severite": "warn", "cle": f"validation-{v['id']}",
                                     "texte": f"Validation demandée par {v['demande_par']} le {v['demande_le'][:10]}, en attente du responsable"})
            elif v["etat"] == "perimee":
                d["alertes"].append({"severite": "warn", "cle": f"perimee-{v['id']}",
                                     "texte": "Dossier modifié depuis la validation du " + (v["traite_le"] or "")[:10] + " : à revalider"})
        d["action"] = regles.prochaine_action(d, manquantes, attente, validation=v)
        return d

    def lister_demandes(self, filiere: str | None = None, projet: str | None = None, statut: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM demandes WHERE 1=1", []
        if filiere:
            q += " AND filiere = ?"; args.append(filiere)
        if projet:
            q += " AND projet_code = ?"; args.append(projet)
        if statut:
            q += " AND statut = ?"; args.append(statut)
        q += " ORDER BY projet_code, filiere, id"
        rows = self.cx.execute(q, args).fetchall()
        out = [self._enrichir(self._aplatir(r)) for r in rows]
        ordre = {f: i for i, f in enumerate(regles.ORDRE_FILIERES)}
        out.sort(key=lambda d: (d["projet_code"], ordre.get(d["filiere"], 9), d["id"]))
        return out

    def obtenir_demande(self, id_: str) -> dict | None:
        r = self.cx.execute("SELECT * FROM demandes WHERE id = ?", (id_,)).fetchone()
        if not r:
            return None
        d = self._enrichir(self._aplatir(r))
        d["pieces"] = self.lister_pieces(id_)
        d["journal"] = self.journal(demande_id=id_, limite=100)
        d["analyses"] = self.lister_analyses(id_)
        return d

    def creer_demande(self, d: dict, auteur: str = "", origine: str = "dashboard") -> dict:
        id_ = _code(d.get("id") or "")
        if not id_:
            raise ValueError("code de demande vide")
        if self.obtenir_demande(id_):
            raise ValueError(f"la demande {id_} existe déjà")
        projet = self.obtenir_projet(d.get("projet_code") or d.get("projet") or "")
        if not projet:
            raise ValueError("projet inconnu")
        filiere = regles.filiere_valide(d.get("filiere"))
        statut = d.get("statut") or "brouillon"
        if statut not in regles.statuts_de(filiere):
            raise ValueError(f"statut {statut} inconnu pour la filière {filiere}")
        depuis_fiche = fiche_site.vers_demande(filiere, self.valeurs_fiche(projet["code"]))
        d = {**depuis_fiche, **{k: v for k, v in d.items() if v not in (None, "")}}
        donnees = {k: d[k] for k in regles.CHAMPS_FILIERE[filiere] if k in d and d[k] not in (None, "")}
        if filiere == "enedis" and "type_enedis" not in donnees:
            donnees["type_enedis"] = "hta"
        t = maintenant()
        self.cx.execute(
            "INSERT INTO demandes (id, projet_code, filiere, statut, site, commune, departement, date_depot, interlocuteur, notes, donnees, cree_le, modifie_le, modifie_par)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (id_, projet["code"], filiere, statut, d.get("site") or "",
             d.get("commune") or projet.get("commune") or "", d.get("departement") or projet.get("departement") or "",
             d.get("date_depot") or None, d.get("interlocuteur") or "", d.get("notes") or "",
             json.dumps(donnees, ensure_ascii=False), t, t, auteur),
        )
        self._journal(id_, auteur, "création", "", statut, origine)
        self.cx.commit()
        return self.obtenir_demande(id_)

    def modifier_demande(self, id_: str, champs: dict, auteur: str = "", origine: str = "dashboard") -> dict:
        r = self.cx.execute("SELECT * FROM demandes WHERE id = ?", (id_,)).fetchone()
        if not r:
            raise KeyError(id_)
        actuel = self._aplatir(r)
        filiere = actuel["filiere"]
        donnees = json.loads(r["donnees"] or "{}")
        colonnes: dict = {}
        journal: list[tuple] = []

        for k, v in champs.items():
            if k in ("id", "projet_code", "projet", "filiere", "cree_le", "modifie_le", "modifie_par"):
                continue
            if v == "":
                v = None
            if k == "statut":
                if v not in regles.statuts_de(filiere):
                    raise ValueError(f"statut {v} inconnu pour la filière {filiere}")
                if v == "depose" and actuel.get("statut") != "depose":
                    manquantes = self.pieces_manquantes(id_, filiere)
                    if manquantes:
                        raise ValueError("passage à « déposé » refusé, pièce obligatoire manquante : " + ", ".join(manquantes))
                    if regles.VALIDATION_REQUISE:
                        ev = self.etat_validation(actuel)
                        if ev["etat"] != "validee":
                            raise ValueError("passage à « déposé » refusé : validation du responsable "
                                             + {"perimee": "périmée, le dossier a changé depuis", "demandee": "en attente",
                                                "refusee": "refusée"}.get(ev["etat"], "absente"))
            if k in COLONNES_DEMANDE:
                if actuel.get(k) != v:
                    colonnes[k] = v
                    journal.append((k, actuel.get(k), v))
            elif k in regles.CHAMPS_FILIERE[filiere]:
                if donnees.get(k) != v:
                    if v is None:
                        donnees.pop(k, None)
                    else:
                        donnees[k] = v
                    journal.append((k, actuel.get(k), v))
            # champ inconnu pour cette filiere : ignore silencieusement

        if not journal:
            return self.obtenir_demande(id_)
        colonnes["donnees"] = json.dumps(donnees, ensure_ascii=False)
        sets = ", ".join(f"{k} = ?" for k in colonnes)
        self.cx.execute(
            f"UPDATE demandes SET {sets}, modifie_le = ?, modifie_par = ? WHERE id = ?",
            (*colonnes.values(), maintenant(), auteur, id_),
        )
        for k, avant, apres in journal:
            self._journal(id_, auteur, k, avant, apres, origine)
        self.cx.commit()
        return self.obtenir_demande(id_)

    def supprimer_demande(self, id_: str, auteur: str = "") -> None:
        self.cx.execute("DELETE FROM demandes WHERE id = ?", (id_,))
        self._journal(id_, auteur, "suppression", "", "", "dashboard")
        self.cx.commit()

    def payload(self, id_: str) -> dict:
        """Donnees pretes pour un robot ou un generateur : demande aplatie + projet, sans les calculs."""
        d = self.obtenir_demande(id_)
        if not d:
            raise KeyError(id_)
        p = self.obtenir_projet(d["projet_code"]) or {}
        exclus = {"echeances", "prochaine_echeance", "alertes", "journal", "libelle_statut", "dimension", "echanges_resume", "action",
                  "commentaires", "ressources", "analyses"}
        payload = {k: v for k, v in d.items() if k not in exclus}
        payload["projet_detail"] = p
        payload["fiche"] = self.valeurs_fiche(d["projet_code"])
        payload["fiche_completude"] = fiche_site.completude(self.fiche(d["projet_code"]), [d["filiere"]])[d["filiere"]]
        payload["pieces_manquantes"] = self.pieces_manquantes(id_, d["filiere"])
        return payload


    # ------------------------------------------------------------------ fiche
    def fiche(self, code: str) -> dict:
        """{champ: {valeur, origine, source_id, source, extrait, valide, modifie_le, modifie_par}}."""
        rows = self.cx.execute(
            "SELECT f.*, s.nom_fichier AS source FROM fiche f LEFT JOIN sources s ON s.id = f.source_id WHERE f.projet_code = ?",
            (code,)).fetchall()
        out = {}
        for r in rows:
            d = dict(r)
            d["valide"] = bool(d["valide"])
            d["valeur"] = fiche_site.valeur_typee(d["champ"], d["valeur"])
            out[d.pop("champ")] = d
        return out

    def valeurs_fiche(self, code: str) -> dict:
        return {k: v["valeur"] for k, v in self.fiche(code).items() if v["valeur"] not in (None, "")}

    def initialiser_fiche(self, code: str, auteur: str = "") -> None:
        """Valeurs par defaut de la societe et reprise des champs du projet, sur les champs vides seulement."""
        p = self.obtenir_projet(code) or {}
        actuel = self.fiche(code)
        a_poser = dict(fiche_site.demandeur_defaut())
        for k_projet, k_fiche in (("nom", "nom_installation"), ("commune", "commune"), ("departement", "departement"),
                                  ("lat", "lat"), ("lon", "lon"), ("puissance_cible_mw", "puissance_mw")):
            if p.get(k_projet) not in (None, ""):
                a_poser[k_fiche] = p[k_projet]
        with self.verrou:
            for k, v in a_poser.items():
                if k in actuel:
                    continue
                origine = "societe" if k in fiche_site.DEMANDEUR_DEFAUT else "projet"
                self._ecrire_fiche(code, k, v, origine, None, "", origine == "societe", auteur)
            self.cx.commit()

    def _ecrire_fiche(self, code, champ, valeur, origine, source_id, extrait, valide, auteur) -> bool:
        v = fiche_site.normaliser(champ, valeur)
        r = self.cx.execute("SELECT valeur, valide FROM fiche WHERE projet_code = ? AND champ = ?", (code, champ)).fetchone()
        if r and r["valeur"] == v and bool(r["valide"]) == bool(valide):
            return False
        self.cx.execute(
            "INSERT INTO fiche (projet_code, champ, valeur, origine, source_id, extrait, valide, modifie_le, modifie_par)"
            " VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(projet_code, champ) DO UPDATE SET valeur = excluded.valeur,"
            " origine = excluded.origine, source_id = excluded.source_id, extrait = excluded.extrait,"
            " valide = excluded.valide, modifie_le = excluded.modifie_le, modifie_par = excluded.modifie_par",
            (code, champ, v, origine, source_id, extrait, 1 if valide else 0, maintenant(), auteur or "interne"))
        if not r or r["valeur"] != v:
            self._journal(None, auteur, f"fiche {code} : {champ}", r["valeur"] if r else "", v, origine)
        return True

    def modifier_fiche(self, code: str, champs: dict, auteur: str = "") -> dict:
        """Saisie manuelle : la valeur est validee d'office. Les propositions en attente du champ sont ecartees."""
        if not self.obtenir_projet(code):
            raise KeyError(code)
        with self.verrou:
            actuel = self.fiche(code)
            for k, v in champs.items():
                if k not in fiche_site.CLES:
                    continue
                v = fiche_site.normaliser(k, v)
                avant = actuel.get(k) or {}
                avant_v = fiche_site.normaliser(k, avant.get("valeur"))
                if v == avant_v:
                    continue
                if v is None:
                    self.cx.execute("DELETE FROM fiche WHERE projet_code = ? AND champ = ?", (code, k))
                    self._journal(None, auteur, f"fiche {code} : {k}", avant_v, "", "dashboard")
                else:
                    self._ecrire_fiche(code, k, v, "manuel", None, "", True, auteur)
                self.cx.execute("UPDATE propositions SET statut = 'ecartee' WHERE projet_code = ? AND champ = ? AND statut = 'en_attente'", (code, k))
            self.cx.commit()
        self._fiche_vers_projet(code, auteur)
        return self.obtenir_site(code)

    def _fiche_vers_projet(self, code: str, auteur: str = "") -> None:
        """Les colonnes de synthese du projet suivent la fiche (nom, commune, departement, GPS, puissance)."""
        v = self.valeurs_fiche(code)
        champs = {k_projet: v[k_fiche] for k_projet, k_fiche in (
            ("commune", "commune"), ("departement", "departement"), ("lat", "lat"), ("lon", "lon"),
            ("puissance_cible_mw", "puissance_mw")) if v.get(k_fiche) not in (None, "")}
        if champs:
            self.modifier_projet(code, champs, auteur)

    def valider_champs(self, code: str, champs: list[str], auteur: str = "") -> dict:
        with self.verrou:
            for k in champs:
                r = self.cx.execute("UPDATE fiche SET valide = 1, modifie_le = ?, modifie_par = ? WHERE projet_code = ? AND champ = ? AND valide = 0",
                                    (maintenant(), auteur or "interne", code, k))
                if r.rowcount:
                    self._journal(None, auteur, f"fiche {code} : {k}", "", "validé", "dashboard")
            self.cx.commit()
        self._fiche_vers_projet(code, auteur)
        return self.obtenir_site(code)

    def accepter_proposition(self, prop_id: int, auteur: str = "") -> dict:
        with self.verrou:
            r = self.cx.execute("SELECT * FROM propositions WHERE id = ?", (prop_id,)).fetchone()
            if not r:
                raise KeyError(prop_id)
            self._ecrire_fiche(r["projet_code"], r["champ"], r["valeur"], "extraction", r["source_id"], r["extrait"], True, auteur)
            self.cx.execute("UPDATE propositions SET statut = 'acceptee' WHERE id = ?", (prop_id,))
            self.cx.execute("UPDATE propositions SET statut = 'ecartee' WHERE projet_code = ? AND champ = ? AND statut = 'en_attente'",
                            (r["projet_code"], r["champ"]))
            self.cx.commit()
        self._fiche_vers_projet(r["projet_code"], auteur)
        return self.obtenir_site(r["projet_code"])

    def rejeter_proposition(self, prop_id: int, auteur: str = "") -> dict:
        with self.verrou:
            r = self.cx.execute("SELECT * FROM propositions WHERE id = ?", (prop_id,)).fetchone()
            if not r:
                raise KeyError(prop_id)
            self.cx.execute("UPDATE propositions SET statut = 'rejetee' WHERE id = ?", (prop_id,))
            self.cx.commit()
        return self.obtenir_site(r["projet_code"])

    def importer_fiche(self, code: str, valeurs: dict, origine: str = "import", auteur: str = "", ecraser: bool = False) -> dict:
        """Entree directe d'un autre programme (ex. DatacenterSiteAnalyzer). Valeurs a verifier, champs vides
        remplis, champs deja remplis laisses en proposition sauf ecraser=True."""
        if not self.obtenir_projet(code):
            raise KeyError(code)
        props = [{"champ": k, "valeur": v, "extrait": f"import {origine}", "confiance": 0.8}
                 for k, v in valeurs.items() if k in fiche_site.CLES]
        return self._appliquer_propositions(code, None, props, origine, auteur, ecraser)

    def _appliquer_propositions(self, code, source_id, props, methode, auteur, ecraser=False) -> dict:
        """Champ vide : rempli, a verifier. Meme valeur : rien. Valeur differente : proposition en attente."""
        n_rempli = n_attente = 0
        with self.verrou:
            actuel = self.fiche(code)
            for p in props:
                k = p["champ"]
                v = fiche_site.normaliser(k, p["valeur"])
                if v is None:
                    continue
                a = actuel.get(k)
                a_v = fiche_site.normaliser(k, a.get("valeur")) if a else None
                if a_v == v:
                    continue
                if a_v is None or (ecraser and not (a or {}).get("valide")):
                    self._ecrire_fiche(code, k, v, "extraction", source_id, p.get("extrait", ""), False, auteur)
                    actuel[k] = {"valeur": v, "valide": False}
                    n_rempli += 1
                    continue
                deja = self.cx.execute("SELECT 1 FROM propositions WHERE projet_code = ? AND champ = ? AND valeur = ? AND statut IN ('en_attente','rejetee')",
                                       (code, k, v)).fetchone()
                if deja:
                    continue
                self.cx.execute(
                    "INSERT INTO propositions (projet_code, champ, valeur, source_id, extrait, confiance, methode, statut, cree_le) VALUES (?,?,?,?,?,?,?,?,?)",
                    (code, k, v, source_id, p.get("extrait", ""), p.get("confiance"), methode, "en_attente", maintenant()))
                n_attente += 1
            self.cx.commit()
        return {"remplis": n_rempli, "en_attente": n_attente}

    # ---------------------------------------------------------------- sources
    def lister_sources(self, code: str) -> list[dict]:
        rows = self.cx.execute("SELECT * FROM sources WHERE projet_code = ? ORDER BY ajoute_le DESC, id DESC", (code,)).fetchall()
        return [dict(r) for r in rows]

    def obtenir_source(self, source_id: int) -> dict | None:
        r = self.cx.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return dict(r) if r else None

    def ajouter_source(self, code: str, nom_fichier: str, chemin: str, taille: int, auteur: str = "") -> dict:
        with self.verrou:
            cur = self.cx.execute(
                "INSERT INTO sources (projet_code, nom_fichier, chemin, taille_octets, statut, ajoute_le, ajoute_par) VALUES (?,?,?,?,?,?,?)",
                (code, nom_fichier, chemin, taille, "en_attente", maintenant(), auteur or "interne"))
            self._journal(None, auteur, f"source {code}", "", nom_fichier, "dashboard")
            self.cx.commit()
        return self.obtenir_source(cur.lastrowid)

    def marquer_source(self, source_id: int, **champs) -> None:
        with self.verrou:
            sets = ", ".join(f"{k} = ?" for k in champs)
            self.cx.execute(f"UPDATE sources SET {sets} WHERE id = ?", (*champs.values(), source_id))
            self.cx.commit()

    def enregistrer_extraction(self, source_id: int, resultat: dict, auteur: str = "") -> dict:
        s = self.obtenir_source(source_id)
        if not s:
            raise KeyError(source_id)
        bilan = self._appliquer_propositions(s["projet_code"], source_id, resultat["propositions"], resultat["methode"], auteur)
        statut = "erreur" if resultat.get("erreur") and not resultat["propositions"] else "fait"
        self.marquer_source(source_id, type_source=resultat["type_source"], statut=statut, methode=resultat["methode"],
                            nb_caracteres=resultat["nb_caracteres"], nb_propositions=len(resultat["propositions"]),
                            erreur=resultat.get("erreur"), extrait_le=maintenant())
        return bilan

    def supprimer_source(self, source_id: int, auteur: str = "") -> dict | None:
        s = self.obtenir_source(source_id)
        if not s:
            return None
        with self.verrou:
            self.cx.execute("DELETE FROM propositions WHERE source_id = ? AND statut = 'en_attente'", (source_id,))
            self.cx.execute("UPDATE fiche SET source_id = NULL WHERE source_id = ?", (source_id,))
            self.cx.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            self._journal(None, auteur, f"source {s['projet_code']} retirée", s["nom_fichier"], "", "dashboard")
            self.cx.commit()
        return s

    # ------------------------------------------------------------------ sites
    def _fiche_initialisee(self, code: str) -> None:
        if not self.cx.execute("SELECT 1 FROM fiche WHERE projet_code = ? LIMIT 1", (code,)).fetchone():
            self.initialiser_fiche(code)

    def obtenir_site(self, code: str) -> dict:
        p = self.obtenir_projet(code)
        if not p:
            raise KeyError(code)
        self._fiche_initialisee(code)
        valeurs = self.fiche(code)
        props = [dict(r) for r in self.cx.execute(
            "SELECT p.*, s.nom_fichier AS source FROM propositions p LEFT JOIN sources s ON s.id = p.source_id"
            " WHERE p.projet_code = ? AND p.statut = 'en_attente' ORDER BY p.champ, p.confiance DESC", (code,)).fetchall()]
        demandes = self.lister_demandes(projet=code)
        return {
            "projet": p,
            "fiche": valeurs,
            "propositions": props,
            "sources": self.lister_sources(code),
            "completude": fiche_site.completude(valeurs, regles.ORDRE_FILIERES),
            "verifications": self.verifications_fiche(code),
            "demandes": {f: [{"id": d["id"], "statut": d["statut"], "libelle_statut": d["libelle_statut"]}
                             for d in demandes if d["filiere"] == f] for f in regles.ORDRE_FILIERES},
        }

    def resume_sites(self) -> list[dict]:
        out = []
        for p in self.lister_projets():
            self._fiche_initialisee(p["code"])
            valeurs = self.fiche(p["code"])
            comp = fiche_site.completude(valeurs, regles.ORDRE_FILIERES)
            n_sources = self.cx.execute("SELECT COUNT(*) FROM sources WHERE projet_code = ?", (p["code"],)).fetchone()[0]
            n_props = self.cx.execute("SELECT COUNT(*) FROM propositions WHERE projet_code = ? AND statut = 'en_attente'", (p["code"],)).fetchone()[0]
            remplis = sum(1 for v in valeurs.values() if v["valeur"] not in (None, ""))
            a_verifier = sum(1 for v in valeurs.values() if v["valeur"] not in (None, "") and not v["valide"])
            out.append({"code": p["code"], "nom": p["nom"], "commune": p.get("commune"), "departement": p.get("departement"),
                        "puissance_cible_mw": p.get("puissance_cible_mw"), "sources": n_sources, "propositions": n_props,
                        "remplis": remplis, "a_verifier": a_verifier, "total": len(fiche_site.CLES),
                        "points_ouverts": self.cx.execute("SELECT COUNT(*) FROM commentaires WHERE projet_code = ? AND a_verifier = 1"
                                                          " AND statut = 'ouvert'", (p["code"],)).fetchone()[0],
                        "completude": {f: {"taux": c["taux"], "pret": c["pret"], "manquants": len(c["manquants"])} for f, c in comp.items()}})
        return out

    def preparer_demandes(self, code: str, filieres: list[str], auteur: str = "") -> list[dict]:
        """Cree les demandes absentes du site pour les filieres demandees, pre-remplies depuis la fiche."""
        p = self.obtenir_projet(code)
        if not p:
            raise KeyError(code)
        existantes = {d["filiere"] for d in self.lister_demandes(projet=code)}
        suffixe = {"rte_ee": "EE", "rte_ptf": "PTF", "enedis": "ENE", "grdf": "GAZ", "natran": "NAT"}
        crees = []
        for f in filieres:
            if f not in regles.ORDRE_FILIERES or f in existantes:
                continue
            id_ = f"{code}-{suffixe.get(f, f.upper())}"
            n = 2
            while self.obtenir_demande(id_):
                id_ = f"{code}-{suffixe.get(f, f.upper())}{n}"
                n += 1
            crees.append(self.creer_demande({"id": id_, "projet_code": code, "filiere": f}, auteur))
        return crees

    def synchroniser_demande(self, id_: str, auteur: str = "") -> dict:
        """Recopie dans une demande les valeurs actuelles de la fiche (champs mappes seulement)."""
        d = self.obtenir_demande(id_)
        if not d:
            raise KeyError(id_)
        champs = fiche_site.vers_demande(d["filiere"], self.valeurs_fiche(d["projet_code"]))
        if d["filiere"] == "enedis" and d.get("type_enedis"):
            champs.pop("type_enedis", None)
        return self.modifier_demande(id_, champs, auteur, "fiche")

    # ------------------------------------------------------------------- pieces
    def lister_pieces(self, demande_id: str) -> list[dict]:
        rows = self.cx.execute("SELECT * FROM pieces WHERE demande_id = ? ORDER BY ajoute_le", (demande_id,)).fetchall()
        return [dict(r) for r in rows]

    def ajouter_piece(self, demande_id: str, type_: str, nom_fichier: str, chemin: str, taille: int, auteur: str = "") -> dict:
        if type_ not in regles.TYPES_PIECES:
            type_ = "autre"
        t = maintenant()
        cur = self.cx.execute(
            "INSERT INTO pieces (demande_id, type, nom_fichier, chemin, taille_octets, ajoute_le, ajoute_par) VALUES (?,?,?,?,?,?,?)",
            (demande_id, type_, nom_fichier, chemin, taille, t, auteur),
        )
        self._journal(demande_id, auteur, "pièce", "", f"{type_} : {nom_fichier}", "dashboard")
        self.cx.commit()
        r = self.cx.execute("SELECT * FROM pieces WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(r)

    def supprimer_piece(self, piece_id: int, auteur: str = "") -> dict | None:
        r = self.cx.execute("SELECT * FROM pieces WHERE id = ?", (piece_id,)).fetchone()
        if not r:
            return None
        self.cx.execute("DELETE FROM pieces WHERE id = ?", (piece_id,))
        self._journal(r["demande_id"], auteur, "pièce retirée", r["nom_fichier"], "", "dashboard")
        self.cx.commit()
        return dict(r)

    def pieces_manquantes(self, demande_id: str, filiere: str) -> list[str]:
        presentes = {p["type"] for p in self.lister_pieces(demande_id)}
        return [t for t in regles.PIECES_OBLIGATOIRES_POUR_DEPOT.get(filiere, []) if t not in presentes]

    # ------------------------------------------------------- filieres optionnelles (NaTran)
    def filieres_optionnelles(self) -> list[str]:
        """Filieres optionnelles actives : le choix fait depuis le site l'emporte sur amont_config.json."""
        r = self.cx.execute("SELECT valeur FROM parametres WHERE cle = 'filieres_optionnelles'").fetchone()
        if r is None:
            return list(regles.CONFIG.get("filieres_optionnelles", []))
        try:
            return [f for f in json.loads(r["valeur"]) if f in regles.FILIERES_OPTIONNELLES]
        except ValueError:
            return []

    def definir_filiere_optionnelle(self, filiere: str, actif: bool, auteur: str = "") -> list[str]:
        if filiere not in regles.FILIERES_OPTIONNELLES:
            raise ValueError(f"filière non optionnelle : {filiere}")
        actives = [f for f in self.filieres_optionnelles() if f != filiere] + ([filiere] if actif else [])
        self.cx.execute("INSERT INTO parametres (cle, valeur) VALUES ('filieres_optionnelles', ?)"
                        " ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur", (json.dumps(actives),))
        self._journal(None, auteur, f"filière {regles.FILIERES[filiere]['court']}", "activée" if not actif else "désactivée",
                      "activée" if actif else "désactivée", "dashboard")
        self.cx.commit()
        return regles.appliquer_optionnelles(actives)

    # ------------------------------------------------------- filieres sans objet
    def filieres_etat(self, code: str) -> dict:
        rows = self.cx.execute("SELECT filiere, etat, motif FROM filieres_projet WHERE projet_code = ?", (code,)).fetchall()
        return {r["filiere"]: {"etat": r["etat"], "motif": r["motif"] or ""} for r in rows}

    def definir_filiere(self, code: str, filiere: str, etat: str | None, motif: str = "", auteur: str = "") -> dict:
        """etat 'sans_objet' : la filiere ne concerne pas ce site (pas de gaz, pas d'Enedis...). None : retour a la normale."""
        if not self.obtenir_projet(code):
            raise KeyError(code)
        if filiere not in regles.FILIERES:
            raise ValueError(f"filière inconnue : {filiere}")
        if etat:
            if etat != "sans_objet":
                raise ValueError(f"état inconnu : {etat}")
            self.cx.execute("INSERT INTO filieres_projet (projet_code, filiere, etat, motif, modifie_le) VALUES (?,?,?,?,?)"
                            " ON CONFLICT(projet_code, filiere) DO UPDATE SET etat = excluded.etat, motif = excluded.motif,"
                            " modifie_le = excluded.modifie_le", (code, filiere, etat, motif or "", maintenant()))
            self._journal(None, auteur, f"projet {code} : {regles.FILIERES[filiere]['court']}", "", "sans objet" + (f" ({motif})" if motif else ""), "dashboard")
        else:
            self.cx.execute("DELETE FROM filieres_projet WHERE projet_code = ? AND filiere = ?", (code, filiere))
            self._journal(None, auteur, f"projet {code} : {regles.FILIERES[filiere]['court']}", "sans objet", "à suivre", "dashboard")
        self.cx.commit()
        return self.filieres_etat(code)

    # ------------------------------------------------- validation a deux cles
    def empreinte(self, d: dict) -> str:
        """Empreinte de ce qui part chez l'operateur : valeurs de la fiche utiles a la filiere, champs de la
        demande (hors dates de suivi) et pieces jointes. Si elle change, la validation est perimee."""
        import hashlib
        fiche_v = self.valeurs_fiche(d["projet_code"])
        cles_fiche = set(fiche_site.REQUIS_PAR_FILIERE.get(d["filiere"], [])) | {"contexte", "complements_techniques",
                                                                                  "puissance_securite_mw", "alimentations_secours"}
        contenu = {
            "fiche": {k: fiche_v.get(k) for k in sorted(cles_fiche) if fiche_v.get(k) not in (None, "")},
            "demande": {k: d.get(k) for k in sorted(regles.CHAMPS_FILIERE.get(d["filiere"], []))
                        if not k.startswith(("date_", "nb_")) and d.get(k) not in (None, "")},
            "site": [d.get("site"), d.get("commune"), d.get("departement")],
            "pieces": sorted((p["type"], p["nom_fichier"], p["taille_octets"]) for p in self.lister_pieces(d["id"])),
        }
        return hashlib.sha256(json.dumps(contenu, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]

    def etat_validation(self, d: dict) -> dict:
        """etat : aucune | demandee | validee | perimee | refusee."""
        r = self.cx.execute("SELECT * FROM validations WHERE demande_id = ? ORDER BY id DESC LIMIT 1", (d["id"],)).fetchone()
        if not r:
            return {"etat": "aucune", "id": None, "requise": regles.VALIDATION_REQUISE, "valideurs": regles.VALIDEURS}
        v = dict(r)
        etat = v["statut"]
        if etat == "validee" and v["empreinte"] != self.empreinte(d):
            etat = "perimee"
        return {**v, "etat": etat, "requise": regles.VALIDATION_REQUISE, "valideurs": regles.VALIDEURS}

    def demander_validation(self, id_: str, message: str = "", auteur: str = "") -> dict:
        d = self.obtenir_demande(id_)
        if not d:
            raise KeyError(id_)
        if d["statut"] not in regles.ETAPES_AVANT_ENVOI:
            raise ValueError("validation inutile : la demande est déjà partie")
        manquantes = self.pieces_manquantes(id_, d["filiere"])
        if manquantes:
            raise ValueError("compléter d'abord les pièces obligatoires : " + ", ".join(manquantes))
        texte = f"Validation demandée avant envoi de {id_} ({regles.FILIERES[d['filiere']]['court']})" + (f" : {message}" if message else "")
        com = self.ajouter_commentaire({"projet_code": d["projet_code"], "demande_id": id_, "texte": texte, "a_verifier": True}, auteur)
        t = maintenant()
        self.cx.execute("INSERT INTO validations (demande_id, statut, empreinte, demande_par, demande_le, message, commentaire_id)"
                        " VALUES (?,?,?,?,?,?,?)", (id_, "demandee", self.empreinte(d), auteur or "interne", t, message, com["id"]))
        self._journal(id_, auteur, "validation", "", "demandée", "dashboard")
        self.cx.commit()
        return self.etat_validation(self.obtenir_demande(id_))

    def traiter_validation(self, id_: str, decision: str, commentaire: str = "", auteur: str = "") -> dict:
        d = self.obtenir_demande(id_)
        if not d:
            raise KeyError(id_)
        if decision not in ("validee", "refusee"):
            raise ValueError("décision inconnue")
        if not regles.peut_valider(auteur):
            raise ValueError(f"« {auteur or 'interne'} » ne fait pas partie des valideurs ({', '.join(regles.VALIDEURS)}) : "
                             "choisir son nom dans la case « Vous » en haut à droite")
        r = self.cx.execute("SELECT * FROM validations WHERE demande_id = ? ORDER BY id DESC LIMIT 1", (id_,)).fetchone()
        if not r or r["statut"] != "demandee":  # validation directe, sans demande en cours
            cur = self.cx.execute("INSERT INTO validations (demande_id, statut, demande_par, demande_le) VALUES (?,?,?,?)",
                                  (id_, "demandee", auteur or "interne", maintenant()))
            r = self.cx.execute("SELECT * FROM validations WHERE id = ?", (cur.lastrowid,)).fetchone()
        t = maintenant()
        self.cx.execute("UPDATE validations SET statut = ?, empreinte = ?, traite_par = ?, traite_le = ?, commentaire = ? WHERE id = ?",
                        (decision, self.empreinte(d), auteur or "interne", t, commentaire, r["id"]))
        if r["commentaire_id"]:
            self.cx.execute("UPDATE commentaires SET statut = 'verifie', reponse = ?, traite_par = ?, traite_le = ? WHERE id = ?",
                            (("Validé" if decision == "validee" else "Refusé") + (f" : {commentaire}" if commentaire else ""),
                             auteur or "interne", t, r["commentaire_id"]))
        self._journal(id_, auteur, "validation", "", ("validée" if decision == "validee" else "refusée")
                      + (f" : {commentaire}" if commentaire else ""), "dashboard")
        self.cx.commit()
        return self.etat_validation(self.obtenir_demande(id_))

    # ------------------------------------------------- robots lances depuis le site
    ROBOTS = {"d1": "rte_ee"}  # robot -> filiere servie
    MODES_ROBOT = {"banc": "banc d'essai", "portail": "portail opérateur"}

    def creer_tache_robot(self, demande_id: str, mode: str, jusqua: int = 5, auteur: str = "") -> dict:
        d = self.obtenir_demande(demande_id)
        if not d:
            raise KeyError(demande_id)
        robot = {"rte_ee": "d1", "enedis": "enedis"}.get(d["filiere"])
        if not robot:
            raise ValueError("robot disponible pour les demandes RTE étude exploratoire et Enedis seulement, pour l'instant")
        if mode not in self.MODES_ROBOT:
            raise ValueError("mode : banc ou portail")
        if robot == "enedis" and mode == "banc":
            raise ValueError("pas de banc d'essai pour le portail Enedis : il garde un brouillon, l'essai se fait sur le portail, étape par étape")
        derniere = 5 if robot == "d1" else 4
        jusqua = max(1, min(derniere, int(jusqua or derniere)))
        if mode == "portail" and jusqua >= derniere - 1 and regles.VALIDATION_REQUISE and d["validation"]["etat"] != "validee":
            raise ValueError("portail complet refusé : validation du responsable " + {"perimee": "périmée", "demandee": "en attente",
                             "refusee": "refusée"}.get(d["validation"]["etat"], "absente") + ". Essai possible jusqu'à l'étape 3, ou sur le banc")
        ouverte = self.cx.execute("SELECT id FROM taches_robot WHERE demande_id = ? AND statut IN ('en_attente','en_cours')",
                                  (demande_id,)).fetchone()
        if ouverte:
            raise ValueError("une tâche robot est déjà en cours pour cette demande")
        cur = self.cx.execute("INSERT INTO taches_robot (demande_id, robot, mode, jusqua, statut, demandee_par, demandee_le) VALUES (?,?,?,?,?,?,?)",
                              (demande_id, robot, mode, jusqua, "en_attente", auteur or "interne", maintenant()))
        self._journal(demande_id, auteur, "robot", "", f"lancement demandé ({self.MODES_ROBOT[mode]}"
                      + (f", jusqu'à l'étape {jusqua}" if jusqua < derniere else "") + ")", "dashboard")
        self.cx.commit()
        return self.obtenir_tache_robot(cur.lastrowid)

    def obtenir_tache_robot(self, tid: int) -> dict | None:
        r = self.cx.execute("SELECT * FROM taches_robot WHERE id = ?", (tid,)).fetchone()
        return dict(r) if r else None

    def lister_taches_robot(self, demande_id: str | None = None, limite: int = 20) -> list[dict]:
        if demande_id:
            rows = self.cx.execute("SELECT * FROM taches_robot WHERE demande_id = ? ORDER BY id DESC LIMIT ?", (demande_id, limite))
        else:
            rows = self.cx.execute("SELECT * FROM taches_robot ORDER BY id DESC LIMIT ?", (limite,))
        return [dict(r) for r in rows.fetchall()]

    def prendre_tache_robot(self, agent: str, version: str = "", info: str = "") -> dict | None:
        """Appel periodique de l'agent du poste : signale sa presence et prend la plus ancienne tache en attente."""
        t = maintenant()
        with self.verrou:
            self.cx.execute("INSERT INTO agents (nom, vu_le, version, info) VALUES (?,?,?,?) ON CONFLICT(nom) DO UPDATE SET "
                            "vu_le = excluded.vu_le, version = excluded.version, info = excluded.info", (agent, t, version, info))
            occupe = self.cx.execute("SELECT id FROM taches_robot WHERE statut = 'en_cours' AND agent = ?", (agent,)).fetchone()
            # un agent anterieur a 0.9.1 ne connait que le robot D1 : il ne doit pas prendre une tache Enedis
            def _v(x):
                try:
                    return tuple(int(n) for n in (x or "0").split(".")[:3])
                except ValueError:
                    return (0,)
            filtre = "" if _v(version) >= (0, 9, 1) else " AND robot = 'd1'"
            r = None if occupe else self.cx.execute("SELECT * FROM taches_robot WHERE statut = 'en_attente'" + filtre + " ORDER BY id LIMIT 1").fetchone()
            if r:
                self.cx.execute("UPDATE taches_robot SET statut = 'en_cours', agent = ?, prise_le = ? WHERE id = ? AND statut = 'en_attente'",
                                (agent, t, r["id"]))
            self.cx.commit()
        return self.obtenir_tache_robot(r["id"]) if r else None

    def journal_tache_robot(self, tid: int, lignes: list[str]) -> None:
        if not lignes:
            return
        with self.verrou:
            r = self.cx.execute("SELECT journal FROM taches_robot WHERE id = ?", (tid,)).fetchone()
            if not r:
                raise KeyError(tid)
            texte = ((r["journal"] or "") + "\n".join(lignes) + "\n")[-60000:]
            self.cx.execute("UPDATE taches_robot SET journal = ? WHERE id = ?", (texte, tid))
            self.cx.commit()

    def finir_tache_robot(self, tid: int, statut: str, resultat: str = "") -> dict:
        if statut not in ("terminee", "erreur", "annulee"):
            raise ValueError("statut de fin : terminee, erreur ou annulee")
        t = self.obtenir_tache_robot(tid)
        if not t:
            raise KeyError(tid)
        self.cx.execute("UPDATE taches_robot SET statut = ?, fin_le = ?, resultat = ? WHERE id = ?", (statut, maintenant(), resultat, tid))
        libelle = {"terminee": "terminé", "erreur": "arrêté", "annulee": "annulé"}[statut]
        self._journal(t["demande_id"], t["agent"] or "robot", "robot", "", libelle + (f" : {resultat}" if resultat else ""), "robot")
        self.cx.commit()
        return self.obtenir_tache_robot(tid)

    def annuler_tache_robot(self, tid: int, auteur: str = "") -> dict:
        t = self.obtenir_tache_robot(tid)
        if not t:
            raise KeyError(tid)
        if t["statut"] != "en_attente":
            raise ValueError("seule une tâche pas encore prise par l'agent peut être annulée (sinon fermer la fenêtre Chrome du robot)")
        return self.finir_tache_robot(tid, "annulee", f"annulée par {auteur or 'interne'}")

    def agents(self) -> list[dict]:
        out = []
        for r in self.cx.execute("SELECT * FROM agents ORDER BY vu_le DESC").fetchall():
            a = dict(r)
            try:
                a["secondes"] = int((datetime.now() - datetime.fromisoformat(a["vu_le"])).total_seconds())
            except (TypeError, ValueError):
                a["secondes"] = None
            a["en_ligne"] = a["secondes"] is not None and a["secondes"] < 60
            out.append(a)
        return out

    # ------------------------------------------------- reponses des operateurs lues
    def ajouter_analyse(self, demande_id: str, piece_id: int | None, type_: str, donnees: dict, auteur: str = "") -> dict:
        cur = self.cx.execute("INSERT INTO analyses (demande_id, piece_id, type, donnees, cree_le, cree_par) VALUES (?,?,?,?,?,?)",
                              (demande_id, piece_id, type_, json.dumps(donnees, ensure_ascii=False), maintenant(), auteur or "interne"))
        n = len(donnees.get("solutions") or [])
        if type_ == "ptf_rte":
            resume = f"PTF n° {donnees.get('num_ptf') or '?'}, {donnees.get('delai_mois') or '?'} mois"
        else:
            resume = f"étude n° {donnees.get('num_etude') or '?'}, {n} solution{'s' if n > 1 else ''}"
        self._journal(demande_id, auteur, "réponse lue", "", resume, "lecture")
        self.cx.commit()
        return self.obtenir_analyse(cur.lastrowid)

    def obtenir_analyse(self, aid: int) -> dict | None:
        r = self.cx.execute("SELECT a.*, p.nom_fichier FROM analyses a LEFT JOIN pieces p ON p.id = a.piece_id WHERE a.id = ?", (aid,)).fetchone()
        if not r:
            return None
        a = dict(r)
        a["donnees"] = json.loads(a["donnees"])
        return a

    def lister_analyses(self, demande_id: str) -> list[dict]:
        ids = [r["id"] for r in self.cx.execute("SELECT id FROM analyses WHERE demande_id = ? ORDER BY id DESC", (demande_id,))]
        return [self.obtenir_analyse(i) for i in ids]

    def reporter_analyse(self, aid: int, champs: dict, numero_solution: int | None, statut: str | None, auteur: str = "") -> dict:
        a = self.obtenir_analyse(aid)
        if not a:
            raise KeyError(aid)
        if statut:
            champs = {**champs, "statut": statut}
        d = self.modifier_demande(a["demande_id"], champs, auteur, "lecture")
        self.cx.execute("UPDATE analyses SET reportee_le = ?, reportee_par = ?, solution_reportee = ? WHERE id = ?",
                        (maintenant(), auteur or "interne", numero_solution, aid))
        self.cx.commit()
        return d

    # ------------------------------------------------- commentaires et verifications
    def _commentaire(self, r: sqlite3.Row) -> dict:
        c = dict(r)
        c["a_verifier"] = bool(c["a_verifier"])
        cible = c.get("cible") or ""
        if cible.startswith("fiche:"):
            c["libelle_cible"] = "Fiche : " + fiche_site.LIBELLES.get(cible[6:], cible[6:])
        elif cible.startswith("demande:"):
            c["libelle_cible"] = "Demande : " + cible[8:]
        else:
            c["libelle_cible"] = ""
        return c

    def lister_commentaires(self, projet: str | None = None, demande: str | None = None, a_verifier: bool = False,
                            ouverts: bool = False, limite: int = 300) -> list[dict]:
        q, args = "SELECT c.*, p.nom AS projet_nom FROM commentaires c LEFT JOIN projets p ON p.code = c.projet_code WHERE 1=1", []
        if projet:
            q += " AND c.projet_code = ?"; args.append(projet)
        if demande:
            q += " AND c.demande_id = ?"; args.append(demande)
        if a_verifier:
            q += " AND c.a_verifier = 1"
        if ouverts:
            q += " AND c.statut = 'ouvert'"
        q += " ORDER BY c.cree_le DESC, c.id DESC LIMIT ?"
        args.append(limite)
        return [self._commentaire(r) for r in self.cx.execute(q, args).fetchall()]

    def verifications_fiche(self, code: str) -> dict:
        """{champ: [points ouverts]} pour surligner les champs signales dans la fiche identite."""
        out: dict = {}
        for c in self.lister_commentaires(projet=code, a_verifier=True, ouverts=True):
            if (c.get("cible") or "").startswith("fiche:"):
                out.setdefault(c["cible"][6:], []).append(c)
        return out

    def ajouter_commentaire(self, c: dict, auteur: str = "") -> dict:
        texte = (c.get("texte") or "").strip()
        if not texte:
            raise ValueError("commentaire vide")
        demande = self.obtenir_demande(c["demande_id"]) if c.get("demande_id") else None
        if c.get("demande_id") and not demande:
            raise ValueError(f"demande inconnue : {c['demande_id']}")
        projet = (demande or {}).get("projet_code") or c.get("projet_code")
        if not projet or not self.obtenir_projet(projet):
            raise ValueError("projet inconnu")
        cible = c.get("cible") or None
        if cible and not (cible.startswith("fiche:") or cible.startswith("demande:")):
            raise ValueError(f"cible inconnue : {cible}")
        a_verifier = bool(c.get("a_verifier")) or bool(cible)
        cur = self.cx.execute(
            "INSERT INTO commentaires (projet_code, demande_id, cible, texte, a_verifier, statut, auteur, cree_le) VALUES (?,?,?,?,?,?,?,?)",
            (projet, c.get("demande_id") or None, cible, texte, 1 if a_verifier else 0, "ouvert", auteur or "interne", maintenant()))
        self._journal(c.get("demande_id"), auteur, f"projet {projet} : " + ("point à vérifier" if a_verifier else "commentaire"),
                      "", (fiche_site.LIBELLES.get(cible[6:], cible) + " : " if cible and cible.startswith("fiche:") else "") + texte[:120], "dashboard")
        self.cx.commit()
        r = self.cx.execute("SELECT c.*, p.nom AS projet_nom FROM commentaires c LEFT JOIN projets p ON p.code = c.projet_code WHERE c.id = ?",
                            (cur.lastrowid,)).fetchone()
        return self._commentaire(r)

    def traiter_commentaire(self, cid: int, statut: str, reponse: str = "", auteur: str = "") -> dict:
        """statut 'verifie' : le point est controle (reponse facultative). 'ouvert' : rouvert."""
        r = self.cx.execute("SELECT * FROM commentaires WHERE id = ?", (cid,)).fetchone()
        if not r:
            raise KeyError(cid)
        if statut not in ("ouvert", "verifie"):
            raise ValueError(f"statut inconnu : {statut}")
        if statut == "verifie":
            self.cx.execute("UPDATE commentaires SET statut = 'verifie', reponse = ?, traite_par = ?, traite_le = ? WHERE id = ?",
                            ((reponse or "").strip() or None, auteur or "interne", maintenant(), cid))
        else:
            self.cx.execute("UPDATE commentaires SET statut = 'ouvert', traite_par = NULL, traite_le = NULL WHERE id = ?", (cid,))
        self._journal(r["demande_id"], auteur, f"projet {r['projet_code']} : point à vérifier", r["texte"][:80],
                      "vérifié" + (f" : {reponse.strip()[:80]}" if reponse and reponse.strip() else "") if statut == "verifie" else "rouvert", "dashboard")
        self.cx.commit()
        r = self.cx.execute("SELECT c.*, p.nom AS projet_nom FROM commentaires c LEFT JOIN projets p ON p.code = c.projet_code WHERE c.id = ?",
                            (cid,)).fetchone()
        return self._commentaire(r)

    def supprimer_commentaire(self, cid: int, auteur: str = "") -> None:
        r = self.cx.execute("SELECT * FROM commentaires WHERE id = ?", (cid,)).fetchone()
        if not r:
            raise KeyError(cid)
        self.cx.execute("DELETE FROM commentaires WHERE id = ?", (cid,))
        self._journal(r["demande_id"], auteur, f"projet {r['projet_code']} : commentaire retiré", r["texte"][:80], "", "dashboard")
        self.cx.commit()

    # --------------------------------------------------------------- ressources
    def lister_ressources(self, filiere: str | None = None, etape: str | None = None) -> list[dict]:
        """Avec filiere : celles de la filiere et les communes. Avec etape : celles de l'etape et les « toutes etapes »."""
        q, args = "SELECT * FROM ressources WHERE 1=1", []
        if filiere:
            q += " AND filiere IN (?, 'commun')"; args.append(filiere)
        if etape:
            q += " AND (etape = ? OR etape = '' OR etape IS NULL)"; args.append(etape)
        q += " ORDER BY CASE filiere WHEN 'commun' THEN 1 ELSE 0 END, ordre, id"
        return [dict(r) for r in self.cx.execute(q, args).fetchall()]

    def obtenir_ressource(self, rid: int) -> dict | None:
        r = self.cx.execute("SELECT * FROM ressources WHERE id = ?", (rid,)).fetchone()
        return dict(r) if r else None

    def creer_ressource(self, r: dict, auteur: str = "") -> dict:
        if not (r.get("libelle") or "").strip():
            raise ValueError("libellé vide")
        if r.get("filiere") not in [*regles.FILIERES, "commun"]:
            raise ValueError(f"filière inconnue : {r.get('filiere')}")
        t = maintenant()
        ordre = self.cx.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM ressources").fetchone()[0]
        cur = self.cx.execute(
            "INSERT INTO ressources (filiere, etape, type, libelle, url, notes, verifie_le, ordre, cree_le, modifie_le) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r["filiere"], r.get("etape") or "", r.get("type") or "formulaire", r["libelle"].strip(), (r.get("url") or "").strip() or None,
             r.get("notes") or "", r.get("verifie_le") or None, ordre, t, t))
        self._journal(None, auteur, "document", "", r["libelle"].strip(), "dashboard")
        self.cx.commit()
        return self.obtenir_ressource(cur.lastrowid)

    def modifier_ressource(self, rid: int, champs: dict, auteur: str = "") -> dict:
        r = self.obtenir_ressource(rid)
        if not r:
            raise KeyError(rid)
        modifs = {k: (v if v != "" or k in ("etape", "notes") else None) for k, v in champs.items() if k in COLONNES_RESSOURCE and r.get(k) != v}
        modifs.update({k: v for k, v in champs.items() if k in ("fichier", "nom_fichier")})
        if modifs:
            sets = ", ".join(f"{k} = ?" for k in modifs)
            self.cx.execute(f"UPDATE ressources SET {sets}, modifie_le = ? WHERE id = ?", (*modifs.values(), maintenant(), rid))
            self.cx.commit()
        return self.obtenir_ressource(rid)

    def supprimer_ressource(self, rid: int, auteur: str = "") -> dict | None:
        r = self.obtenir_ressource(rid)
        if not r:
            return None
        self.cx.execute("DELETE FROM ressources WHERE id = ?", (rid,))
        self._journal(None, auteur, "document retiré", r["libelle"], "", "dashboard")
        self.cx.commit()
        return r

    # ------------------------------------------------------------------ contacts
    def lister_contacts(self) -> list[dict]:
        rows = self.cx.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM echanges e WHERE e.contact_id = c.id) AS nb_echanges,"
            " (SELECT MAX(date) FROM echanges e WHERE e.contact_id = c.id) AS dernier_echange"
            " FROM contacts c ORDER BY c.organisation, c.nom").fetchall()
        return [dict(r) for r in rows]

    def obtenir_contact(self, contact_id: int) -> dict | None:
        r = self.cx.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        return dict(r) if r else None

    def contact_par_email(self, email: str) -> dict | None:
        if not email:
            return None
        r = self.cx.execute("SELECT * FROM contacts WHERE lower(email) = ?", (email.lower().strip(),)).fetchone()
        return dict(r) if r else None

    def creer_contact(self, c: dict, auteur: str = "") -> dict:
        if not (c.get("nom") or "").strip():
            raise ValueError("nom du contact vide")
        if c.get("email") and self.contact_par_email(c["email"]):
            raise ValueError(f"un contact existe déjà avec l'adresse {c['email']}")
        t = maintenant()
        cur = self.cx.execute(
            f"INSERT INTO contacts ({', '.join(COLONNES_CONTACT)}, cree_le, modifie_le) VALUES ({', '.join('?' * (len(COLONNES_CONTACT) + 2))})",
            (*[(c.get(k) or "").strip() if isinstance(c.get(k), str) else c.get(k) for k in COLONNES_CONTACT], t, t))
        self._journal(None, auteur, "contact", "", f"{c.get('nom')} ({c.get('organisation') or ''})", "dashboard")
        self.cx.commit()
        return self.obtenir_contact(cur.lastrowid)

    def modifier_contact(self, contact_id: int, champs: dict, auteur: str = "") -> dict:
        c = self.obtenir_contact(contact_id)
        if not c:
            raise KeyError(contact_id)
        modifs = {k: v for k, v in champs.items() if k in COLONNES_CONTACT and c.get(k) != v}
        if modifs:
            sets = ", ".join(f"{k} = ?" for k in modifs)
            self.cx.execute(f"UPDATE contacts SET {sets}, modifie_le = ? WHERE id = ?", (*modifs.values(), maintenant(), contact_id))
            self.cx.commit()
        return self.obtenir_contact(contact_id)

    def supprimer_contact(self, contact_id: int, auteur: str = "") -> None:
        c = self.obtenir_contact(contact_id)
        if not c:
            raise KeyError(contact_id)
        self.cx.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        self._journal(None, auteur, "contact retiré", c["nom"], "", "dashboard")
        self.cx.commit()

    # ------------------------------------------------------------------ echanges
    def _echange(self, r: sqlite3.Row) -> dict:
        e = dict(r)
        e["attend_reponse"] = bool(e["attend_reponse"])
        e["libelle_sens"] = regles.SENS_ECHANGE.get(e["sens"], e["sens"])
        e["libelle_canal"] = regles.CANAUX_ECHANGE.get(e["canal"], e["canal"])
        if e["attend_reponse"]:
            d = regles.lire_date(e["date"])
            e["jours_attente"] = (date.today() - d).days if d else None
        return e

    _SELECT_ECHANGE = ("SELECT e.*, c.nom AS contact_nom, c.organisation AS contact_organisation, d.filiere AS filiere"
                       " FROM echanges e LEFT JOIN contacts c ON c.id = e.contact_id LEFT JOIN demandes d ON d.id = e.demande_id")

    def lister_echanges(self, projet: str | None = None, demande: str | None = None, attente: bool = False,
                        contact: int | None = None, limite: int = 200) -> list[dict]:
        q, args = self._SELECT_ECHANGE + " WHERE 1=1", []
        if projet:
            q += " AND e.projet_code = ?"; args.append(projet)
        if demande:
            q += " AND e.demande_id = ?"; args.append(demande)
        if contact:
            q += " AND e.contact_id = ?"; args.append(contact)
        if attente:
            q += " AND e.attend_reponse = 1"
        q += " ORDER BY e.date DESC, e.id DESC LIMIT ?"
        args.append(limite)
        return [self._echange(r) for r in self.cx.execute(q, args).fetchall()]

    def obtenir_echange(self, echange_id: int) -> dict | None:
        r = self.cx.execute(self._SELECT_ECHANGE + " WHERE e.id = ?", (echange_id,)).fetchone()
        return self._echange(r) if r else None

    def resume_echanges(self, projet: str | None = None, demande: str | None = None) -> dict:
        """Dernier echange, plus ancien envoi encore sans reponse, nombre total."""
        cle, val = ("demande_id", demande) if demande else ("projet_code", projet)
        n = self.cx.execute(f"SELECT COUNT(*) FROM echanges WHERE {cle} = ?", (val,)).fetchone()[0]
        if not n:
            return {"nb": 0, "dernier": None, "attente": None, "nb_attente": 0}
        dernier = self.cx.execute(self._SELECT_ECHANGE + f" WHERE e.{cle} = ? ORDER BY e.date DESC, e.id DESC LIMIT 1", (val,)).fetchone()
        attentes = self.cx.execute(self._SELECT_ECHANGE + f" WHERE e.{cle} = ? AND e.attend_reponse = 1 ORDER BY e.date ASC", (val,)).fetchall()
        att = None
        if attentes:
            a = self._echange(attentes[0])
            att = {"id": a["id"], "date": a["date"], "jours": a.get("jours_attente") or 0, "objet": a["objet"],
                   "contact": a["contact_nom"] or a["destinataires"] or "", "relance_le": a["relance_le"],
                   "demande_id": a["demande_id"]}
        dn = self._echange(dernier)
        return {"nb": n, "nb_attente": len(attentes), "attente": att,
                "dernier": {"id": dn["id"], "date": dn["date"], "sens": dn["sens"], "libelle_sens": dn["libelle_sens"],
                            "objet": dn["objet"], "contact": dn["contact_nom"] or dn["expediteur"] or "", "demande_id": dn["demande_id"]}}

    def ajouter_echange(self, e: dict, auteur: str = "", origine: str = "manuel") -> dict:
        """Enregistre un echange. Un echange recu clot les attentes de reponse ouvertes sur la meme
        demande (ou le meme projet sans demande), sauf clore_attente=False. Doublon de message_id : renvoie l'existant."""
        if e.get("message_id"):
            r = self.cx.execute("SELECT id FROM echanges WHERE message_id = ?", (e["message_id"],)).fetchone()
            if r:
                return {**self.obtenir_echange(r["id"]), "doublon": True}
        demande = self.obtenir_demande(e["demande_id"]) if e.get("demande_id") else None
        if e.get("demande_id") and not demande:
            raise ValueError(f"demande inconnue : {e['demande_id']}")
        projet = (demande or {}).get("projet_code") or e.get("projet_code")
        if not projet or not self.obtenir_projet(projet):
            raise ValueError("projet inconnu : indiquer projet_code ou demande_id")
        sens = e.get("sens") or "note"
        if sens not in regles.SENS_ECHANGE:
            raise ValueError(f"sens inconnu : {sens}")
        canal = e.get("canal") or "mail"
        if canal not in regles.CANAUX_ECHANGE:
            raise ValueError(f"canal inconnu : {canal}")
        date_e = (e.get("date") or maintenant()).replace("T", " ")
        if len(date_e) == 10:
            date_e += " 12:00:00"
        contact_id = e.get("contact_id") or None
        if not contact_id:
            adresse = e.get("expediteur") if sens == "recu" else (e.get("destinataires") or "").split(",")[0]
            c = self.contact_par_email((adresse or "").strip())
            contact_id = c["id"] if c else None
        attend = bool(e.get("attend_reponse")) if "attend_reponse" in e else sens == "envoye"
        repondu = None
        if attend and sens == "envoye":
            # depot dans le desordre (releve de boite mail, .eml deposes apres coup) : une reponse deja enregistree,
            # posterieure a ce message, le cloture d'emblee
            if e.get("demande_id"):
                deja = self.cx.execute("SELECT MIN(date) AS d FROM echanges WHERE demande_id = ? AND sens = 'recu' AND date > ?",
                                       (e["demande_id"], date_e)).fetchone()
            else:
                deja = self.cx.execute("SELECT MIN(date) AS d FROM echanges WHERE projet_code = ? AND demande_id IS NULL"
                                       " AND sens = 'recu' AND date > ?", (projet, date_e)).fetchone()
            if deja and deja["d"]:
                attend, repondu = False, deja["d"]
        cur = self.cx.execute(
            "INSERT INTO echanges (projet_code, demande_id, contact_id, date, sens, canal, expediteur, destinataires, objet, resume,"
            " attend_reponse, relance_le, fichier, nom_fichier, message_id, origine, cree_le, cree_par) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (projet, e.get("demande_id") or None, contact_id, date_e, sens, canal, e.get("expediteur") or "",
             e.get("destinataires") or "", (e.get("objet") or "").strip(), (e.get("resume") or "").strip(),
             1 if attend and sens == "envoye" else 0, e.get("relance_le") or None, e.get("fichier"), e.get("nom_fichier"),
             e.get("message_id") or None, origine, maintenant(), auteur or "interne"))
        nouvel = cur.lastrowid
        if repondu:
            self.cx.execute("UPDATE echanges SET repondu_le = ? WHERE id = ?", (repondu, nouvel))
        if sens == "recu" and e.get("clore_attente", True):
            if e.get("demande_id"):
                self.cx.execute("UPDATE echanges SET attend_reponse = 0, repondu_le = ? WHERE demande_id = ? AND attend_reponse = 1 AND date <= ?",
                                (date_e, e["demande_id"], date_e))
            else:
                self.cx.execute("UPDATE echanges SET attend_reponse = 0, repondu_le = ? WHERE projet_code = ? AND demande_id IS NULL"
                                " AND attend_reponse = 1 AND date <= ?", (date_e, projet, date_e))
        self._journal(e.get("demande_id"), auteur, "échange", "",
                      f"{regles.SENS_ECHANGE[sens].lower()} ({regles.CANAUX_ECHANGE[canal].lower()}) : {e.get('objet') or ''}".strip(), origine)
        self.cx.commit()
        return self.obtenir_echange(nouvel)

    def modifier_echange(self, echange_id: int, champs: dict, auteur: str = "") -> dict:
        e = self.obtenir_echange(echange_id)
        if not e:
            raise KeyError(echange_id)
        modifs = {}
        for k, v in champs.items():
            if k not in COLONNES_ECHANGE or k == "projet_code":
                continue
            if k == "attend_reponse":
                v = 1 if v else 0
            if v == "":
                v = None
            if k == "demande_id" and v:
                d = self.obtenir_demande(v)
                if not d:
                    raise ValueError(f"demande inconnue : {v}")
                modifs["projet_code"] = d["projet_code"]
            if k == "sens" and v not in regles.SENS_ECHANGE:
                raise ValueError(f"sens inconnu : {v}")
            if k == "canal" and v not in regles.CANAUX_ECHANGE:
                raise ValueError(f"canal inconnu : {v}")
            modifs[k] = v
        if "attend_reponse" in modifs and not modifs["attend_reponse"] and e["attend_reponse"] and "repondu_le" not in modifs:
            modifs["repondu_le"] = maintenant()
        if modifs:
            sets = ", ".join(f"{k} = ?" for k in modifs)
            self.cx.execute(f"UPDATE echanges SET {sets} WHERE id = ?", (*modifs.values(), echange_id))
            if "attend_reponse" in modifs:
                self._journal(e["demande_id"], auteur, "échange", e["objet"],
                              "en attente de réponse" if modifs["attend_reponse"] else "réponse close", "dashboard")
            self.cx.commit()
        return self.obtenir_echange(echange_id)

    def supprimer_echange(self, echange_id: int, auteur: str = "") -> dict | None:
        e = self.obtenir_echange(echange_id)
        if not e:
            return None
        self.cx.execute("DELETE FROM echanges WHERE id = ?", (echange_id,))
        self._journal(e["demande_id"], auteur, "échange retiré", e["objet"], "", "dashboard")
        self.cx.commit()
        return e

    # ------------------------------------------------------------------ journal
    def _journal(self, demande_id, auteur, champ, avant, apres, origine) -> None:
        self.cx.execute(
            "INSERT INTO journal (demande_id, horodatage, auteur, champ, avant, apres, origine) VALUES (?,?,?,?,?,?,?)",
            (demande_id, maintenant(), auteur or "interne", champ, _texte(avant), _texte(apres), origine),
        )

    def journal(self, demande_id: str | None = None, projet: str | None = None, limite: int = 50) -> list[dict]:
        if demande_id:
            rows = self.cx.execute("SELECT * FROM journal WHERE demande_id = ? ORDER BY id DESC LIMIT ?", (demande_id, limite)).fetchall()
        elif projet:
            rows = self.cx.execute(
                "SELECT j.* FROM journal j LEFT JOIN demandes d ON d.id = j.demande_id"
                " WHERE d.projet_code = ? OR j.champ LIKE ? OR j.champ LIKE ? OR j.champ LIKE ? ORDER BY j.id DESC LIMIT ?",
                (projet, f"fiche {projet} :%", f"source {projet}%", f"projet {projet} :%", limite)).fetchall()
        else:
            rows = self.cx.execute("SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ notifications
    def a_notifier(self) -> list[dict]:
        """Alertes de toutes les demandes, avec pour chacune la date du dernier envoi."""
        out = []
        for d in self.lister_demandes():
            for a in d["alertes"]:
                r = self.cx.execute("SELECT severite, dernier_envoi FROM notifications WHERE demande_id = ? AND cle = ?", (d["id"], a["cle"])).fetchone()
                out.append({
                    "demande_id": d["id"], "projet": d["projet_code"], "filiere": d["filiere"],
                    "severite": a["severite"], "texte": a["texte"], "cle": a["cle"],
                    "severite_precedente": r["severite"] if r else None,
                    "dernier_envoi": r["dernier_envoi"] if r else None,
                })
        return out

    def marquer_notifie(self, items: list[dict]) -> None:
        t = maintenant()
        for it in items:
            self.cx.execute(
                "INSERT INTO notifications (demande_id, cle, severite, dernier_envoi) VALUES (?,?,?,?)"
                " ON CONFLICT(demande_id, cle) DO UPDATE SET severite = excluded.severite, dernier_envoi = excluded.dernier_envoi",
                (it["demande_id"], it["cle"], it["severite"], t),
            )
        self.cx.commit()

    # -------------------------------------------------------------------- divers
    def compte(self) -> dict:
        n_p = self.cx.execute("SELECT COUNT(*) FROM projets").fetchone()[0]
        n_d = self.cx.execute("SELECT COUNT(*) FROM demandes").fetchone()[0]
        n_j = self.cx.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
        n_e = self.cx.execute("SELECT COUNT(*) FROM echanges").fetchone()[0]
        n_a = self.cx.execute("SELECT COUNT(*) FROM echanges WHERE attend_reponse = 1").fetchone()[0]
        n_v = self.cx.execute("SELECT COUNT(*) FROM commentaires WHERE a_verifier = 1 AND statut = 'ouvert'").fetchone()[0]
        return {"projets": n_p, "demandes": n_d, "journal": n_j, "echanges": n_e, "en_attente_reponse": n_a, "a_verifier": n_v}


def _code(s: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_.\-]", "-", (s or "").strip())[:40]


def _texte(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "oui" if v else "non"
    return str(v)
