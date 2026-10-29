# Étude exploratoire : ce qui s'automatise et ce qui reste manuel

Note du 27/07/2026, établie après confrontation de l'outil DCEX à 4 études exploratoires RTE réelles (6 solutions de raccordement).

## Le corpus de référence

| Étude | Puissance | d | Tension | Solution | Coût | Contribution | Délai |
|---|---|---|---|---|---|---|---|
| Oursel-Maison 26-2818 | 600-1000 MW | n.c. | HTB3 400 kV | double coupure ligne + nouveau poste, 2,3 km aérien | 44 800 k€ | 38 100 (85 %) | 120 mois |
| Angoulême 26-4883 | 60 MW | 10 km | HTB1 90 kV | antenne poste Rabion, 0,5 km souterrain | 4 500 k€ | 3 150 (70 %) | 61 mois |
| Haynecourt 23-1496 s1 | 180 MW | 17 km | HTB2 225 kV | double antenne Mastaing, 2 x 17 km souterrain + AT + selfs | 77 000 k€ | 65 500 (85 %) | 59 mois |
| Haynecourt 23-1496 s2 | 180 MW | 17 km | HTB2 225 kV | coupure Gavrelle-Dechy + nouveau poste, 2 x 13 km | 66 000 k€ | 46 000 (70 %) | 59 mois |
| Fortum 24-1410 s1 | 64 MW | 25 km | HTB2 225 kV | antenne Mastaing, 17 km souterrain | 25 000 k€ | 17 500 (70 %) | 60 mois |
| Fortum 24-1410 s2 | 40 MW | 8 km | HTB1 63 kV | antenne Premy, 8 km souterrain | 12 000 k€ | 8 400 (70 %) | 60 mois |

## 1. Automatisable, déterministe, à fiabilité élevée

### La tension de référence, avec le critère « d » (corrigé ce jour)

C'est la découverte majeure du corpus. La règle de l'article 105 n'est pas un simple seuil de puissance : Prac doit être inférieure à la **plus petite** de deux valeurs, un seuil absolu et K/d, où d est la distance au point de transformation vers la tension supérieure le plus proche (K = 1 000 pour HTB1, 10 000 pour HTB2).

L'outil ne testait que le seuil absolu. Sur le cas Fortum il concluait HTB1 alors que RTE impose le 225 kV : 64 MW à 25 km donnent une limite HTB1 de 1 000/25 = 40 MW. Erreur d'un niveau de tension entier, donc d'un facteur 2 sur le coût.

Corrigé et vérifié sur les 5 cas où d est explicité : **5 sur 5**.

Corollaire à forte valeur commerciale : l'outil calcule maintenant la puissance plafond permettant de rester au domaine inférieur. C'est exactement l'arbitrage que RTE propose à Fortum (64 MW à 225 kV pour 25 M€, ou 40 MW à 63 kV pour 12 M€). Ce type d'alternative se calcule, il ne s'improvise pas.

### L'inventaire réseau et la géométrie
Lignes et postes proches par niveau de tension, distances, identification des candidats de raccordement, cartographie. Déjà en place, fiable.

### Les solutions de raccordement candidates
Les 6 solutions du corpus se répartissent en 3 schémas seulement : antenne sur poste existant, double antenne, entrée en coupure avec création de poste. L'énumération des candidats est mécanique.

### Le contexte du site
PLU, risques, environnement, nappe, cadastre, concurrence. C'est ce que fait déjà votre outil d'étude de faisabilité (Drancy), et il le fait bien. Cette brique est directement transposable.

### Le texte non variable
Préambule, objectifs, hypothèses, notas administratifs, CNDP, évaluation environnementale, forfait PTF de 42 k€. Environ 60 % du volume du document, identique d'une étude à l'autre.

## 2. Semi-automatisable, à produire comme fourchette et non comme chiffre

### Le coût
Écarts de l'outil avant recalibrage : -36 %, -14 %, +1 %, -22 %, -13 %. Le +1 % était une coïncidence (coefficient aérien appliqué à une liaison souterraine).

Ce que le corpus apprend :

- Le coût suit une structure **fixe + variable**, pas une proportionnelle. Ramené au km, le coût va de 1 470 k€/km sur 17 km à 9 000 k€/km sur 0,5 km. Sur les liaisons courtes, le terme fixe domine entièrement.
- Le variable souterrain 225 kV converge à **1 300 à 1 650 k€/km** selon la section (630 ou 1600 mm²). Le fichier de configuration indiquait 6 000, soit 4 fois trop.
- Le choix aérien ou souterrain est le premier levier de coût, dans un rapport de 1 à 5, et ce n'est pas une donnée calculable : c'est un arbitrage d'acceptabilité locale.
- Les équipements de compensation ne se déduisent d'aucune donnée publique : l'autotransformateur 400/225 kV et les selfs de Haynecourt pèsent une vingtaine de M€ sur 77, la self et le filtre harmonique évoqués chez Fortum ajoutent 5 à 6 M€ conditionnels.

Conclusion : produire une fourchette basse-haute avec la structure de coût détaillée, jamais un chiffre unique. La ligne « à confirmer par PTF » de votre deck Drancy est la bonne formulation.

### Le taux de contribution
Il n'est pas constant. 70 % dans 4 cas, 85 % dans 2. La règle sous-jacente est claire : 70 % sur l'alimentation principale, 100 % sur les travaux supplémentaires demandés par le client. Les deux cas à 85 % sont ceux avec alimentation de secours ou double antenne. Automatisable **si** le besoin de secours est saisi en entrée. C'est désormais un paramètre.

### Le délai
Corpus : 59, 60, 60, 61 mois en HTB1 et HTB2, et 120 mois à Oursel-Maison. La configuration prévoyait 84 mois en HTB2, soit 40 % d'erreur.

Le délai n'est pas piloté par la tension mais par la consistance des travaux : environ 60 mois pour un raccordement sur poste existant (dont 30 à 36 mois de procédures et études), le double dès qu'il faut créer un poste 400 kV avec renforcements lourds. Corrigé.

## 3. Strictement manuel, à ne pas tenter d'automatiser

### L'étude de transit
C'est le cœur de l'étude RTE et le seul champ vraiment non reproductible. Il demande le modèle de réseau interne avec les scénarios de consommation à l'horizon de mise en service. Trois exemples du corpus montrent ce qui s'y joue :

- Angoulême : le raccordement aggrave une contrainte sur Rabion-Vallade et en crée une sur Fléac-Rabion n°2. Le soutirage des 60 MW est conditionné à des travaux prévus pour 2031.
- Oursel-Maison : limitations de 2 800 h/an jusqu'en 2035, non indemnisées.
- Haynecourt : saturation de transformation imposant un autotransformateur.

Aucune de ces informations n'existe en open data. Ce sont pourtant celles qui décident de la viabilité d'un projet : une limitation à 2 800 h/an, c'est un tiers de l'année, cela peut suffire à disqualifier un site.

### Les jugements d'ingénierie
Aérien ou souterrain, section de câble, tracé réaliste, franchissements (l'A16 à Oursel-Maison), acceptabilité locale, stabilité du sous-sol, besoin de compensation de réactif.

### La distance « d » elle-même
RTE la mesure sur un parcours réseau réalisable techniquement et administrativement, pas à vol d'oiseau. L'outil applique un coefficient de sinuosité de 1,25 par défaut, à ajuster manuellement site par site. Comme d conditionne le niveau de tension, une erreur ici change tout : à 25 km la limite HTB1 est de 40 MW, à 20 km elle est de 50 MW.

## 4. Ce que je recommande de construire

L'objet à viser n'est pas une étude exploratoire automatique. C'est une **note de pré-instruction** qui :

1. tranche la tension de référence et affiche le calcul de d, avec la puissance plafond au domaine inférieur ;
2. énumère 2 ou 3 solutions candidates avec leur consistance de travaux ;
3. chiffre chacune en fourchette, structure de coût détaillée, hypothèse aérien/souterrain explicite ;
4. annonce un délai de 60 mois par défaut, 120 en cas de création de poste 400 kV ;
5. laisse en évidence les 4 champs que seule RTE peut remplir : impact sur le RPT, renforcements amont, compensation de réactif, limitations temporaires ;
6. intègre le volet site de votre outil Drancy, qui est déjà au niveau.

Ce livrable vous sert à trois choses : éliminer un site avant de payer 42 k€ de PTF, arbitrer entre plusieurs sites sur une base homogène, et arriver devant RTE avec un dossier déjà instruit.

## 5. Correctifs appliqués ce jour

- Critère d implémenté dans la tension de référence, validé 5 sur 5
- Fonction de puissance maximale admissible par domaine de tension, pour proposer les solutions dégradées
- Liaison souterraine passée en défaut, conforme à toutes les études HTB1 et HTB2 du corpus
- Coûts au km divisés par 4 en HTB2, structure fixe plus variable
- Délai HTB2 ramené de 84 à 60 mois
- Taux de contribution ramené à 70 %, avec 85 % documenté pour les cas avec secours
- Nombre de cellules en antenne ramené de 2 à 1, conforme aux 3 cas observés

## 6. Ce qu'il reste à vérifier

Le corpus compte 4 études, dont 2 sur la même commune. C'est assez pour corriger des erreurs grossières, pas pour valider un modèle de coût. Deux points à confirmer sur les prochaines études :

- le coût fixe de raccordement à un poste existant, actuellement estimé à 3 000 k€ sur un seul point d'appui (Angoulême, où il est mêlé à un renforcement non chiffré) ;
- la règle réelle du taux de contribution, la lecture « 70 % principal, 100 % supplémentaire » restant une inférence sur 6 observations.
