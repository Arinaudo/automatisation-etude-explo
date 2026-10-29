# Amont 0.2 : sources et fiche identité des sites

Note du 07/10/2026. Ajoute à Amont 0.1 (18/09) une partie amont du registre : on dépose les fichiers d'un site, un programme en extrait les données, on corrige et on valide la fiche identité, puis les demandes de raccordement se créent à partir de la fiche. NaTran est ajouté en filière optionnelle.

---

## 1. Principe

Un site est un projet : même code (SOC, AIV...), même ligne dans le registre. Pour chaque site :

1. **Sources** : on dépose les fichiers du site (étude de faisabilité du DatacenterSiteAnalyzer, règlement de PLU, cadastre, plan de cession, études RTE, plans, Kbis...). Formats lus : PDF, Word, Excel, PowerPoint, JSON, texte, images.
2. **Extraction** : chaque fichier est lu en tâche de fond. Les valeurs trouvées remplissent les champs vides de la fiche, surlignés « à vérifier ». Si un fichier contredit une valeur déjà présente, la valeur part dans « Valeurs divergentes » avec la phrase du document : Prendre ou Ignorer.
3. **Fiche identité** : 41 champs en 6 groupes (site, foncier et urbanisme, demandeur, électricité, chantier, gaz). Chaque valeur garde sa provenance (fichier, saisie manuelle, valeur société, projet). Une saisie à la main est validée d'office et n'est jamais écrasée par une extraction.
4. **Prêt pour les demandes** : pour chaque filière, le taux de remplissage des champs que demande l'opérateur, ce qui manque, ce qui reste à vérifier, et le canal de dépôt. Le bouton « Préparer les demandes manquantes » crée d'un coup les demandes absentes (SOC-EE, SOC-PTF, SOC-ENE, SOC-GAZ, SOC-NAT), pré-remplies depuis la fiche.

Les robots et générateurs liront la fiche via `GET /api/demandes/{id}/payload`, qui contient maintenant `fiche` (toutes les valeurs du site) et `fiche_completude` (manquants et à vérifier pour la filière).

---

## 2. Les deux moteurs d'extraction

| Moteur | Quand | Ce qu'il sait faire |
|---|---|---|
| IA (Claude) | variable `ANTHROPIC_API_KEY` posée et paquet `anthropic` installé | Tous les champs, sur tout document. Les PDF sans texte (scans, plans comme le plan de cession PSA) et les images sont envoyés tels quels au modèle |
| Règles | sinon, ou si l'appel IA échoue | Calées sur le corpus : études de faisabilité (adresse, commune, GPS, parcelles, surface, zonage PLU, poste RTE et distance, INSEE), études RTE (commune, GPS, puissance, date), nom de fichier PLU (zone), SIRET, TVA, n° de permis |

Sans IA, les fichiers scannés sont marqués « à revoir » avec le motif. Pour activer l'IA :

```
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-...
set AMONT_MODELE=claude-sonnet-4-5
python 2026_09_18_amont_serveur.py
```

`AMONT_MODELE` est facultatif. `AMONT_IA=non` force les règles. Le bandeau de la fiche du site indique le moteur actif. Point d'attention : avec l'IA, le contenu des fichiers sort vers l'API Anthropic, à valider en interne avant de l'activer sur des documents confidentiels.

---

## 3. Mise à jour depuis la 0.1

```
cd Amont
pip install -r requirements.txt
python 2026_09_18_amont_serveur.py
```

Les nouvelles tables (sources, fiche, propositions) se créent seules au premier lancement, la base existante est conservée. À la première ouverture, chaque fiche est amorcée avec les valeurs société (`amont_config.json`) et ce que le projet connaissait déjà (nom, commune, GPS, puissance), ces dernières à vérifier.

Import en masse d'un dossier existant, serveur lancé ou non :

```
python 2026_10_07_amont_sources_import.py --site SOC --nom "Datacenter Sochaux PSA Sud" --dossier "..\Sochaux" --recursif
```

Testé sur le dossier Sochaux en règles seules : 22 champs remplis sur 41, dont les 10 parcelles, la surface de 30,28 ha, le zonage UYb/UZ et le poste d'Étupes 225 kV à 1,56 km. Le plan de cession scanné attend l'IA. Points à corriger à la main sur ce site : la commune et le code INSEE extraits sont ceux d'Exincourt (plus grande parcelle), alors que le point de raccordement déclaré est sur Sochaux (25547) ; la puissance de 300 MW et la date de mise à disposition sont à saisir.

---

## 4. Configuration : amont_config.json

| Clé | Rôle |
|---|---|
| `filieres_optionnelles` | `["natran"]` pour afficher NaTran dans la matrice, la fiche et les demandes. Vide par défaut |
| `demandeur` | Société, SIREN, interlocuteur repris sur chaque nouvelle fiche. Ajouter `demandeur_siret`, `demandeur_tva` et `adresse_facturation` ici une fois connus : ils manquent aux filières PTF, Enedis et GRDF sur tous les sites |

Redémarrer le serveur après modification.

---

## 5. NaTran (ex-GRTgaz), en option

Étapes : demande, étude de faisabilité (convention payante, date de remise contractuelle), rapport, convention d'études de raccordement, contrat, mise en service. Seuls deux délais sont calculés car ce sont les seuls écrits dans les conventions types NaTran 2025 pour un client final : la date de remise du rapport (à saisir, elle est propre à chaque convention) et la signature de la convention d'études au plus tard 6 mois après le rapport. Champs propres : débits maximal et minimal, pression de livraison, usage. Pas de portail : la demande part par courriel à l'interlocuteur commercial. L'alerte GRDF au-delà de 650 Nm³/h renvoie désormais vers NaTran.

---

## 6. Enedis

Le canal retenu est la procédure en ligne du Portail Raccordement Entreprise (raccordement-entreprise-enedis.fr). Les champs requis pour la filière Enedis dans la fiche correspondent à une alimentation de chantier (adresse, parcelles, SIRET, interlocuteur, puissance en kVA, date de début). Le relevé réel du formulaire, comme celui fait sur le portail RTE le 05/10, reste à faire pour écrire le robot et ajuster cette liste.

---

## 7. API ajoutée

| Route | Rôle |
|---|---|
| GET /api/sites, GET /api/sites/{code} | Liste avec complétude, détail (fiche, sources, divergences, complétude, demandes) |
| PATCH /api/sites/{code}/fiche | Saisie manuelle, validée d'office |
| POST /api/sites/{code}/fiche/valider | Valide les champs listés, ou tous les champs à vérifier |
| POST /api/sites/{code}/fiche/import | Entrée directe d'un autre programme : `{"origine": "dcsa", "valeurs": {...}}`. Prévue pour que le DatacenterSiteAnalyzer pousse ses résultats sans passer par un fichier |
| POST /api/sites/{code}/sources | Dépôt de fichiers (multipart, champ `fichiers`, plusieurs possibles) |
| POST /api/sources/{id}/extraire, POST /api/sites/{code}/extraire | Relire un fichier, ou tous |
| POST /api/propositions/{id}/accepter, /rejeter | Arbitrage des divergences |
| POST /api/sites/{code}/preparer | Crée les demandes absentes, pré-remplies |
| POST /api/demandes/{id}/synchroniser | Recopie la fiche dans une demande existante |

---

## 8. Suite proposée

1. Brancher le DatacenterSiteAnalyzer sur `POST /api/sites/{code}/fiche/import` à la fin de chaque étude.
2. Robot Selenium D1 lisant le payload (fiche comprise), d'après les notes du 05/10.
3. Relevé du formulaire Enedis Raccordement Entreprise, puis robot.
4. Générateur de fiche D2 et brouillon Outlook.
5. Relevé du formulaire GRDF.
