# Amont : relevé de la boîte Outlook (Microsoft 365)

Note du 29/10/2026. Le script `2026_10_29_amont_releve_outlook.py` lit les boîtes Outlook `@castignac.com` et dépose les échanges avec RTE, Enedis, GRDF et NaTran dans le CRM d'Amont. Lecture seule : rien n'est envoyé, déplacé ni supprimé dans Outlook.

## Ce que fait le relevé

- Il lit la boîte de réception et les éléments envoyés, sur les 30 derniers jours au premier passage.
- Un message est retenu s'il a un correspondant externe et que (a) ce correspondant est chez `rte-france.com`, `enedis.fr`, `grdf.fr`, `natrangroupe.com`, `natran.com` ou `grtgaz.com`, ou (b) l'objet ou l'aperçu contient un code connu d'Amont (code de demande comme OM01-GAZ, numéro d'étude, numéro de dossier). Les échanges internes `@castignac.com` sont ignorés.
- Chaque message retenu est téléchargé en `.eml` complet et déposé sur `/api/echanges/eml`, comme un glisser-déposer : rattachement à la demande, clôture des attentes de réponse, étude RTE en pièce jointe rangée et lue, doublons ignorés.
- Les messages sont traités du plus ancien au plus récent, tous dossiers confondus. Un courriel envoyé déposé après sa réponse est clos d'emblée (correctif du stockage, vaut aussi pour les dépôts manuels).
- Un message qu'Amont ne sait pas rattacher à un projet est noté « non rattaché » dans le journal du script et n'est pas repris : le déposer à la main depuis la fiche du projet.

## Inscription de l'application (Entra ID), à faire une fois

Rôle suffisant : administrateur des applications cloud. Le relevé utilise un droit **délégué** (`Mail.Read`) : chaque utilisateur lit sa propre boîte. Un droit d'application demanderait un administrateur général, ce n'est pas nécessaire.

1. Centre d'administration Entra, Applications, Inscriptions d'applications, **Nouvelle inscription**.
2. Nom : `Amont relevé courrier`. Types de comptes : **ce répertoire uniquement** (locataire unique).
3. URI de redirection : plateforme « Client public (mobile et bureau) », valeur `http://localhost` (nécessaire seulement pour l'option `--navigateur`).
4. Après création, relever **l'ID d'application (client)** et **l'ID de l'annuaire (locataire)**.
5. Authentification, « Paramètres avancés » : **Autoriser les flux de clients publics = Oui**. Sans cela, la connexion par code est refusée.
6. Autorisations d'API, Ajouter, Microsoft Graph, **Autorisations déléguées** : `Mail.Read` (et `User.Read`, déjà présent). Pas d'autorisation d'application.
7. **Accorder le consentement administrateur** pour le locataire (ou laisser chaque utilisateur consentir si la politique du locataire l'autorise).
8. Si un accès conditionnel bloque le flux par code, essayer `--navigateur` ; sinon ajouter les deux comptes ou le poste à une exception.

## Mise en route sur chaque poste

```bash
pip install msal
```

Dans `amont_config.json`, ajouter :

```json
"outlook": {
  "tenant_id": "ID de l'annuaire",
  "client_id": "ID d'application",
  "amont_url": "https://amont.arinaudo.fr"
}
```

Premier essai, sans rien déposer :

```bash
python 2026_10_29_amont_releve_outlook.py --simulation
```

Le script affiche un code à saisir sur https://microsoft.com/devicelogin : se connecter avec son compte `@castignac.com`. Il liste ensuite les messages qu'il déposerait. Le jeton est gardé dans `%LOCALAPPDATA%\AmontOutlook` et se renouvelle seul.

Passage réel, puis en boucle :

```bash
python 2026_10_29_amont_releve_outlook.py
python 2026_10_29_amont_releve_outlook.py --boucle 10
```

Chaque personne lance le script sur son poste avec son compte : les deux boîtes alimentent le même Amont. L'auteur noté dans le journal est `outlook:` suivi du nom d'utilisateur Windows. Pour qu'il tourne en continu, y mettre un raccourci dans `shell:startup` comme pour l'agent du poste, ou une tâche planifiée.

Réglages facultatifs du bloc `outlook` : `domaines` (remplace la liste des domaines suivis), `depuis_jours` (30 par défaut), `auteur`.

## Limites

- Non essayé sur une vraie boîte : le code est testé avec un faux Graph et la vraie API d'Amont (`python tests/test_releve_outlook.py`). Le premier `--simulation` sert de vérification.
- Les messages chiffrés ou protégés par une étiquette de confidentialité peuvent ne pas se télécharger en `.eml` lisible.
- Le contenu des réponses de GRDF n'est pas lu : la redirection vers NaTran reste à signaler à la main (bouton « Ouvrir la demande NaTran »).
