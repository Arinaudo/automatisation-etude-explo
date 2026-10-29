# Amont 0.8 : robot lancé depuis le site, lecture des études RTE

Note du 28/10/2026.

---

## 1. Lancer le robot depuis le site

Plus de ligne de commande : sur la fiche d'une demande RTE étude exploratoire, bloc « Robot D1 », trois boutons.

| Bouton | Ce qui se passe |
|---|---|
| Banc d'essai | répétition sur l'imitation locale du formulaire ; Amont n'est pas modifié |
| Portail, étapes 1 et 2 | vrai portail RTE, s'arrête après l'étape 2 ; possible sans validation, pour les essais |
| Pré-remplir le portail RTE | les 4 étapes, arrêt avant la certification ; exige la validation du responsable à jour |

Le serveur ne peut pas ouvrir un navigateur que vous voyez : c'est **l'agent du poste** qui le fait. Il interroge Amont
toutes les 5 secondes, lance le robot dans Chrome sur votre PC, renvoie au site ce que le robot affiche (journal visible
sous les boutons, mis à jour en direct), puis attend la tâche suivante. Le site indique si l'agent est en ligne.

Démarrer l'agent (dossier Amont du poste, Tailscale connecté) : double-clic sur `2026_10_28_amont_agent_poste.bat`,
laisser la fenêtre ouverte (réduite). Pour qu'il démarre avec Windows : Win+R, `shell:startup`, y déposer un raccourci
vers le .bat. Une seule instance par poste.

Connexion au portail RTE : si la session du profil Chrome du robot a expiré, le robot l'affiche dans le journal et
attend (10 minutes au plus) que vous vous connectiez dans sa fenêtre Chrome, puis reprend seul.

Le dernier clic ne change pas : le robot s'arrête avant l'interrupteur de certification, la fenêtre Chrome reste ouverte
pour la relecture, la certification et l'envoi. Fermer cette fenêtre avant de relancer un robot (le profil Chrome est
verrouillé tant qu'elle est ouverte).

## 2. Lecture des études exploratoires RTE

Sur une demande RTE étude exploratoire déposée, bloc « Étude exploratoire reçue » : déposer le PDF de l'étude. Amont
le joint à la demande et le lit :

- numéro et date de l'étude, date de la demande, puissance, domaine de tension, distance « d » et poste de référence ;
- pour chaque solution étudiée : intitulé, tension, coût du raccordement, contribution du client, délai.

Les solutions s'affichent côte à côte. « Reporter » sur l'une d'elles recopie numéro, date, distance, intitulé, coûts et
délai dans la demande, la passe à « étude reçue » et crée un point « à vérifier » pour le responsable.

Lecture par règles, calée sur le gabarit RTE : testée sur les 5 études du corpus (2023 à 2026), toutes lues exactement,
y compris les deux solutions de Haynecourt et de Fortum, les montants en M€ ou en k€ et le délai en années
d'E-Valley (7 ans). Si RTE change de gabarit et qu'aucune solution n'est lue, l'IA locale prend le relais, signalée
« lu par IA ».

Une étude qui arrive en pièce jointe d'un courriel déposé en .eml sur la demande est reconnue, jointe et lue d'office.

Les études déjà jointes aux demandes du registre (Haynecourt, Fortum, E-Valley, Angoulême, Oursel-Maison) ont un bouton
« Lire » : E-Valley n'avait aucun coût saisi, la lecture donne 102,5 M€ dont 87,21 M€ à la charge du client, 7 ans.

Pas encore : la PTF (pas d'exemple dans le corpus pour caler la lecture ; l'IA peut la lire en attendant un vrai document).

## 3. Mise à jour

Serveur, depuis PowerShell :

```powershell
$src = "C:\Castignac\Codes castignac(archive nicolas)\Automatisation étude explo\Amont"
$vm = "alexis@100.116.240.111"
scp -r "$src\amont_core" "$src\static" "${vm}:~/amont/"
scp "$src\docker-compose.yml" "${vm}:~/amont/"
```

Sur la VM :

```bash
cd ~/amont && cp donnees/amont.sqlite donnees/amont_avant_0.8.sqlite && docker compose up -d --build && sleep 5 && curl -s localhost:8010/api/sante ; echo
```

Poste : rien à copier, l'agent et le robot sont dans le dossier Amont. Lancer `2026_10_28_amont_agent_poste.bat`.
