# Amont 0.6 : IA locale

Note du 27/10/2026. L'extraction des fichiers et la rédaction des textes passent par un modèle qui tourne sur une
machine de l'entreprise : aujourd'hui l'Ollama du serveur perso pour les tests, demain le serveur interne à RTX 5090.
Aucun document ne sort.

---

## 1. Ce que fait l'IA

| Où | Quoi | Modèle |
|---|---|---|
| Dépôt d'un fichier dans les sources d'un site | Complète la fiche identité : les règles d'abord, l'IA ajoute ce qu'elles n'ont pas trouvé | qwen3:8b |
| Scan, plan, photo (PDF sans texte, image) | Pages rendues en images (4 au plus) et lues par le modèle de vision | gemma3:12b |
| Fiche du site, champs « Contexte du projet » et « Éléments complémentaires D1 » | Lien « rédiger avec l'IA » : texte de la D1 rédigé depuis la fiche, 500 et 1000 caractères au plus | qwen3:8b |

Garde-fous, pour qu'un petit modèle ne fasse pas entrer d'erreur dans un dossier :
- chaque valeur extraite doit se lire dans le document (valeur ou phrase citée) : sinon elle est **écartée** ;
- une valeur différente de celle déjà dans la fiche n'écrase rien : elle va dans « Valeurs divergentes » ;
- tout ce que l'IA remplit est « à vérifier » (surligné) jusqu'à validation ;
- un texte rédigé ne dépasse jamais la limite du portail (coupé à la dernière phrase entière) ; un nombre qui n'est
  pas dans la fiche est signalé (« nombres à vérifier »).

## 2. Réglages

Dans `docker-compose.yml` (déjà rempli pour le home server) :

| Variable | Home server (tests) | Serveur interne, plus tard |
|---|---|---|
| `AMONT_IA_API` | `ollama` | `ollama`, ou `openai` si le modèle est servi par vLLM |
| `AMONT_IA_URL` | `http://127.0.0.1:11434` | adresse du service de modèle |
| `AMONT_IA_MODELE` | `qwen3:8b` | modèle texte plus gros (choix à tester sur vos dossiers) |
| `AMONT_IA_MODELE_VISION` | `gemma3:12b` | modèle de vision |
| `AMONT_IA_CONTEXTE` | `16384` | 32768 ou plus selon la mémoire de la carte |
| `AMONT_IA_DELAI` | `900` (processeur, lent) | 120 |

`AMONT_IA=non` coupe l'IA : les règles seules s'appliquent, comme avant.

Le conteneur passe en **réseau de l'hôte** : il joint Ollama sur 127.0.0.1 sans qu'Ollama soit ouvert au réseau, et
écoute lui-même sur 127.0.0.1:8010, l'adresse que Caddy proxifie déjà. Rien à changer dans le Caddyfile.

## 3. Vitesse attendue

Le home server n'a pas de carte graphique dédiée : le modèle tourne sur le processeur. Compter 1 à 4 minutes pour
une étude de faisabilité de 28 pages, 1 à 2 minutes pour la rédaction d'un texte, plus au premier appel (chargement
du modèle). C'est suffisant pour les tests ; sur la RTX 5090 ce sera de l'ordre de la dizaine de secondes. L'extraction
tourne en tâche de fond, le site affiche « lecture… » pendant ce temps.

## 4. Mise à jour du serveur et premier test

Depuis PowerShell :

```powershell
$src = "C:\Castignac\Codes castignac(archive nicolas)\Automatisation étude explo\Amont"
$vm = "alexis@100.116.240.111"
scp -r "$src\amont_core" "$src\static" "${vm}:~/amont/"
scp "$src\docker-compose.yml" "$src\Dockerfile" "$src\requirements.txt" "$src\amont_config.json" "$src\2026_10_27_amont_extraits_cadastraux.py" "$src\2026_10_27_amont_tester_ia.py" "${vm}:~/amont/"
```

Sur la VM :

```bash
cd ~/amont && cp donnees/amont.sqlite donnees/amont_avant_0.6.sqlite && docker compose up -d --build && sleep 5 && curl -s localhost:8010/api/sante ; echo
docker compose exec amont python 2026_10_27_amont_tester_ia.py
```

Le test affiche les réglages, vérifie que les deux modèles sont présents, mesure une réponse courte et rédige un
commentaire D1 sur une fiche type Sochaux. Pour tester l'extraction sur un vrai fichier déjà déposé :

```bash
docker compose exec amont python 2026_10_27_amont_tester_ia.py --fichier donnees/sources/SOC/<fichier>.pdf
```

Puis sur le site : déposer l'étude de faisabilité de Sochaux dans les sources du site SOC, attendre la fin de la
lecture, regarder les valeurs « à vérifier » et les divergences.

## 5. Si ça ne marche pas

| Message | Piste |
|---|---|
| serveur du modèle injoignable | Ollama arrêté (`systemctl status ollama`), ou il tourne dans un conteneur sans port publié sur l'hôte |
| modèle absent du serveur | `ollama pull qwen3:8b` (ou le nom exact affiché par `ollama ls`) |
| trop lent, « injoignable ou trop lent » | augmenter `AMONT_IA_DELAI`, ou prendre `qwen3:4b` pour les essais |
| valeurs écartées en nombre | le modèle invente : c'est le garde-fou qui travaille. Essayer un modèle plus gros |

## 6. Technique

`amont_core/ia.py` : client unique (Ollama natif, compatible OpenAI, Claude pour mémoire), bibliothèque standard.
Sur Ollama : taille de contexte imposée (sinon il tronque sans prévenir), sortie JSON contrainte par un schéma
(liste fermée des champs de la fiche), raisonnement coupé pour qwen3. `amont_core/redaction.py` : textes de la D1, avec
les textes écrits à la main pour Sochaux comme modèles de ton. `amont_core/extraction.py` : règles puis IA, découpage
des longs documents, garde-fou de présence dans le texte. Correction au passage : les règles ne prennent plus le SIRET
d'un extrait cadastral, d'une étude RTE ou d'un PLU pour celui du demandeur.
