# DCEX : générateur de pré-études exploratoires de raccordement RTE

## Installation (une seule fois)

```
pip install requests python-docx matplotlib
```

## Utilisation

1. Dupliquer `2026_07_13_dcex_site_exemple.json` et le remplir (client, commune, département, puissances, dates).
2. Lancer :

```
python 2026_07_13_dcex_etude_explo.py --site mon_site.json
```

Le script géocode la commune (API geo.gouv), interroge l'open data ODRE (lignes aériennes, souterraines et postes RTE dans un rayon de 30 km), détermine la tension de référence (arrêté du 9 juin 2020), propose une solution de raccordement (antenne sur poste existant ou entrée en coupure sur ligne + nouveau poste), estime coût et délai, puis génère : le document Word au format étude exploratoire RTE, la carte du réseau, et un JSON des données.

On peut aussi fournir directement des coordonnées dans le JSON du site ("lat" et "lon") au lieu de la commune.

## Paramétrage

`2026_07_13_dcex_config.json` contient les ratios ajustables : coûts unitaires par niveau de tension (cellule, génie civil poste, km de liaison), nombre de cellules par type de solution, taux de contribution client (0,85 calibré sur l'étude Oursel-Maison), délais indicatifs par domaine de tension, rayon de recherche.

Calibrage vérifié sur l'étude RTE n°26-2818 (Oursel-Maison, 600-1000 MW) : coût estimé 44 400 k€ contre 44 800 k€ réels, délai 120 mois identique.

## Limites

Les résultats d'étude de transit (contraintes réseau, renforcements, limitations temporaires) nécessitent le modèle de réseau interne RTE : ils apparaissent en champs [À COMPLÉTER]. Le document est une pré-étude interne indicative, clairement marquée comme non émise par RTE. Depuis 2024, RTE publie des tracés géographiques simplifiés pour raison de sécurité : les distances sont donc approximatives.
