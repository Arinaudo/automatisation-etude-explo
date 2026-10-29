# Amont, registre des raccordements : premier test en local

Note du 18/09/2026. Première version (0.1.0) du site décrit dans le cahier des charges du 17/09 : registre SQLite, API FastAPI, front à une page, courriel du matin, import du registre existant. Pas encore de robots ni de générateur D2 : les boutons correspondants annoncent ce qu'ils feront.

---

## 1. Contenu du dossier

| Fichier | Rôle |
|---|---|
| `amont_core/regles.py` | Filières, statuts, échéances, alertes, article 105. Sans dépendance, partagé par tout le reste |
| `amont_core/stockage.py` | Base SQLite : projets, demandes, pièces, journal, notifications |
| `amont_core/alertes.py` | Composition du courriel du matin et règle de renvoi |
| `amont_core/api.py` | Routes HTTP, dépôt de pièces, export Excel, service du front |
| `static/index.html` | Le site, une seule page, sans dépendance hors polices Google |
| `2026_09_18_amont_serveur.py` | Lance le serveur |
| `2026_09_18_amont_import.py` | Charge l'amorce, le registre du 03/09 et les PDF d'études |
| `2026_09_18_amont_alertes.py` | Courriel du matin, avec mode aperçu |
| `2026_09_18_amont_amorce.json` | Les 6 projets et 9 demandes du registre au 10/09 |
| `requirements.txt` | fastapi, uvicorn, python-multipart, openpyxl |

La base et les pièces vont dans `donnees/` (créé au premier lancement, exclu de git), la configuration SMTP dans `.env` (jamais versionné).

---

## 2. Mise en route, une fois

```
cd Amont
pip install -r requirements.txt
python 2026_09_18_amont_import.py
python 2026_09_18_amont_import.py --etudes "..\Etudes exploratoires RTE"
```

La deuxième commande d'import copie les cinq PDF d'études RTE dans `donnees/raccordement/<projet>/rte_ee/` et les rattache aux demandes par leur numéro d'étude. L'import est rejouable : ce qui existe déjà est ignoré.

---

## 3. Lancer et tester

```
python 2026_09_18_amont_serveur.py
```

Puis ouvrir http://localhost:8000. La documentation interactive de l'API est sur http://localhost:8000/api/docs.

Parcours de test conseillé, dans l'ordre du cahier des charges :

1. Tableau de bord : la matrice montre les six projets, AI-Valley avec ses quatre demandes.
2. Ouvrir AIV-600-PTF, saisir une date de dépôt et une date de recevabilité, passer l'étape à « PTF en instruction », enregistrer : l'échéancier affiche la remise de la PTF à 3 mois, le journal enregistre chaque champ.
3. Tenter de passer AIV-600-PTF à « Déposé » sans pièce : refus, avec la liste des pièces manquantes (unifilaire, preuve de virement). Déposer deux PDF avec ces types, réessayer.
4. Ouvrir la fiche projet AI-Valley : échéancier fusionné des quatre filières, pièces, journal.
5. Courriel du matin : l'aperçu montre ce qui partirait. Sur une base fraîche, rien ne part.
6. Exporter en Excel : deux onglets, demandes et échéances.

Pour voir le site depuis un autre poste du réseau interne : `python 2026_09_18_amont_serveur.py --hote 0.0.0.0`, puis http://<adresse du poste>:8000.

---

## 4. Identité des auteurs

En local, chaque modification est journalisée au nom de « interne ». Derrière Cloudflare Access, l'API lit l'adresse e-mail dans l'en-tête `Cf-Access-Authenticated-User-Email` et la journalise. Pour simuler en local, un client peut poser l'en-tête `X-Amont-Auteur`.

Un robot signale son origine avec l'en-tête `X-Amont-Origine: robot`. Il peut lire `GET /api/demandes/{id}/payload` et modifier une demande, mais l'API lui refuse le passage à « déposé ».

---

## 5. Courriel du matin

```
python 2026_09_18_amont_alertes.py --apercu
```

n'envoie rien. Sans `--apercu`, le script lit `.env` (voir l'en-tête du script pour les variables), envoie un seul courriel aux destinataires et marque les alertes envoyées. Règle de renvoi : une alerte déjà signalée n'est renvoyée que si elle passe en dépassement, ou tous les 7 jours tant qu'elle reste dépassée. À planifier à 8 h.

---

## 6. Vers le serveur interne

Rien à changer dans le code. Sur le serveur : `pip install -r requirements.txt`, variables `AMONT_DB`, `AMONT_FICHIERS`, `AMONT_URL` (l'adresse publique, utilisée dans les liens du courriel), service systemd ou conteneur lançant `uvicorn amont_core.api:app --host 127.0.0.1 --port 8000`, tunnel Cloudflare vers ce port, politique Access sur les deux adresses. Sauvegarde nocturne de `donnees/`.

---

## 7. Choix faits et points ouverts

SQLite plutôt que PostgreSQL. Jours fériés ignorés dans les jours ouvrés. Validité du devis GRDF fixée à 3 mois en attendant de la lire sur une offre réelle. Pièces obligatoires avant dépôt : extrait cadastral pour RTE EE, unifilaire et preuve de virement pour RTE PTF, permis pour Enedis, rien pour GRDF ; liste modifiable dans `regles.py`. Les champs de date s'affichent au format du navigateur.

Étapes suivantes selon la note du 10/09 : générateur de fiche D2 et brouillon Outlook, relevé du formulaire GRDF, Enedis après ouverture du compte, bascule du robot D1 sur l'API.
