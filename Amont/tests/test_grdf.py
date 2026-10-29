"""Fiche GRDF Grands Projets : le PDF rempli reprend la fiche du site, case par case.

Lancer : python -m pytest tests/test_grdf.py   (ou python tests/test_grdf.py)
Donnees fictives ; le modele PDF est celui du depot.
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pypdf import PdfReader, PdfWriter  # noqa: E402

from amont_core import grdf  # noqa: E402

FICHE = {
    "nom_installation": "DC TEST 01", "adresse": "Lieudit Les Prés", "code_postal": "60000", "commune": "Beauvais", "departement": "60",
    "parcelles": "AB 12, AB 13", "surface_ha": 20, "demandeur_societe": "SAS TEST", "demandeur_siret": "12345678900011",
    "demandeur_representant": "Jeanne MARTIN, Directrice générale", "demandeur_siege_adresse": "1 rue Exemple",
    "demandeur_siege_cp_ville": "75001 Paris", "interlocuteur_prenom": "Alex", "interlocuteur_nom": "DUPONT",
    "interlocuteur_mail": "alex@example.com", "interlocuteur_tel": "0102030405", "gaz_date_mise_en_service": "2030-06-30",
    "usage_gaz": "Production électrique de secours", "debit_gaz_nm3h": 10000, "gaz_conso_annuelle_mwh": 5000,
    "gaz_conso_jour_mwh": 200, "gaz_pression_demandee": "300 mbar", "gaz_double_ligne": "non", "gaz_redondance": "oui",
    "gaz_augmentation": "non", "gaz_solutions": "Cogénération, PAC gaz et moteurs 20 MW",
    "gaz_profil_10_ans": "5000/200 ; 10000/400", "gaz_presentation": "Centre de données de test. " * 30,
}


def _lire(pdf: bytes, cle: str):
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    nom = grdf.traduction(w)[grdf.TEXTES.get(cle) or grdf.CASES[cle]]
    champs = PdfReader(io.BytesIO(pdf)).get_fields() or {}
    return (champs.get(nom) or {}).get("/V")


def test_modele_contient_tous_les_champs():
    w = PdfWriter(clone_from=PdfReader(str(grdf.MODELE)))
    attendus = set(grdf.TEXTES.values()) | set(grdf.CASES.values()) | {grdf.CHOIX_SUPPRESSION}
    trad = grdf.traduction(w)
    assert attendus <= set(trad)
    noms = [trad[c] for c in attendus]
    assert len(noms) == len(set(noms)), "deux champs attendus partagent le meme champ PDF"


def test_modele_vide_de_toute_donnee():
    brut = grdf.MODELE.read_bytes()
    for mot in (b"OM01", b"ODF", b"Oursel", b"TAIEB", b"OBADIA", b"castignac"):
        assert mot not in brut


def test_fiche_remplie():
    pieces = [{"type": "plan_situation"}, {"type": "plan_cadastral_1000"}]
    x = grdf.donnees(FICHE, {}, pieces, "TEST")
    pdf = grdf.remplir(x)
    assert _lire(pdf, "moa_societe") == "SAS TEST"
    assert _lire(pdf, "moa_siret") == "123 456 789 00011"
    assert _lire(pdf, "sign_nom") == "Jeanne MARTIN"
    assert _lire(pdf, "sign_fonction") == "Directrice générale"
    assert _lire(pdf, "date_mes") == "30/06/2030"
    assert _lire(pdf, "puissance_max_mw") == "112"          # 10 000 Nm3/h x 11,2 kWh/Nm3 PCS
    assert _lire(pdf, "puissance_installee_kw") == "112 000"
    assert _lire(pdf, "annee1_conso") == "10 000" and _lire(pdf, "annee2_conso") in (None, "")
    assert _lire(pdf, "pression_300") == "/Yes" and _lire(pdf, "pression_fil") == "/Off"
    assert _lire(pdf, "double_non") == "/Yes" and _lire(pdf, "redond_oui") == "/Yes"
    assert _lire(pdf, "augm_non") == "/Yes" and _lire(pdf, "augm_oui") == "/Off"
    assert _lire(pdf, "sol_cogeneration") == "/Yes" and _lire(pdf, "sol_pac_gaz") == "/Yes" and _lire(pdf, "sol_chaudiere") == "/Off"
    assert _lire(pdf, "sol_autres") == "/Yes" and "moteurs" in _lire(pdf, "solution_autre")
    assert _lire(pdf, "piece_situation") == "/Yes" and _lire(pdf, "piece_kbis") == "/Off"
    assert _lire(pdf, "dest_datacenter") == "/Yes" and _lire(pdf, "neuf") == "/Yes"
    assert "\n" in _lire(pdf, "presentation"), "le texte long doit etre coupe aux mots"


def test_champ_requis_absent_sort_a_completer():
    x = grdf.donnees({**FICHE, "demandeur_siret": ""}, {}, [], "TEST")
    assert "SIRET" in grdf.manquants(x)
    assert _lire(grdf.remplir(x), "moa_siret") == grdf.A_COMPLETER


def test_pression_par_defaut_depuis_la_fiche():
    x = grdf.donnees({**FICHE, "gaz_pression_demandee": "", "pression_gaz_bar": 4}, {}, [], "TEST")
    assert x["pression_autre"] == "4 bar rel."


def test_courriel_alertes_et_pieces():
    pieces = [{"id": 1, "type": "fiche_grdf", "nom_fichier": "2030_01_01_fiche_GRDF_TEST.pdf", "ajoute_le": "1", "taille_octets": 10},
              {"id": 2, "type": "fiche_grdf", "nom_fichier": "fiche_signee.pdf", "ajoute_le": "2", "taille_octets": 10},
              {"id": 3, "type": "fiche_grdf", "nom_fichier": "2030_01_02_fiche_GRDF_TEST.pdf", "ajoute_le": "3", "taille_octets": 10}]
    m = grdf.courriel(FICHE, {"projet_code": "TEST"}, pieces, [grdf.DESTINATAIRE_GRDF])
    assert [p["id"] for p in m["pieces"]] == [2], "la version signee l'emporte sur une version generee plus recente"
    assert not any("non signée" in a for a in m["alertes"])
    assert any("plan de situation" in a for a in m["alertes"])
    assert "Grands Projets" in m["objet"]


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
            print("ok", nom)
