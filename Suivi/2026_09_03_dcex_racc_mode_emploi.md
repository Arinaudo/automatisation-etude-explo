# Automatiser les demandes d'étude exploratoire RTE

Note du 03/09/2026. Fait suite à la note du 27/07/2026 sur ce qui s'automatise dans
l'étude elle-même. Celle-ci porte sur la **demande** et son **suivi**.

---

## 1. Ce que la recherche établit

**Il n'existe aucune API RTE de raccordement.** Le catalogue data.rte-france.com ne
couvre que les données de marché (consommation, effacements, éco2mix). Aucun jeu de
données raccordement sur ODRE. SimuRacco ne traite que la production et le stockage,
plafonné à 250 MW, donc inutilisable pour la consommation.

**Deux canaux de dépôt existent, et seulement deux :**

| Canal | Automatisable | Remarque |
|---|---|---|
| Formulaire dématérialisé du Portail Services | Oui, par robot navigateur | Compte requis. Reprend toutes les rubriques de la fiche D1 de la DTR, avec saisie guidée. Ouvert depuis le 7 octobre à la production, la consommation et le stockage. |
| Fiche D1 PDF par courriel | Oui, intégralement | `rte-fcent-raccordement-conso-dist@rte-france.com` pour la consommation seule, sinon `rte-fcent-dp-raccordement@rte-france.com`. Voie sans compte. |

C'est le premier canal qui est retenu ici : c'est la voie officielle, et elle donne un
accusé de réception horodaté dans l'espace client.

**Les délais opposables, base de tout l'échéancier :** recevabilité sous 8 jours ouvrés,
remise de l'étude sous 6 semaines à compter de la recevabilité, confirmation de validité
sous 15 jours, instruction de la PTF sous 3 mois, validité de la PTF 3 mois. L'étude
exploratoire est gratuite, facultative, et ne vaut pas entrée en file d'attente.

**Le délai réel de remise est plus long que le délai annoncé**, et croît avec la
puissance. Sur nos quatre études : 4 semaines à 60 MW, 7 à 64 MW, 8 à 1 000 MW, 16 à
600 MW. L'outil calcule donc deux échéances, la contractuelle à 6 semaines et un
prévisionnel calibré, et déclenche une relance écrite à la sixième semaine.

---

## 2. Le verrou du dernier clic

Le robot remplit tout, téléverse les pièces, prend les captures, puis s'arrête.
Ce n'est pas une convention d'usage, c'est verrouillé à trois niveaux :

1. **Aucune fonction d'envoi n'existe** dans `2026_09_03_dcex_racc_portail.py`.
   Il n'y a rien à activer, aucun drapeau à basculer.
2. **Le mapping de sélecteurs est refusé au chargement** s'il contient un libellé
   d'envoi : envoyer, soumettre, submit, valider la demande, déposer, transmettre.
   Une erreur de configuration ne peut donc pas produire un envoi accidentel.
3. **La checklist de recevabilité bloque le lancement** tant qu'une pièce obligatoire
   manque, l'extrait cadastral en tête, dont l'absence fait tomber le dossier dès les
   8 premiers jours.

Le navigateur reste ouvert sur le formulaire relu, le récapitulatif est imprimé en
console, et c'est vous qui cliquez.

---

## 3. Architecture

```
   Dashboard (page publiée, base partagée)
        |  création, suivi, échéancier, alertes
        v
   Registre JSON local  <----  2026_09_03_dcex_racc_suivi.py
        |  payload D1 + checklist de recevabilité
        v
   Robot Playwright  <----  2026_09_03_dcex_racc_portail.py
        |  session persistante, remplissage, pièces jointes, captures
        v
   ARRÊT.  Relecture puis clic humain.
        |
        v
   Portail Services RTE
```

Trois fichiers, une seule règle de circulation : le registre JSON est la source de
vérité côté poste, le dashboard est la vue de suivi partageable.

---

## 4. Installation, une fois

```
pip install playwright
playwright install chromium
```

Le noyau de suivi n'a aucune dépendance, bibliothèque standard uniquement.

---

## 5. Première mise en route, une fois

Le relevé des champs est **déjà fait**, en direct sur le formulaire connecté le 04/09/2026.
Le fichier `2026_09_03_dcex_racc_selecteurs.json` couvre les 5 étapes, 29 champs. Il n'y a
plus de commande `capture` à lancer. Il reste une seule chose à faire :

```
python 2026_09_03_dcex_racc_portail.py login
```
Connectez-vous dans la fenêtre, code par e-mail compris. La session est conservée dans
`profil_navigateur_rte`, les lancements suivants sont directs.

Le relevé n'est à refaire que si RTE modifie son formulaire.

---

## 6. Cycle d'une demande

```
python 2026_09_03_dcex_racc_suivi.py add --id AIV-600 \
   --champ projet="AI-Valley" --champ commune="Haynecourt" --champ puissance_mw=600 \
   --champ d_km=17 --champ demandeur_siren=880034798 \
   --champ date_mise_a_disposition=30/09/2035

python 2026_09_03_dcex_racc_suivi.py payload AIV-600
python 2026_09_03_dcex_racc_portail.py verifier --id AIV-600     # sans navigateur
python 2026_09_03_dcex_racc_portail.py remplir  --id AIV-600     # avec navigateur
   -> relecture des 4 étapes, puis vous certifiez et vous envoyez

python 2026_09_03_dcex_racc_suivi.py set AIV-600 statut=depose date_depot=2026-09-15
python 2026_09_03_dcex_racc_suivi.py alertes
```

La commande `verifier` est le filet de sécurité. Elle ne lance aucun navigateur et contrôle
que chaque champ du formulaire trouve sa valeur dans le registre : champ obligatoire vide,
date mal formée ou passée, valeur absente de la liste d'options RTE, pièce jointe
introuvable ou au-delà de 2 Mo. À lancer systématiquement avant `remplir`.

La commande `payload` applique au passage le contrôle de l'article 105 et annonce le
domaine de tension imposé, avec la puissance plafond du domaine inférieur.

### Les trois pièges du formulaire, et comment le robot les traite

**Le SIREN est validé en direct** contre un registre. Un numéro fictif est refusé et
bloque le parcours. En cas de succès, RTE affiche automatiquement le nom de la société.

**La commune déclenche une autocomplétion asynchrone.** Le robot tape au clavier, attend
2,5 s, puis prend la première option de la liste Code INSEE, qui s'est peuplée entre-temps.

**La date ne se tape pas.** Son champ porte `readonly`, la valeur ne peut venir que du
calendrier, et son déclencheur n'est pas le composant Material standard mais une icône
maison. Le robot ouvre le calendrier, passe en vue multi-années, et sélectionne année, mois
puis jour par leur `aria-label` en toutes lettres. C'est le seul ancrage fiable : le texte
visible d'une cellule jour n'est que le numéro, donc viser « 5 » attraperait aussi 15 et 25.
Le champ porte en plus un minimum calé sur le lendemain, une date passée est refusée.

---

## 7. Le dashboard

Page publiée, base partagée entre ses lecteurs. Chaîne complète en 8 étapes, de la
préparation du dossier au maintien annuel en file d'attente, échéancier calculé,
bandeau d'alertes en tête, fiche éditable par demande. Il est amorcé avec les
cinq études du corpus et la demande AIV-600 en préparation.

Les modifications faites dans la page y sont conservées. Pour les répercuter dans le
registre local, ou l'inverse, demandez-moi la synchronisation.

---

## 8. Ce qui reste hors de portée

- **La récupération automatique du numéro de dossier et de l'accusé RTE.** Le portail
  ne l'expose pas de façon stable. Le robot capture la page après envoi, la lecture
  du numéro reste à faire à l'œil, ou à ajouter une fois qu'on aura vu un vrai écran
  de confirmation.
- **Le dépouillement automatique de l'étude reçue.** Les PDF RTE ne suivent pas un
  gabarit constant. Le corpus est trop mince pour un extracteur fiable.
- **L'étude de transit.** Inchangé depuis la note du 27/07 : contraintes induites,
  renforcements amont, compensation de réactif et limitations temporaires ne sont
  produits par personne d'autre que RTE.

---

## Sources

Fiche D1 consommation et procédure de traitement des demandes de raccordement,
documentation technique de référence RTE, articles 1.2.2 et 1.4.1. Annonce de la
dématérialisation du formulaire D1. Catalogue API data.rte-france.com. Arrêté du
9 juin 2020, article 105. Études exploratoires RTE n°23-1496, 24-1410, 26-2278,
26-2818 et 26-4883.
