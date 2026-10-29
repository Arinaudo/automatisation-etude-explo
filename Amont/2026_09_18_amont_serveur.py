"""Lance le serveur Amont en local.

    python 2026_09_18_amont_serveur.py                  # http://localhost:8000
    python 2026_09_18_amont_serveur.py --port 8080
    python 2026_09_18_amont_serveur.py --hote 0.0.0.0   # visible sur le reseau interne

Variables d'environnement facultatives : AMONT_DB, AMONT_FICHIERS, AMONT_URL, AMONT_ENSEIGNE
(voir amont_core/api.py). Sur le serveur interne, ce script est lance par systemd ou Docker,
derriere le tunnel Cloudflare.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    ap = argparse.ArgumentParser(description="Serveur Amont")
    ap.add_argument("--hote", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--recharger", action="store_true", help="rechargement automatique en developpement")
    args = ap.parse_args()

    import uvicorn

    print(f"Amont : http://{args.hote}:{args.port}   (API : /api/docs)")
    uvicorn.run("amont_core.api:app", host=args.hote, port=args.port, reload=args.recharger, log_level="info")


if __name__ == "__main__":
    main()
