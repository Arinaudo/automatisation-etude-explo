"""Fabrique le modele de la fiche GRDF Grands Projets : la fiche remplie d'un dossier, videe de ses valeurs.

Usage : python 2026_10_29_amont_grdf_modele.py fiche_remplie.pdf
Ecrit amont_core/modeles/fiche_grdf_modele.pdf. Seuls les champs que Amont renseigne sont vides ; le contact GRDF,
les libelles et le logo sont conserves. Verifie que chaque champ attendu par amont_core/grdf.py existe dans la fiche.
"""
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from amont_core import grdf  # noqa: E402


def main(source: str) -> None:
    lecteur = PdfReader(source)
    champs = set((lecteur.get_fields() or {}).keys())
    attendus = set(grdf.TEXTES.values()) | set(grdf.CASES.values()) | {grdf.CHOIX_SUPPRESSION}
    absents = sorted(attendus - champs)
    if absents:
        sys.exit("champs introuvables dans la fiche : " + " ; ".join(absents))
    w = PdfWriter(clone_from=lecteur)
    trad = grdf.traduction(w)
    noms = [trad[c] for c in attendus]
    doubles = sorted({n for n in noms if noms.count(n) > 1})
    if doubles:
        sys.exit("plusieurs champs attendus partagent le meme champ PDF : " + " ; ".join(doubles))
    vides = {c: "" for c in grdf.TEXTES.values()}
    vides[grdf.CHOIX_SUPPRESSION] = grdf.SUPPRESSION_DEFAUT
    off = {c: "/Off" for c in grdf.CASES.values()}
    for page in w.pages:
        w.update_page_form_field_values(page, {trad[c]: v for c, v in {**vides, **off}.items()}, auto_regenerate=False)
    # les noeuds parents de la fiche portent eux aussi une valeur (heritee de la fiche d'origine) : on les vide
    cibles = set(grdf.TEXTES.values()) | set(grdf.CASES.values()) | {grdf.CHOIX_SUPPRESSION}
    parents = {".".join(c.split(".")[:i]) for c in cibles for i in range(1, c.count(".") + 1)}

    def parcourir(noeud, prefixe=""):
        noeud = noeud.get_object()
        nom = ".".join(x for x in (prefixe, str(noeud["/T"]) if "/T" in noeud else "") if x)
        if nom in parents and "/V" in noeud:
            del noeud["/V"]
        for k in noeud.get("/Kids", []):
            parcourir(k, nom)

    for champ in w._root_object["/AcroForm"]["/Fields"]:
        parcourir(champ)
    grdf.purger_apparences(w, set(grdf.TEXTES.values()))
    sortie = grdf.MODELE
    sortie.parent.mkdir(exist_ok=True)
    with open(sortie, "wb") as f:
        w.write(f)
    print(f"{len(attendus)} champs reperes, modele ecrit : {sortie}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
