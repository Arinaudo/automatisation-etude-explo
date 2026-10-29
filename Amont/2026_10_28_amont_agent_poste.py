"""Agent du poste : execute sur ce PC les robots lances depuis le site Amont.

Le serveur Amont ne peut pas piloter un navigateur que vous voyez : c'est ce petit programme, sur votre poste,
qui le fait. Il interroge Amont toutes les 5 secondes ; quand vous cliquez « Banc d'essai » ou « Pré-remplir le
portail » sur une demande, il lance le robot D1 (RTE) ou le robot Enedis dans une fenetre Chrome, renvoie au site ce que le robot affiche,
puis reprend son attente. Le robot s'arrete toujours avant la certification : le dernier clic reste le votre,
dans la fenetre Chrome.

Lancement (dossier Amont du poste, Tailscale connecte) :
    python 2026_10_28_amont_agent_poste.py
ou double-clic sur 2026_10_28_amont_agent_poste.bat. Pour qu'il demarre avec Windows : Win+R, « shell:startup »,
y deposer un raccourci vers le .bat.

Options : --amont URL (defaut : variable AMONT_URL, sinon https://amont.arinaudo.fr), --nom (defaut : nom du PC),
--intervalle SECONDES. Bibliotheque standard seulement ; le robot, lui, demande Selenium (pip install selenium).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

VERSION = "0.9.1"
ICI = Path(__file__).resolve().parent
ROBOT_D1 = ICI / "2026_10_26_amont_robot_d1.py"
ROBOT_ENEDIS = ICI / "2026_10_28_amont_robot_enedis.py"
ROBOTS = {"d1": (ROBOT_D1, 5), "enedis": (ROBOT_ENEDIS, 4)}  # script, derniere etape
AMONT_DEFAUT = os.environ.get("AMONT_URL", "https://amont.arinaudo.fr").rstrip("/")
VERROU = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AmontRobot" / "agent.verrou"


def appel(base: str, chemin: str, corps: dict | None = None, delai: int = 20):
    req = urllib.request.Request(base + "/api" + chemin, data=json.dumps(corps or {}).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "X-Amont-Origine": "robot",
                                          "X-Amont-Auteur": urllib.parse.quote("agent du poste")})
    with urllib.request.urlopen(req, timeout=delai) as r:
        return json.loads(r.read() or b"null")


def dire(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


class Execution:
    """Lance le robot pour une tache et relaie sa sortie vers Amont, par paquets."""

    def __init__(self, base: str, tache: dict):
        self.base, self.t = base, tache
        self.tampon: list[str] = []
        self.verrou = threading.Lock()
        self.derniere_utile = ""
        self.fini = False

    def commande(self) -> list[str]:
        script, derniere = ROBOTS.get(self.t.get("robot") or "d1", ROBOTS["d1"])
        c = [sys.executable, str(script), "--demande", self.t["demande_id"], "--amont", self.base, "--non-interactif"]
        if self.t["mode"] == "banc":
            c.append("--banc")
        if (self.t.get("jusqua") or derniere) < derniere:
            c += ["--jusqua", str(self.t["jusqua"])]
        return c

    def relayer(self) -> None:
        while not self.fini:
            time.sleep(1.5)
            self.vider()

    def vider(self) -> None:
        with self.verrou:
            lignes, self.tampon = self.tampon, []
        if lignes:
            try:
                appel(self.base, f"/robot/taches/{self.t['id']}/journal", {"lignes": lignes})
            except (urllib.error.URLError, OSError):
                with self.verrou:  # Amont injoignable un instant : on garde les lignes pour le prochain envoi
                    self.tampon = lignes + self.tampon

    def lancer(self) -> None:
        dire(f"tâche {self.t['id']} : robot {self.t.get('robot') or 'd1'} sur {self.t['demande_id']} ({self.t['mode']})")
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        threading.Thread(target=self.relayer, daemon=True).start()
        try:
            p = subprocess.Popen(self.commande(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", env=env, cwd=str(ICI))
        except OSError as e:
            self.fin("erreur", f"robot non lancé : {e}")
            return
        for ligne in p.stdout:
            ligne = ligne.rstrip()
            print("   " + ligne, flush=True)
            with self.verrou:
                self.tampon.append(ligne)
            if ligne.startswith(("FORMULAIRE PRÉ-REMPLI", "ARRÊT DU ROBOT", "Test arrêté", "Amont :")):
                self.derniere_utile = ligne
        code = p.wait()
        self.fini = True
        self.vider()
        if code == 0:
            self.fin("terminee", self.derniere_utile or "robot terminé")
        else:
            self.fin("erreur", self.derniere_utile or f"le robot s'est arrêté (code {code})")

    def fin(self, statut: str, resultat: str) -> None:
        for essai in range(10):
            try:
                appel(self.base, f"/robot/taches/{self.t['id']}/fin", {"statut": statut, "resultat": resultat})
                break
            except (urllib.error.URLError, OSError):
                time.sleep(5)
        dire(f"tâche {self.t['id']} : {statut} · {resultat}")


def battement(base: str, nom: str, arret: threading.Event) -> None:
    """Pendant qu'un robot tourne, l'agent reste vu en ligne par le site (Amont ne lui confie rien d'autre)."""
    while not arret.wait(20):
        try:
            appel(base, "/robot/prendre", {"agent": nom, "version": VERSION, "info": "robot en cours"})
        except (urllib.error.URLError, OSError):
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Agent du poste Amont : exécute les robots lancés depuis le site")
    ap.add_argument("--amont", default=AMONT_DEFAUT)
    ap.add_argument("--nom", default=platform.node() or "poste")
    ap.add_argument("--intervalle", type=float, default=5)
    args = ap.parse_args()
    base = args.amont.rstrip("/")
    for script, _ in ROBOTS.values():
        if not script.exists():
            print(f"Robot introuvable : {script}. Lancer l'agent depuis le dossier Amont.")
            return 1
    VERROU.parent.mkdir(parents=True, exist_ok=True)
    try:  # une seule instance par poste
        fd = os.open(VERROU, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        try:
            ancien = int(VERROU.read_text().strip())
            os.kill(ancien, 0)
            print(f"Un agent tourne déjà sur ce poste (processus {ancien}).")
            return 1
        except (ValueError, OSError):
            VERROU.write_text(str(os.getpid()))  # verrou d'un agent arrete brutalement
    print(f"Agent Amont {VERSION} « {args.nom} » relié à {base}. Ctrl+C pour arrêter.", flush=True)
    print("En attente de robots lancés depuis le site (fiche d'une demande RTE étude exploratoire).", flush=True)
    joignable = None
    try:
        while True:
            try:
                rep = appel(base, "/robot/prendre", {"agent": args.nom, "version": VERSION, "info": platform.platform()})
                if joignable is not True:
                    dire("Amont joignable.")
                joignable = True
            except (urllib.error.URLError, OSError) as e:
                if joignable is not False:
                    dire(f"Amont injoignable ({e}). Tailscale est-il connecté ? Nouvel essai toutes les 30 s.")
                joignable = False
                time.sleep(30)
                continue
            t = (rep or {}).get("tache")
            if t:
                arret = threading.Event()
                threading.Thread(target=battement, args=(base, args.nom, arret), daemon=True).start()
                try:
                    Execution(base, t).lancer()
                finally:
                    arret.set()
            else:
                time.sleep(args.intervalle)
    except KeyboardInterrupt:
        print("\nAgent arrêté.")
        return 0
    finally:
        try:
            VERROU.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
