# Amont 0.9.1 : relevé du portail Enedis et robot Enedis

28/10/2026. Relevé fait en direct dans le navigateur intégré, session Enedis d'Alexis, commune SOCHAUX. Rien n'a été envoyé et aucune donnée réelle n'a été saisie.

## Le parcours

1. **Accueil** (`raccordement-entreprise-enedis.fr`, « Faire une demande de raccordement ») : commune des travaux, choisie dans une recherche en direct (« SOCHAUX (25600) »), puis « Commencer ».
2. **Type de raccordement** : « Un site industriel en HTA » (consommation, au-delà de 250 kVA), puis « Continuer » dans la fenêtre de confirmation.
   - Ce clic crée un brouillon : l'adresse de la page prend un identifiant de dossier.
   - Consigne du 28/10 : tous nos sites passent par « Un site industriel en HTA », chantier compris. Le besoin de chantier se déclare à l'étape Échéance (« branchement provisoire le temps de votre construction »).
   - « Un local ou un site » n'est donc pas utilisé. Aperçu relevé avant la consigne : on y saisit d'abord la puissance en kVA, ce qui oriente vers le bon formulaire (36 à 250 kVA : liste de 48 à 250 kVA, pas d'usage « Data Center », pas de secours ni de groupes).
3. **Formulaire en 4 étapes** dans la même page : Coordonnées, Construction, Documents, Échéance. Un seul bouton « Suivant » les fait défiler.

Le connecteur « Demande de raccordement » de la page d'accueil Enedis mène à `connect-racco.enedis.fr`, qui passe par la même connexion « Mon compte Enedis ».

## Ce qu'il faut savoir pour automatiser

- **Technique** : application Vue 2.
  - Les attributs `name` et les valeurs des boutons radio sont stables.
  - Les `id` sont tirés au hasard à chaque chargement : le robot cible donc par `name`.
  - Deux champs de la rampe partagent le même `name` (`dureePalier1`, `puissancePalier1`).
- **Champs conditionnels** : ils n'existent qu'après la réponse qui les ouvre. Le plan les remplit dans l'ordre.
- **Communes** : bénéficiaire et accueil se choisissent dans une recherche en direct ; le code postal et le code INSEE se remplissent seuls. L'adresse du chantier reprend la commune de l'accueil.
- **Pracc** : liste fermée en kW, de 500 à 19 500 par pas de 500, puis « Plus de 20000 ».
- **Date de mise en service** : JJ/MM/AAAA tapée, au plus tôt demain.
- **Brouillon** : le portail crée un brouillon dès l'accueil, contrairement au portail RTE. Un essai laisse donc une demande non envoyée dans « Mon suivi de dossier », à supprimer depuis le portail.

## Contenu relevé

**Coordonnées.**

- Type de demande :
  - définitive : avec autorisation d'urbanisme ;
  - anticipée : sans permis, prestation payante, à transformer ensuite auprès d'Enedis.
- Travaux réalisés par Enedis ou en ESSOC (demande définitive seulement).
- Bénéficiaire : statut (entreprise), SIRET, raison sociale, civilité, courriel, nom, prénom, adresse (voie limitée à 33 caractères), commune, téléphone fixe et portable (tous deux obligatoires), notifications.
- Siège social : nom, statut juridique, SIREN, lieu d'immatriculation, **capital**, signataire de la convention (nom, prénom, fonction).
- Tiers mandaté : avec « Oui », le mandat Enedis est à joindre. C'est le cas où Castignac dépose pour la société de projet.
- Envoi des documents contractuels et interlocuteur technique du chantier.

**Construction.**

- Adresse du chantier, dénomination du site, ZAC (nom si oui).
- Nouveau raccordement ou modification (n° PRM).
- Usages : la case « Centre de données / Data Center » existe.
- IRVE, configuration (référence ou autre), Pracc.
- **Rampe sur 10 ans** : 4 paliers de 2 à 3 ans, durée et puissance de chacun.
- Transformateurs (facultatif) : 1, 2 ou plus, avec leurs puissances.
- **Alimentation de secours** : avec « Oui », la puissance demandée.
- Autoproduction.
- Appareils perturbateurs (facultatif).
- **Groupes électrogènes** : nombre (1, 2 ou plus, avec le total et la puissance totale), mode de couplage (normal/secours, fugitif, permanent).
- Qualité d'alimentation : standard ou personnalisée.

**Documents.**

- **Extrait de plan cadastral** (obligatoire), avec section et numéro de parcelle.
- Plan de situation (facultatif).
- **Plan de masse** (obligatoire), avec l'emplacement du poste de livraison accessible 24 h/24.
- Photographie (facultative).
- Autorisation d'urbanisme : oui ou non, avec la copie du permis.
- Jusqu'à 10 documents complémentaires.

**Échéance.**

- Date souhaitée de mise en service.
- Branchement provisoire de chantier.
- Demande particulière (texte libre).

## Dans Amont

- **Plan de saisie** : `GET /api/demandes/{id}/enedis`, avec 57 saisies au maximum. Il est affiché sur la demande Enedis (bloc « Robot Enedis »).
- **Vérification** : chaque cible du plan a été confrontée au portail réel le 28/10. Les 57 existent.
- **Règles de remplissage** :
  - demande définitive si un permis est connu (numéro dans la fiche ou pièce « permis »), sinon anticipée ;
  - Pracc = puissance de la fiche, arrondie à la valeur supérieure de la liste ; au-delà de 40 MW, Amont bloque (c'est RTE) ;
  - secours de même puissance si la fiche prévoit une alimentation supplémentaire ;
  - groupes électrogènes lus dans le champ « Groupes de secours » (« 8 groupes de 2,5 MW ») ;
  - rampe à « Non » par défaut : le format Enedis (4 paliers de 2 à 3 ans) ne recoupe pas notre montée en charge, elle se saisit à la main si on la veut ;
  - branchement provisoire à « Oui » si la fiche a une puissance de chantier, ou si la demande est de type « HTA + chantier » ; la puissance et la date de début de chantier sont ajoutées à la demande particulière.
- **Nouveaux champs de la fiche** : capital social, civilité et portable de l'interlocuteur, ZAC.
- **Nouveaux types de pièces** : `plan_masse`, `photo_environnement`.
- **Pièces obligatoires avant « déposé »** : extrait cadastral et plan de masse. « Récupérer l'extrait cadastral » joint désormais l'extrait aux demandes Enedis en préparation.
- **Type par défaut** : une demande Enedis créée depuis la fiche est désormais de type HTA, et non plus chantier.

## Le robot

`2026_10_28_amont_robot_enedis.py`, lancé à la main ou par l'agent du poste (mis à jour en 0.9.1).

- Il ouvre le portail avec son propre profil Chrome et attend ta connexion si besoin.
- Il passe l'accueil, remplit les 4 étapes et **s'arrête sur l'étape Échéance sans cliquer le dernier « Suivant »**.
- Les clics sur un bouton dont le texte évoque un envoi, une validation, une signature ou un paiement sont refusés.
- Le pré-remplissage complet exige la validation du responsable. L'essai « étape 1 » est libre.
- Il n'y a pas de banc d'essai : l'essai se fait sur le portail, étape par étape.

Premier essai conseillé :

```
python 2026_10_28_amont_robot_enedis.py --demande SOC-ENE --simulation
python 2026_10_28_amont_robot_enedis.py --demande SOC-ENE --jusqua 1 --pause
```

Pour le relevé, « Un local ou un site » n'est plus à faire.

Points non vérifiés tant que le robot n'a pas tourné une fois en vrai, avec les messages d'erreur du portail :

- le format de téléphone accepté (le champ a un sélecteur +33) ;
- les règles de validation propres à chaque étape ;
- l'écran qui suit Échéance.

## Brouillons à supprimer

Le relevé a créé deux brouillons à SOCHAUX, sans données réelles. Supprime-les depuis « Mon suivi de dossier » sur le portail Enedis :

- une demande HTA (dossier `5beb4250…`) ;
- une demande « local ou site » de 240 kVA (dossier `dc471359…`).

## Déploiement

Sur le serveur : mêmes commandes que pour la 0.9, image `amont:0.9.1`.

Sur le PC : remplacer `2026_10_28_amont_agent_poste.py` et ajouter `2026_10_28_amont_robot_enedis.py` dans le dossier Amont, puis relancer l'agent. Un agent 0.9.0 ne prend pas les tâches Enedis.
