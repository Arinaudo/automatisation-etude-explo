# Amont 0.3 : suivi des dossiers et des échanges

Note du 26/10/2026. Ajoute à Amont 0.2 le suivi des dossiers par site et un espace Mails.
Le relevé automatique de la boîte mail n'est pas branché : le backend reste à choisir.

---

## 1. Le tableau de bord : une ligne par site

Chaque case opérateur affiche l'étape, la **prochaine action** et l'échéance, plus « ✉ sans réponse N j »
quand un envoi attend une réponse. Dernière colonne : le dernier échange du site.

Une filière qui ne concerne pas un site (pas de gaz, pas d'Enedis) se marque **sans objet** sous la case vide,
avec un motif facultatif. « Remettre à suivre » l'annule.

## 2. La prochaine action

Calculée pour chaque demande, dans cet ordre de priorité :

| Priorité | Cas | Exemple |
|---|---|---|
| 1 | Action saisie à la main sur la fiche de la demande | « Attendre le retour de Brayane sur la date » |
| 2 | Échéance dépassée | « Relancer RTE par écrit, en visant l'article 1.2.2 » |
| 3 | Envoi sans réponse depuis 10 jours ou plus | « Relancer Jean Dupont, sans réponse depuis 12 jours » |
| 4 | Date de relance atteinte sur un envoi | « Relance prévue : Question sur la solution 225 kV » |
| 5 | Action de l'étape, avec les pièces manquantes | « Compléter la D1 et la déposer sur le Portail RTE · manque : extrait cadastral » |

Vider le champ « Prochaine action, à la main » rend la main au calcul. Le délai de relance (10 jours)
se règle dans `amont_config.json` avec la clé `delai_relance_jours`.

## 3. Les échanges

Sur chaque fiche de demande, chaque fiche projet et la page **Mails** : « + Ajouter un échange ».

| Champ | Rôle |
|---|---|
| Sens | Envoyé, Reçu ou Note (appel, réunion) |
| Canal | Courriel, téléphone, portail, courrier, réunion |
| J'attends une réponse | Coché par défaut sur un envoi. L'envoi apparaît « sans réponse » jusqu'à la réponse |
| Relancer le | Date à laquelle la relance remonte dans la prochaine action |

Un échange **reçu** sur une demande clôt automatiquement les attentes ouvertes de cette demande. Le bouton
« Réponse reçue » les clôt à la main.

**Dépôt de .eml** : dans Outlook web ou le nouvel Outlook, ouvrir le message, menu « … », Télécharger.
Glisser le fichier dans la zone de dépôt. Sont lus : expéditeur, destinataires, date, objet, texte (sans
l'historique cité), pièces jointes (noms). Le sens est deviné à partir de votre adresse. Depuis la page Mails,
la demande est retrouvée si l'objet cite son code (AIV-600), son n° d'étude RTE ou son n° de dossier ; sinon
le site d'après le nom ou la commune, puis l'opérateur d'après l'adresse (rte-france.com, enedis.fr...).
Un même courriel déposé deux fois n'est enregistré qu'une fois. Le .eml est conservé dans
`donnees/raccordement/<site>/courriels/`.

Les alertes « sans réponse » et « relance prévue » partent dans le courriel du matin comme les échéances.

## 4. Contacts

Page **Contacts** : nom, organisation, rôle, courriel, téléphone, filière. Un échange est rattaché tout seul
au contact dont l'adresse correspond. La relance affiche alors son nom.

## 5. Pour le futur backend mail

Point d'entrée : `POST /api/echanges` en JSON (`projet_code` ou `demande_id`, `sens`, `canal`, `date`,
`expediteur`, `destinataires`, `objet`, `resume`, `message_id`), avec l'en-tête `X-Amont-Origine` (ex. `graph`).
Le `message_id` dédoublonne. Sans projet ni demande, l'objet et le résumé sont analysés pour retrouver la demande.

## 6. Export Excel

Colonnes ajoutées : prochaine action, dernier échange, sans réponse depuis. Nouvel onglet « Échanges ».

## 7. Technique

Base : tables `contacts`, `echanges`, `filieres_projet` et colonne `demandes.prochaine_action`, créées seules au
premier démarrage. Une connexion SQLite par thread (les requêtes simultanées du site plantaient avec la connexion
partagée). Nouveau module `amont_core/courriels.py` (lecture .eml, bibliothèque standard seulement).
