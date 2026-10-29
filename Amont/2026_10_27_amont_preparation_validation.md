# Amont 0.7 : tout préparer, plan de situation, validation à deux clés

Note du 27/10/2026.

---

## 1. « Tout préparer » (fiche du site)

Bouton en haut de la fiche d'un site. Enchaîne, en tâche de fond, avec un suivi étape par étape :

| Étape | Ce qui se passe |
|---|---|
| Demande RTE étude exploratoire | créée et pré-remplie depuis la fiche si elle n'existe pas (sauf si la filière est « sans objet ») |
| Lecture des fichiers | attend la fin de la lecture des fichiers déposés (règles et IA) |
| Extrait du plan cadastral | récupéré sur cadastre.gouv.fr et joint, s'il manque |
| Plan de situation et plan de l'installation | idem, puis assemblage du plan de l'installation de la D1 |
| Textes de la D1 | rédigés par l'IA locale s'ils sont vides, à relire |
| Bilan | valeurs à vérifier, divergences, formulaire D1 complet ou non, état de la validation, prochaine action |

Une étape en échec (cadastre indisponible, IA éteinte) n'arrête pas les suivantes. Rejouable : ce qui est déjà fait
est sauté. Compter 1 à 5 minutes selon le cadastre et l'IA.

Le parcours type devient : créer le site, déposer les fichiers, renseigner ou vérifier les parcelles, « Tout préparer »,
relire les valeurs surlignées, demander la validation, robot D1, dernier clic.

## 2. Plan de situation et plan de l'installation

- **Plan de situation DGFiP** (cadastre.gouv.fr) : contrairement à l'extrait, il dessine toutes les communes sur une page
  (limites, sections, cours d'eau). 1/5000 au plus, limite du service. Bloc « Plan de situation » de la fiche du site,
  ou bouton sur la demande RTE EE.
- **Plan de l'installation** : le portail RTE n'a qu'un emplacement PDF (2 Mo) pour le plan de situation, le plan
  d'implantation et l'unifilaire. Amont fusionne la dernière version de chacun, dans cet ordre, en un seul PDF joint
  comme « plan de l'installation », que le robot dépose à l'étape 4. Réassemblé à chaque nouveau plan de situation ;
  bouton « Assembler le plan de l'installation » après dépôt d'un plan d'implantation ou d'un unifilaire (nouveaux types
  de pièces : plan de situation, plan d'implantation).

## 3. Validation à deux clés

Tu prépares, Brayane valide, puis le dernier clic. Bloc « Validation du responsable » sur la fiche de chaque demande
pas encore envoyée.

| Étape | Qui | Effet |
|---|---|---|
| Demander la validation | toi | fige l'empreinte du dossier, crée un point dans « À vérifier » |
| Valider ou refuser | Brayane (liste `valideurs` de amont_config.json) | refus : motif obligatoire, remonte en prochaine action |
| Modification après validation | n'importe qui | la validation devient **périmée** : à redemander |

L'empreinte couvre ce qui part chez l'opérateur : les valeurs de la fiche utiles à la filière, les textes de la D1, les
champs de la demande (hors dates de suivi) et les pièces jointes. Ajouter une pièce ou changer la puissance après la
validation la périme : ce que Brayane a validé est exactement ce qui part.

Sans validation à jour :
- le robot D1 refuse de remplir le vrai portail jusqu'au bout (le banc d'essai et `--jusqua 3` restent possibles pour
  la mise au point) ;
- la demande ne peut pas passer à « Déposé ».

Pour valider, Brayane choisit son nom dans la case « Vous » (Brayane suffit). Le jour où l'outil passe derrière
Cloudflare Access, mettre son adresse dans `valideurs`. Pour couper la règle : `"validation_requise": false`.

## 4. Mise à jour du serveur

Depuis PowerShell :

```powershell
$src = "C:\Castignac\Codes castignac(archive nicolas)\Automatisation étude explo\Amont"
$vm = "alexis@100.116.240.111"
scp -r "$src\amont_core" "$src\static" "${vm}:~/amont/"
scp "$src\docker-compose.yml" "$src\amont_config.json" "${vm}:~/amont/"
```

Sur la VM :

```bash
cd ~/amont && cp donnees/amont.sqlite donnees/amont_avant_0.7.sqlite && docker compose up -d --build && sleep 5 && curl -s localhost:8010/api/sante ; echo
```

Attendu : `"version":"0.7.0"`. La table des validations se crée seule. Le robot (sur ton poste) est aussi mis à jour :
rien à faire, il est dans le dossier Amont.
