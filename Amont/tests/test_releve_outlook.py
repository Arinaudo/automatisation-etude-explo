"""Releve Outlook : choix des messages et depot dans Amont, avec un faux Graph et la vraie API (base temporaire).

Lancer : python tests/test_releve_outlook.py   (necessite fastapi, httpx)
"""
import importlib.util
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
tmp = tempfile.mkdtemp()
os.environ.update(AMONT_DB=f"{tmp}/amont.sqlite", AMONT_FICHIERS=f"{tmp}/f", AMONT_SOURCES=f"{tmp}/s")

from fastapi.testclient import TestClient  # noqa: E402

from amont_core import api  # noqa: E402

spec = importlib.util.spec_from_file_location("releve", RACINE / "2026_10_29_amont_releve_outlook.py")
releve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(releve)
releve.DOSSIER = Path(tmp) / "etat"

CFG = {"domaines": releve.DOMAINES_DEFAUT, "internes": ["castignac.com"], "auteur": "test", "amont_url": "http://amont"}


def adr(a):
    return {"emailAddress": {"address": a}}


def message(id_, de, a, objet, apercu=""):
    return {"id": id_, "subject": objet, "bodyPreview": apercu, "from": adr(de), "toRecipients": [adr(x) for x in a],
            "receivedDateTime": "2026-10-20T09:00:00Z"}


def mime(de, a, objet, corps, il_y_a_h=0):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = de, a, objet, make_msgid(domain="test.local")
    m["Date"] = format_datetime(datetime.now(timezone.utc) - timedelta(hours=il_y_a_h))
    m.set_content(corps)
    return bytes(m)


class FauxGraph:
    def __init__(self, messages):
        self.messages_par_dossier = messages
        self.mimes = {}

    def messages(self, dossier, depuis):
        return iter(self.messages_par_dossier.get(dossier, []))

    def mime(self, id_):
        return self.mimes[id_]


def test_filtre():
    codes = ["om01-gaz", "26-2818"]
    assert releve.pertinent(message("1", "x@grdf.fr", ["a@castignac.com"], "Bonjour"), CFG, codes)[0]
    assert releve.pertinent(message("2", "a@castignac.com", ["x@sous.rte-france.com"], "Bonjour"), CFG, codes)[0]
    assert not releve.pertinent(message("3", "a@castignac.com", ["b@castignac.com"], "OM01-GAZ à voir"), CFG, codes)[0], "interne"
    assert releve.pertinent(message("4", "x@bureau-etudes.fr", ["a@castignac.com"], "Dossier 26-2818"), CFG, codes)[0], "code connu"
    assert not releve.pertinent(message("5", "x@newsletter.com", ["a@castignac.com"], "Promo"), CFG, codes)[0]
    assert not releve.pertinent(message("6", "x@autregrdf.fr", ["a@castignac.com"], "Bonjour"), CFG, codes)[0], "pas un sous-domaine"


def test_passage_complet():
    c = TestClient(api.app)
    c.post("/api/projets", json={"code": "OM01", "nom": "DIGITAL2060 OM01", "commune": "Oursel-Maison", "departement": "60"})
    api.registre.preparer_demandes("OM01", ["grdf", "rte_ee"], "t")

    def deposer(contenu, nom):
        return c.post("/api/echanges/eml", files=[("fichiers", (nom, contenu, "message/rfc822"))]).json()

    g = FauxGraph({
        "sentitems": [message("s1", "a@castignac.com", ["jb@grdf.fr"], "OM01-GAZ : fiche Grands Projets")],
        "inbox": [message("r1", "jb@grdf.fr", ["a@castignac.com"], "RE: OM01-GAZ : fiche Grands Projets"),
                  message("r2", "promo@newsletter.com", ["a@castignac.com"], "Offre"),
                  message("r3", "inconnu@rte-france.com", ["a@castignac.com"], "Sans rapport avec un site")]})
    g.mimes = {"s1": mime("a@castignac.com", "jb@grdf.fr", "OM01-GAZ : fiche Grands Projets", "Ci-joint la fiche.", il_y_a_h=2),
               "r1": mime("jb@grdf.fr", "a@castignac.com", "RE: OM01-GAZ : fiche Grands Projets", "Bien reçu, nous revenons vers vous."),
               "r3": mime("inconnu@rte-france.com", "a@castignac.com", "Sans rapport avec un site", "Bonjour")}
    codes = releve.codes_demandes(c.get("/api/demandes").json())
    etat = {"traites": {}}
    b = releve.traiter(g, deposer, CFG, codes, etat, datetime.now(timezone.utc), journal=lambda *a: None)
    assert (b["deposes"], b["ignores"], b["refuses"], b["erreurs"]) == (2, 1, 1, 0), b
    echanges = c.get("/api/echanges?demande=OM01-GAZ").json()
    assert sorted(e["sens"] for e in echanges) == ["envoye", "recu"]
    attente = c.get("/api/echanges?attente=true").json()
    assert attente == [], [(e["objet"], e["sens"], e["demande_id"], e["date"]) for e in attente] + [(e["sens"], e["date"], e["demande_id"]) for e in echanges]
    # deuxieme passage : plus rien a deposer (etat local), et un redepot cote Amont serait un doublon
    b2 = releve.traiter(g, deposer, CFG, codes, etat, datetime.now(timezone.utc), journal=lambda *a: None)
    assert b2["deposes"] == 0 and b2["ignores"] == 0
    etat2 = {"traites": {}}
    b3 = releve.traiter(g, deposer, CFG, codes, etat2, datetime.now(timezone.utc), journal=lambda *a: None)
    assert b3["doublons"] == 2, b3


def test_simulation_ne_depose_rien():
    g = FauxGraph({"inbox": [message("r1", "jb@grdf.fr", ["a@castignac.com"], "Bonjour")]})
    appels = []
    b = releve.traiter(g, lambda *a: appels.append(a), CFG, [], {"traites": {}}, datetime.now(timezone.utc), simulation=True, journal=lambda *a: None)
    assert not appels and b["deposes"] == 0


def test_erreur_reseau_reprise_au_passage_suivant():
    g = FauxGraph({"inbox": [message("r1", "jb@grdf.fr", ["a@castignac.com"], "Bonjour")]})

    def echec(*a):
        raise RuntimeError("Amont 500")
    etat = {"traites": {}}
    g.mimes = {"r1": b"x"}
    b = releve.traiter(g, echec, CFG, [], etat, datetime.now(timezone.utc), journal=lambda *a: None)
    assert b["erreurs"] == 1 and "r1" not in etat["traites"]


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
            print("ok", nom)
