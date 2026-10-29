# Amont 0.4 : démarrer les tests d'automatisation

Note du 26/10/2026. Contient la mise à jour du serveur (0.3 et 0.4 ensemble), le chargement de Sochaux et
la progression des tests du robot D1, du banc d'essai jusqu'au vrai portail RTE.

---

## 1. Ce que la 0.4 ajoute

| Élément | Où |
|---|---|
| Icône du site (pylône orange) | onglet du navigateur |
| Onglet actif encadré en orange | barre du haut |
| Case « Vous » : votre nom signe commentaires, vérifications et modifications | en haut à droite, retenu par le navigateur |
| Commentaires et points à vérifier | fiche projet, fiche demande |
| ⚑ à côté de chaque champ de la fiche identité : signaler un champ à faire vérifier | Sites, fiche du site |
| Page **À vérifier** : tous les points ouverts, « Vérifié » avec réponse | menu, compteur orange |
| Page **Documents** : formulaire, modèle ou lien d'origine par opérateur et par étape | menu ; rappelés sur chaque demande selon son étape |
| Bloc **Robot D1** sur les demandes RTE EE : prêt ou non, ce qui manque, commandes à copier, les 27 saisies prévues | fiche de la demande |
| Deux champs de fiche pour la D1 : éléments complémentaires (1000 car.), puissance de mise en sécurité | fiche identité, groupe Électricité |

Le collaborateur qui vérifie passe par **À vérifier** ou par le compteur « ⚑ n à vérifier » sous le nom du site
dans le tableau de bord. Pour lui ouvrir le site, il faut l'ajouter au tailnet (ou passer plus tard par
Cloudflare Access sur le serveur interne).

Les liens de la page Documents portent leur date de vérification. Ceux sans date restent à tester :
bouton « Lien OK » pour dater, « Joindre » pour déposer un modèle (la fiche D2 vierge, par exemple).

## 2. Mise à jour du serveur

Depuis PowerShell :

```powershell
$src = "C:\Castignac\Codes castignac(archive nicolas)\Automatisation étude explo\Amont"
$vm = "alexis@100.116.240.111"
scp -r "$src\amont_core" "$src\static" "${vm}:~/amont/"
scp "$src\docker-compose.yml" "$src\amont_config.json" "${vm}:~/amont/"
```

Sur la VM :

```bash
cd ~/amont && cp donnees/amont.sqlite donnees/amont_avant_0.4.sqlite && docker compose up -d --build && sleep 5 && curl -s localhost:8010/api/sante ; echo
```

Attendu : `"version":"0.4.0"`. Les nouvelles tables se créent seules, les 15 documents de départ aussi.

## 3. Préparer le poste

```powershell
pip install selenium
cd "C:\Castignac\Codes castignac(archive nicolas)\Automatisation étude explo\Amont"
python 2026_10_26_amont_robot_d1.py --verifier
```

Attendu : Amont joignable (Tailscale connecté) et Selenium installé. Selenium télécharge seul le pilote de Chrome.

## 4. Charger Sochaux

```powershell
python 2026_10_26_amont_amorce_sochaux.py
```

Crée le site SOC et la demande SOC-EE à partir de la note du 08/10, avec les 10 parcelles de l'étude de faisabilité
(Sochaux et Exincourt), et récupère l'extrait du plan cadastral officiel sur cadastre.gouv.fr (voir
`2026_10_27_amont_extraits_cadastraux.md`). Si cadastre.gouv.fr ne répond pas, `Plan_cadastre_sochaux.pdf` est joint à la
place. Les valeurs importées sont « à vérifier » : relire la fiche sur le site, utiliser ⚑ pour ce qui doit être confirmé,
valider le reste.

## 5. Tester le robot, dans cet ordre

| Étape | Commande | Ce qui se passe |
|---|---|---|
| 1. Simulation | `--demande SOC-EE --simulation` | Affiche les 27 saisies prévues et ce qui manque. Aucun navigateur |
| 2. Banc d'essai | `--demande SOC-EE --banc` | Remplit l'imitation locale du formulaire (`robot_banc/`). Journal des saisies en bas de page. Amont non modifié |
| 3. Portail, étapes 1 et 2 | `--demande SOC-EE --jusqua 2 --pause` | Vrai portail RTE, s'arrête après l'étape 2. Amont non modifié |
| 4. Portail complet | `--demande SOC-EE --pause` | Les 4 étapes avec pause entre chacune, arrêt à l'étape 5. SOC-EE passe à « prêt pour validation » |

Toutes les commandes commencent par `python 2026_10_26_amont_robot_d1.py`.

Au premier passage sur le portail, le robot ouvre un Chrome dédié (profil dans `%LOCALAPPDATA%\AmontRobot`) :
se connecter au Portail Services RTE dans cette fenêtre, puis Entrée dans le terminal. Fermer cette fenêtre
Chrome avant de relancer le robot, sinon le profil reste verrouillé.

Rien ne part chez RTE sans vous : le robot n'a aucune fonction d'envoi, refuse tout clic sur un bouton d'envoi et
ne touche pas à la certification. Le portail ne garde pas de brouillon, donc un test interrompu ne laisse aucune trace.
Captures de chaque étape dans `robot_captures/`.

Après l'envoi à la main : passer SOC-EE à « Déposé » avec la date du jour. Les échéances démarrent de là.

## 6. Si le robot s'arrête

Le message dit quel champ il n'a pas trouvé. Les causes probables sur le vrai portail :

| Message | Piste |
|---|---|
| champ ou bouton radio introuvable | libellé de question changé : comparer la capture avec le texte de la question dans `amont_core/d1.py` |
| la liste des communes n'arrive pas | portail lent : relancer ; l'attente est de 15 s |
| date introuvable dans le calendrier | libellés aria du calendrier changés : capture à envoyer |
| Chrome n'a pas démarré | fenêtre Chrome du robot encore ouverte |

Sur le banc d'essai, deux défauts ont déjà été corrigés avant votre premier test : la recherche des champs à libellé
court (Latitude, Longitude) et les mois accentués du calendrier (février, août, décembre), qui auraient bloqué sur le
vrai portail.
