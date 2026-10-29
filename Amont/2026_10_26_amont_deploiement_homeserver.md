# Amont : deploiement sur le home server (usage personnel)

Note du 26/10/2026. Amont 0.2 en conteneur Docker sur la VM ubuntu-docker, accessible
uniquement depuis le tailnet a l'adresse https://amont.arinaudo.fr (Caddy + Tailscale).
Pas de tunnel Cloudflare : rien n'est expose sur Internet. Le site n'a pas de login,
c'est Tailscale qui fait office de controle d'acces.

## Fichiers ajoutes

| Fichier | Role |
|---|---|
| Dockerfile | Image python:3.12-slim + poppler-utils, lance uvicorn sur le port 8000 |
| docker-compose.yml | Service `amont`, volume `./donnees`, port publie sur 127.0.0.1:8010 |
| .dockerignore | Exclut la base, le .env, les caches et les notes |

## Donnees

`donnees/` (base SQLite + pieces) est montee depuis la VM : elle survit aux reconstructions.
La copie initiale reprend la base locale du poste (6 projets, 9 demandes, 5 etudes RTE).
Les tables de la 0.2 (sources, fiche) se creent au premier demarrage.

## Mise a jour du code plus tard

Recopier les dossiers `amont_core` et `static` sur la VM, puis
`docker compose up -d --build`. Ne jamais recopier `donnees/` par-dessus celle de la VM.

## Sauvegarde

`tar czf ~/sauvegardes/amont_$(date +%Y_%m_%d).tar.gz -C ~/amont donnees`
a planifier en cron (le fichier SQLite est petit).

## Emplacement sur la VM

`/home/alexis/amont`, comme les autres projets compose. Caddy (`/home/alexis/caddy`, reseau host)
proxifie `amont.arinaudo.fr` vers `localhost:8010`.

## Mise en ligne du 26/10/2026

En ligne sur https://amont.arinaudo.fr (certificat Let's Encrypt obtenu par DNS-01).
Piege rencontre : le Caddyfile est monte en fichier unique ; apres ajout du bloc, le conteneur
voyait encore l'ancienne version ("config is unchanged"). Correctif : `docker compose restart caddy`.
Pour eviter ca : editer avec `cat >>` ou `nano`, ou monter le dossier `~/caddy` entier.
