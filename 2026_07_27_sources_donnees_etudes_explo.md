# Sources de données pour automatiser les études exploratoires datacenter (DCEX)

Recherche du 27/07/2026. Pour chaque source : URL, mode d'accès, authentification, fraîcheur, limites et usage dans le pipeline DCEX. Les sources marquées TESTÉ ont été vérifiées par appel réel.

## 1. Réseau de transport RTE

### ODRE, Open Data Réseaux Énergies (déjà intégré dans DCEX)
- URL : https://odre.opendatasoft.com (miroir : https://opendata.reseaux-energies.fr)
- Accès : API opendatasoft REST (v2.1 `/api/explore/v2.1/catalog/datasets/{id}/records` et legacy `/api/records/1.0/search/`), exports CSV/GeoJSON/SHP. Sans authentification.
- Datasets clés :
  - `lignes-aeriennes-rte-nv` : lignes aériennes, màj 16/06/2026, semestriel
  - `lignes-souterraines-rte-nv` : lignes souterraines
  - `postes-electriques-rte` : sites électriques RTE et points de piquage, màj 16/06/2026
  - `registre-national-installation-production-stockage-electricite-agrege` : registre production/stockage (màj 31/03/2026), utile pour voir ce qui est déjà raccordé autour d'un poste
  - `suivi-projet-raccordement-enr` : file d'attente production EnR par poste (PTF acceptées et propositions d'entrée en file d'attente)
- Limites : depuis 2024 RTE publie des tracés géographiquement simplifiés pour raison de sécurité, distances approximatives. La file d'attente CONSOMMATION (datacenters) n'est pas publiée, seule celle de la production EnR l'est.

### Caparéseau, capacités d'accueil par poste
- URL : https://www.capareseau.fr et dataset data.gouv « Capacités d'accueil du réseau » (https://www.data.gouv.fr/datasets/capacites-daccueil-du-reseau)
- Accès : consultation web par poste source, données téléchargeables ; publié conjointement par RTE et Enedis dans le cadre des S3REnR.
- Contenu : capacité réservée/disponible par poste (MW), transformation HTB/HTA, projets en file d'attente par poste.
- Limites : orienté PRODUCTION EnR (S3REnR), pas soutirage. À utiliser comme proxy : un poste saturé en production signale un réseau contraint. Le site n'a pas d'API documentée : scraping HTML/JSON interne possible.

### data.rte-france.com, API officielles RTE
- URL : https://data.rte-france.com
- Accès : API REST OAuth2, gratuit sur inscription (création d'une application, token).
- Contenu utile : consommation, production, échanges, signaux marché. Rien sur les capacités de soutirage par poste.
- Usage DCEX : marginal à ce stade, utile plus tard pour données de contexte (adéquation offre-demande régionale).

### SDDR, schéma décennal de développement du réseau
- URL : https://www.rte-france.com/donnees-publications/plans-strategiques/schema-developpement-reseau ; rapport complet PDF : https://assets.rte-france.com/prod/public/2025-06/2025-06-06-sddr-rapport-complet.pdf
- Accès : PDF à parser (pdftotext/pdfplumber). Consultation CRE : https://consultations.cre.fr/2025-08/new
- Contenu : 100 Md€ d'investissements 2025-2040, renforcements 400 kV prévus, zones d'accueil des gros consommateurs. Précieux pour anticiper les renforcements qui lèveront les limitations temporaires.
- Limites : pas de données structurées, extraction manuelle ou LLM.

### Documentation technique de référence RTE (DTR)
- URL : https://www.services-rte.com (bibliothèque documentaire), ex. procédure raccordement consommation : DTR 1.4.1 et article 1.2.2
- Accès : PDF téléchargeables sans authentification.
- Usage DCEX : source officielle des règles (contribution 70 %, somme forfaitaire PTF 42 k€, délais). À surveiller pour la réforme annoncée de la file d'attente (passage de « premier arrivé premier servi » à « premier prêt premier servi », cf. Usine Nouvelle 2026).

## 2. Réseau de distribution Enedis (sites < 40 MW ou contexte local)

- URL : https://data.enedis.fr (alias enedis.opendatasoft.com, opendata.enedis.fr)
- Accès : API opendatasoft identique à ODRE, sans authentification.
- Datasets clés : `poste-source` (position des postes sources HTB/HTA), `donnees-relatives-aux-lignes-et-aux-postes`.
- Usage DCEX : localisation des postes sources pour les projets plus petits ou pour l'alimentation de chantier ; croisement avec Caparéseau pour la capacité.

## 3. Coûts et délais

- DTR RTE (ci-dessus) : principes de facturation, barèmes.
- Délibérations CRE : https://www.cre.fr (approbation des procédures de raccordement et du TURPE). PDF scrapables.
- Vos propres études exploratoires reçues : la meilleure source de calibrage des ratios k€/cellule et k€/km du fichier config DCEX. Un parseur PDF des études RTE reçues (comme Oursel-Maison) permettrait d'enrichir automatiquement le calibrage.

## 4. Foncier et urbanisme

### Cadastre Etalab
- URL : https://cadastre.data.gouv.fr ; données brutes : https://cadastre.data.gouv.fr/data/etalab-cadastre/latest/geojson/ (par commune/département)
- Accès : téléchargement direct GeoJSON/SHP, sans authentification. Màj trimestrielle environ.
- Usage DCEX : géométrie exacte des parcelles au lieu du centroïde communal, surface disponible.

### API Carto IGN (TESTÉ)
- URL : https://apicarto.ign.fr
- Accès : REST GeoJSON sans authentification. Modules : `cadastre` (parcelle par référence), `gpu` (zonage PLU au point : `/api/gpu/zone-urba?geom={point}`), `nature` (Natura 2000, ZNIEFF), `rpg`.
- Usage DCEX : LA brique à intégrer en premier : une requête par site donne parcelle + zonage PLU + zonages nature.

### Géoportail de l'urbanisme
- URL : https://www.geoportail-urbanisme.gouv.fr/services/ (WFS/WMS)
- Accès : flux WFS sans authentification, documents PLU/PLUi/CC/SUP.
- Limites : communes en RNU absentes (cas d'Oursel-Maison), servitudes SUP incomplètes selon les départements.

### DVF / DVF+ / DV3F (valeurs foncières)
- DVF brut : https://www.data.gouv.fr (fichiers annuels, sans auth)
- DVF+ géolocalisé Cerema : https://datafoncier.cerema.fr/donnees/autres-donnees-foncieres/dvfplus-open-data (CSV, GPKG, SQL PostGIS, open data)
- API données foncières Cerema : https://www.data.gouv.fr/dataservices/api-donnees-foncieres (certains endpoints réservés sphère publique)
- Usage DCEX : estimation de la valeur des terrains autour du site, comparables de transactions.

### Sitadel (permis de construire)
- URL : dataset mensuel sur data.gouv.fr (« autorisations d'urbanisme Sitadel »), locaux d'activité inclus
- Accès : CSV mensuel sans auth ; alternative payante PermisAPI (49-199 €/mois).
- Usage DCEX : détection de projets concurrents (permis de locaux industriels/tertiaires de grande surface près des postes sources).

## 5. Risques et environnement

### Géorisques (TESTÉ)
- URL : https://www.georisques.gouv.fr/api ; doc : https://www.georisques.gouv.fr/doc-api
- Accès : v1 REST JSON sans token (testé OK : `/api/v1/gaspar/risques?code_insee=...`), v2 avec token gratuit (compte Cerbère, valable 1 an).
- Endpoints utiles : risques GASPAR par commune, ICPE et sites SEVESO à proximité, retrait-gonflement argiles, zonage sismique, TRI inondation, canalisations de matières dangereuses, cavités.
- Usage DCEX : section « risques » complète du rapport en 5-6 requêtes.

### INPN / Natura 2000 / ZNIEFF
- URL : https://inpn.mnhn.fr/telechargement/cartes-et-information-geographique (SHP, WFS/WMS) ; datasets miroir sur data.gouv.fr
- Accès : téléchargement et flux sans authentification. Alternative plus simple : module `nature` d'API Carto (requête au point).

### Hub'Eau (TESTÉ)
- URL : https://hubeau.eaufrance.fr/page/apis
- Accès : REST JSON sans authentification (testé OK : `/api/v1/niveaux_nappes/stations`). Màj quotidienne.
- API utiles : piézométrie (niveaux de nappes), prélèvements en eau, qualité. Pertinent pour le refroidissement et les conflits d'usage eau.

## 6. Connectivité télécom

- Arcep, Ma connexion internet : https://data.arcep.fr/fixe/maconnexioninternet/ (dossiers base_imb, eligibilite, reference par trimestre, dernier millésime T1 2026)
- Accès : fichiers CSV volumineux sans authentification.
- Limites : éligibilité grand public par immeuble, pas les dorsales fibre opérateurs (non publiques). Pour les backbones, seule la négociation directe ou des sources commerciales existent.

## 7. Concurrence datacenters

Pas de registre public des demandes de raccordement consommation. Approches indirectes : ICPE via Géorisques (rubriques 2921 tours aéroréfrigérantes, 4802 fluides), permis Sitadel, registre ODRE production/stockage (batteries colocalisées), presse spécialisée et debatpublic.fr (projets soumis à CNDP, obligatoire au-delà de 600 M€ d'investissement).

## Priorités d'intégration dans DCEX

1. API Carto IGN (parcelle + PLU + Natura 2000/ZNIEFF) : gain immédiat, zéro auth
2. Géorisques v1 : section risques automatique
3. Cadastre Etalab : passer du centroïde communal à la parcelle réelle
4. Caparéseau/data.gouv capacités d'accueil : enrichir le choix du poste de raccordement
5. Parseur des études RTE reçues (PDF) : calibrage continu des ratios de coûts
6. Hub'Eau et Arcep : sections eau et télécom du rapport
