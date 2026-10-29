# DCEX Raccordement : cahier des charges du registre et du dashboard

Note du 17/09/2026. Spécifie ce qui sera codé aux étapes 1 et 2 de la note du 10/09 (mise à jour le 17/09) : le registre des demandes de raccordement sur le serveur interne, et le dashboard qui s'y branche. Les robots et générateurs (étapes 3 à 6) ne sont pas couverts ici, sauf pour ce qu'ils attendent du registre.

---

## 1. Objet et périmètre

L'outil suit les demandes de raccordement des projets datacenter de Castignac auprès de RTE (étude exploratoire, puis PTF), d'Enedis (site HTA ou alimentation de chantier) et de GRDF, avec leurs échéances opposables, leurs pièces et leur historique. Il est utilisé par deux personnes, le responsable et l'analyste, depuis un navigateur, sur le réseau interne ou à distance.

Il ne fait pas : de dépôt automatique auprès des opérateurs, de gestion documentaire au-delà du rangement des pièces par projet, de comptes utilisateurs, de rôles, d'attribution de dossiers.

Deux règles non négociables, héritées du 03/09 : le dernier clic vers un opérateur est humain, et le registre est l'unique source de vérité (le JSON local du 03/09 disparaît).

---

## 2. Modèle de données

Cinq tables. Les noms de champs reprennent ceux du dashboard actuel pour que la migration des 9 demandes existantes soit un simple export.

### 2.1 projets

| Champ | Type | Remarque |
|---|---|---|
| code | texte, clé | Code court, ex. AIV, ANG, OUR |
| nom | texte | Nom d'usage du projet |
| commune, departement | texte | |
| lat, lon | décimal | Point de raccordement pressenti |
| puissance_cible_mw | décimal | Programme visé |
| statut_projet | liste | prospection, en_etude, engage, abandonne |
| notes | texte long | |
| cree_le, modifie_le | horodatage | |

### 2.2 demandes

| Champ | Type | Remarque |
|---|---|---|
| id | texte, clé | Code de la demande, ex. AIV-600-PTF |
| projet_code | référence projets | |
| filiere | liste | rte_ee, rte_ptf, enedis, grdf |
| statut | liste | Valeurs propres à chaque filière, voir 2.6 |
| site, commune, departement | texte | Repris du projet à la création, modifiables |
| date_depot | date | Point de départ de tous les échéanciers |
| interlocuteur | texte | Nom et adresse du contact opérateur |
| notes | texte long | |
| donnees | JSON | Champs spécifiques à la filière, voir 2.7 |
| cree_le, modifie_le, modifie_par | horodatage, texte | |

Une seule demande par couple projet × filière à la fois, sauf Enedis où le site HTA et le chantier sont deux demandes distinctes : contrainte d'unicité sur (projet_code, filiere, donnees.type_enedis).

### 2.3 echeances

Calculées, jamais saisies. Régénérées à chaque modification d'une demande à partir des règles de la section 3.

| Champ | Type | Remarque |
|---|---|---|
| id | entier, clé | |
| demande_id | référence demandes | |
| libelle | texte | Ex. « Remise de la PTF, 3 mois » |
| date | date | |
| fait | booléen | Vrai quand la date de réalisation correspondante est saisie |
| severite | liste | info, warn (sous 14 jours), crit (dépassée) |
| notifie_le | horodatage | Dernier envoi d'alerte, pour ne pas renvoyer chaque jour |

### 2.4 pieces

| Champ | Type | Remarque |
|---|---|---|
| id | entier, clé | |
| demande_id | référence demandes | |
| type | liste | extrait_cadastral, plan_installation, unifilaire, permis, preuve_virement, etude_recue, ptf, pdr, devis, convention, autre |
| chemin | texte | Relatif au dossier du projet sur le serveur |
| taille_octets, ajoute_le, ajoute_par | | |
| obligatoire_pour | liste | Étape à partir de laquelle la pièce bloque, ex. depose |

Les fichiers sont rangés sur le serveur dans `raccordement/<projet_code>/<filiere>/`, nommés au format `annee_mois_jour_type.pdf`. La base ne stocke que le chemin.

### 2.5 journal

| Champ | Type | Remarque |
|---|---|---|
| id | entier, clé | |
| demande_id | référence demandes | |
| horodatage | | |
| auteur | texte | Adresse e-mail transmise par Cloudflare Access |
| champ | texte | Champ modifié, ex. statut, date_depot |
| avant, apres | texte | Valeurs sérialisées |
| origine | liste | dashboard, robot, import |

Le journal est en ajout seul. Il permet de reconstituer la date exacte à laquelle un dossier est passé à « déposé », ce qui est la donnée opposable si un délai est contesté.

### 2.6 Statuts par filière

| Filière | Statuts, dans l'ordre |
|---|---|
| rte_ee | brouillon, pret_validation, depose, recevable, etude_recue, confirmation_demandee, clos |
| rte_ptf | brouillon, pret_validation, depose, recevable, ptf_recue, file_attente, convention |
| enedis | brouillon, pret_validation, depose, qualifiee, pdr_recue, acceptee, convention, mise_en_service |
| grdf | brouillon, pret_validation, depose, devis_recu, accepte, travaux, mise_en_service |

Deux statuts hors chaîne communs : irrecevable, abandonne. Le passage à un statut est libre (pas de machine à états stricte), mais le passage à « depose » est refusé tant qu'une pièce marquée obligatoire pour cette étape manque.

### 2.7 Champs spécifiques par filière (JSON `donnees`)

| Filière | Champs |
|---|---|
| rte_ee | puissance_mw, hypothese_secondaire_mw, d_km, num_etude, date_recevabilite, date_etude_recue, date_relance, date_confirmation_demandee, date_confirmation_recue, solution, cout_total_keur, cout_client_keur, delai_mois |
| rte_ptf | puissance_mw, d_km, ref_etude_exploratoire, gps_lat, gps_lon, alimentations_supplementaires, date_virement, date_recevabilite, date_ptf_recue, prorogation_ptf, date_ptf_acceptee, date_convention_signee, nb_versements_forfaitaires, date_signature_fasttrack, date_permis_obtenu, cout_total_keur, cout_client_keur, delai_mois |
| enedis | type_enedis (hta, chantier), puissance_kva, complexite (simple, etude), ouvrages_rte, ref_dossier, date_qualification, date_pdr_recue, date_pdr_acceptee, date_convention_signee, date_mise_en_service, cout_client_keur |
| grdf | debit_nm3h, usage_gaz, etude_requise, ref_dossier, date_devis_recu, date_relance, date_devis_accepte, date_travaux_prevue, date_mise_en_service, cout_client_keur |

---

## 3. Règles de calcul des échéances

Implémentées côté serveur dans un module unique, pour que le dashboard, les alertes et les robots partagent le même résultat. Jours ouvrés : lundi à vendredi, sans prise en compte des fériés dans un premier temps (à ajouter avec le calendrier français si un écart est constaté).

| Filière | Échéance | Point de départ | Délai | Réalisée quand |
|---|---|---|---|---|
| rte_ee | Recevabilité | date_depot | 8 jours ouvrés | date_recevabilite ou date_etude_recue |
| rte_ee | Remise de l'étude, délai annoncé | date_recevabilite sinon date_depot | 6 semaines | date_etude_recue |
| rte_ee | Remise de l'étude, prévisionnel | idem | 7 semaines sous 100 MW, 10 entre 100 et 400, 16 au-delà | date_etude_recue |
| rte_ee | Relance écrite | idem | 6 semaines | date_relance |
| rte_ee | Confirmation de solution | date_confirmation_demandee | 15 jours ouvrés | date_confirmation_recue |
| rte_ptf | Recevabilité de la D2 | date_depot | 8 jours ouvrés | date_recevabilite ou date_ptf_recue |
| rte_ptf | Remise de la PTF | date_recevabilite sinon date_depot | 3 mois | date_ptf_recue |
| rte_ptf | Fin de validité de la PTF | date_ptf_recue | 3 mois, 6 si prorogation_ptf | date_ptf_acceptee |
| rte_ptf | Dernier jour pour demander la prorogation | date_ptf_recue | 3 mois | date_ptf_acceptee ou prorogation_ptf |
| rte_ptf | Maintien en file d'attente | date_ptf_acceptee | chaque anniversaire, jusqu'à date_convention_signee | jamais, récurrente |
| rte_ptf | Fin des justificatifs de phase d'étude | date_ptf_acceptee | 24 mois | date_convention_signee |
| rte_ptf | Permis fast-track | date_signature_fasttrack | 15 mois | date_permis_obtenu |
| enedis | Dossier complet, qualification | date_depot | 3 mois | date_qualification ou date_pdr_recue |
| enedis | Proposition de raccordement | date_qualification | 1 mois si complexite simple, 3 si etude | date_pdr_recue |
| enedis | Fin de validité de la PDR | date_pdr_recue | 3 mois | date_pdr_acceptee |
| enedis | Convention | date_pdr_acceptee | 9 mois, 12 si ouvrages_rte | date_convention_signee |
| enedis | Acceptation de la convention | date_convention_signee | 3 mois | date_mise_en_service |
| grdf | Devis | date_depot | 8 jours ouvrés, 1 mois si etude_requise | date_devis_recu |
| grdf | Relance du conseiller | date_depot | 15 jours | date_relance |
| grdf | Fin de validité du devis | date_devis_recu | 3 mois, à confirmer sur l'offre | date_devis_accepte |
| grdf | Début des travaux | date_travaux_prevue | | date_mise_en_service |

Alertes hors échéancier : statut pret_validation (en attente du clic humain), statut irrecevable, nb_versements_forfaitaires égal à 1 (avertissement) ou 2 (critique, faculté épuisée), debit_nm3h supérieur à 650 (vérifier le seuil GRTgaz), contrôle de l'article 105 sur les demandes RTE (domaine de tension imposé par la puissance et la distance).

---

## 4. API

Serveur Python, FastAPI, base SQLite dans un premier temps (deux utilisateurs, quelques centaines de lignes), migration vers PostgreSQL seulement si le serveur interne héberge d'autres applications qui la justifient. Toutes les routes sous `/api`, réponses JSON, dates en ISO 8601.

| Méthode et route | Rôle |
|---|---|
| GET /projets, POST /projets, GET et PATCH /projets/{code} | Projets et leur synthèse (une ligne par filière) |
| GET /demandes?filiere=&projet=&statut= | Liste filtrée, avec la prochaine échéance de chacune |
| POST /demandes | Création, initialise le statut à brouillon et copie commune et département du projet |
| GET, PATCH, DELETE /demandes/{id} | Fiche complète, échéances et pièces incluses ; PATCH journalise chaque champ modifié |
| GET /demandes/{id}/payload | Données prêtes pour le robot ou le générateur de la filière, mêmes clés que le mapping de sélecteurs du 03/09 |
| GET /echeances?avant=&severite= | Vue transversale, alimente le bandeau d'alertes et l'envoi quotidien |
| POST /demandes/{id}/pieces, DELETE /pieces/{id} | Dépôt de fichier (multipart), rangé dans le dossier du projet |
| GET /demandes/{id}/journal | Historique |
| GET /export.xlsx | Export de toutes les demandes avec leur prochaine échéance, pour un point d'équipe |
| GET /sante | Version, date de la dernière alerte envoyée, nombre de demandes |

L'auteur de chaque écriture est lu dans l'en-tête `Cf-Access-Authenticated-User-Email` posé par Cloudflare Access. En l'absence de cet en-tête (accès depuis le réseau interne sans passer par le tunnel), l'API accepte la requête et journalise « interne ».

Les robots du poste appellent GET /demandes/{id}/payload avant de remplir, et PATCH /demandes/{id} avec le statut pret_validation après avoir rempli. Ils n'écrivent jamais depose : c'est l'humain qui le fait, après avoir cliqué chez l'opérateur.

---

## 5. Dashboard

La page publiée du 10/09 est reprise telle quelle dans sa structure. Ce qui change : le stockage partagé est remplacé par l'API, et quatre éléments s'ajoutent.

| Élément | Contenu |
|---|---|
| Matrice projet × filière | Inchangée, en tête. Une case par filière, statut et prochaine échéance, création directe depuis une case vide |
| Fiche projet | Nouvelle page par projet : synthèse des quatre filières, échéancier fusionné trié par date, pièces, journal. Lisible en une page par quelqu'un qui n'a pas ouvert l'outil depuis un mois |
| Fiche demande | Inchangée : champs communs, champs de la filière, échéancier calculé, pièces attendues. Ajout du dépôt de fichier et du journal en bas de fiche |
| Bandeau d'alertes | Inchangé, alimenté par GET /echeances |
| Journal | Sous chaque fiche, et vue globale des 50 derniers changements |
| Export | Bouton vers GET /export.xlsx |

Pas de page de connexion, pas de préférences utilisateur, pas de tableau de bord personnel : la même vue pour les deux suiveurs.

---

## 6. Alertes par e-mail

Une tâche planifiée chaque matin à 8 h (cron ou planificateur du serveur) interroge GET /echeances et envoie un seul courriel aux deux adresses, uniquement s'il y a quelque chose à dire. Contenu : les échéances dépassées, celles à moins de 14 jours, les demandes en attente de validation humaine, dans cet ordre, une ligne par item avec le code de la demande, le projet, la filière et le lien direct vers la fiche. Une échéance déjà notifiée n'est renvoyée que si elle passe de warn à crit, ou tous les 7 jours tant qu'elle reste dépassée. Envoi par le serveur SMTP de la messagerie Castignac, identifiants dans un fichier d'environnement non versionné.

---

## 7. Hébergement et exposition

| Couche | Choix |
|---|---|
| Serveur | Serveur interne Castignac, service Python lancé par systemd ou conteneur Docker, même schéma que le serveur personnel |
| Base et fichiers | SQLite et dossier `raccordement/` sur un volume sauvegardé chaque nuit, rétention 30 jours |
| Exposition | Cloudflare Tunnel depuis le serveur, aucun port entrant ouvert |
| Authentification | Cloudflare Access, politique « e-mail figure dans la liste » avec les deux adresses des suiveurs, code à usage unique par e-mail, session de 24 h |
| Nom | Sous-domaine dédié du domaine Castignac, à demander à l'administrateur du DNS |
| Journalisation | Journal des connexions Cloudflare Access, journal applicatif sur le serveur |

Le réseau interne peut atteindre le service directement sans passer par le tunnel ; dans ce cas l'auteur des modifications n'est pas identifié, ce qui est acceptable à deux et signalé « interne » dans le journal.

---

## 8. Migration et mise en route

1. Export des 9 demandes du dashboard publié vers la base serveur, avec création des projets correspondants (AI-Valley, Angoulême, E-Valley, Fortum, Haynecourt, DIGITAL2060).
2. Rangement des PDF d'études RTE déjà sur le disque dans `raccordement/<projet>/rte_ee/` et enregistrement dans la table pieces.
3. Recalcul des échéances, vérification à la main sur AIV-600 et OUR-1000.
4. Ouverture du tunnel et de la politique Access, test depuis l'extérieur avec les deux adresses.
5. Premier envoi d'alerte manuel, puis activation de la tâche du matin.
6. Bascule du robot D1 sur l'API (étape 6 de la note du 10/09).

---

## 9. Critères de réception

L'outil est reçu quand, pour chaque filière, une demande créée dans le dashboard produit le bon échéancier au jour près sur un cas de test daté ; quand un changement de statut fait depuis l'extérieur via le tunnel apparaît dans le journal avec l'adresse e-mail de son auteur ; quand une pièce déposée se retrouve au bon chemin sur le serveur ; quand une échéance placée artificiellement à J-3 déclenche le courriel du matin aux deux adresses ; et quand le robot D1 du 03/09 remplit le Portail Services à partir de GET /demandes/{id}/payload sans son JSON local.

---

## 10. Hors périmètre, pour mémoire

Dépouillement automatique des PDF d'études et de PTF (gabarits instables), récupération du numéro de dossier après envoi (non exposé par les portails), intégration au calendrier, notifications autres que le courriel, accès pour d'autres personnes que les deux suiveurs.
