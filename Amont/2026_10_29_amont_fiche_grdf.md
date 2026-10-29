# Amont 0.10 : fiche GRDF Grands Projets

Note du 29/10/2026.

Le gaz commence toujours par la fiche de renseignements « Grands Projets » de GRDF, même sans réseau à proximité du site ou quand le besoin dépasse les limites de GRDF : GRDF redirige ensuite vers NaTran. Amont n'aiguille donc plus selon le débit. La fiche est un PDF à champs, envoyé par courriel : le formulaire public GRDF n'est pas utilisé pour les datacenters, et il n'y a pas de robot.

## Ce que fait Amont

Sur une demande GRDF, bloc « Fiche GRDF Grands Projets et courriel » :

- **Générer la fiche GRDF** remplit le PDF depuis la fiche du site (nom `AAAA_MM_JJ_fiche_GRDF_CODE.pdf`, type de pièce `fiche_grdf`). 125 champs et cases sont remplis : demandeur, signataire, interlocuteur du site, adresses, parcelles, dates, pièces fournies, destination datacenter, puissances, consommations, pression, double ligne, redondance, augmentation prévue, poste et tranchées, tableau des années 1 à 10, solutions techniques.
- Le contact GRDF du modèle (Jean-Baptiste Jedrusko), les libellés et le logo sont conservés.
- Un champ requis vide sort « à compléter ». Un point à vérifier liste ce qui manque.
- **Courriel d'envoi** : brouillon `.eml` non envoyé (`X-Unsent`) avec les pièces. Vous relisez, vous envoyez. Destinataire par défaut : l'interlocuteur Grands Projets ; pour le changer, `"grdf_destinataires": [...]` dans `amont_config.json`.
- **Tout préparer** crée la demande GRDF si elle manque et génère la fiche.
- Les pièces déjà rangées avec l'étude exploratoire RTE (plan de situation, extrait cadastral, Kbis) sont reprises pour GRDF sans les redéposer.

## Ce qui reste à faire à la main

1. Relire la fiche, puis la **signer** page 2 (nom, date, signature, cachet).
2. Déposer le PDF signé dans les pièces, type « fiche grdf », avec « signee » dans le nom : Amont préfère alors cette version à la version générée.
3. Joindre le plan de situation avec l'emplacement du poste gaz, et le plan cadastral **portrait au 1/1000e** (cadastre.gouv.fr, « outils avancés »). L'extrait que génère Amont pour RTE n'a pas cette échelle : le courriel le signale.
4. Envoyer le courriel, puis passer la demande à « Envoyée ».
5. Si GRDF redirige vers NaTran : passer la demande à « Redirigé vers NaTran » et activer la filière dans `amont_config.json` (`"filieres_optionnelles": ["natran"]`).

## Nouveaux champs de la fiche du site

Groupe Demandeur : code NAF, interlocuteur du site ou chantier (nom, fonction, téléphone, portable, courriel).
Groupe Foncier et urbanisme : numéro de lot de la ZAC.
Groupe Gaz : dénomination du bâtiment, texte de présentation, dates de mise en service et de mise en place du poste, puissance installée (kW PCS), puissances minimale et maximale (MWPCS), consommations annuelle et journalière, pression, poste double ligne, redondance, augmentation prévue (puissance, date, usage), domaine du poste, tranchées, solutions techniques, tableau années 1 à 10 (`25800/12400 ; 51600/24800 ; ...`).

La puissance maximale se calcule depuis le débit maximal (PCS 11,2 kWh/m3(n)) si elle n'est pas saisie. Déposer une fiche GRDF déjà remplie dans les sources du site propose ces valeurs.

## Vérification

Les valeurs de la fiche OM01 saisies à la main ont été rejouées dans le générateur : les 124 champs et cases sont identiques au PDF fait à la main. Seul le texte de présentation diffère (coupé aux mots pour tenir dans la case). Tests : `python tests/test_grdf.py`.

## Mise à jour du serveur

Recopier `amont_core`, `static`, `docker-compose.yml` et `requirements.txt` (pypdf 6.17 ou plus), puis `docker compose up -d --build`. Attendu : `"version":"0.10.0"`. Ne pas recopier `donnees/`.

La page Documents d'une base existante n'est pas modifiée : ajouter le modèle de fiche GRDF depuis la page si besoin.

## Pas encore fait

- Aucune demande NaTran créée automatiquement à la redirection.
- Lecture des réponses de GRDF (comme pour les études RTE et les PTF) : à faire quand une réponse réelle sera déposée.
- Le délai de réponse de GRDF Grands Projets n'est pas connu : seule une relance à 15 jours est calculée.
