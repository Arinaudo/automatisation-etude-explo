# DCEX : automatiser les demandes de raccordement sur les quatre filières

Note du 10/09/2026, mise à jour le 17/09/2026. Fait suite à la note du 03/09/2026 sur la demande d'étude exploratoire RTE (fiche D1). Celle-ci étend l'analyse aux trois autres démarches d'un projet datacenter : la demande de PTF chez RTE (fiche D2), le raccordement chez Enedis (sites de moins de 40 MW en HTA, et alimentation de chantier), le raccordement gaz chez GRDF. Elle décrit ce qui s'automatise, ce qui reste manuel, et l'architecture cible sur le serveur interne de Castignac. Rien n'est codé à ce stade.

**Cadrage arrêté le 17/09/2026.** L'objet principal du projet est le suivi des demandes de raccordement sur les trois opérateurs, pour faciliter l'implantation des datacenters. L'automatisation vient ensuite, par rentabilité décroissante. Le dossier raccordement est suivi par deux personnes seulement, le responsable et l'analyste : pas de rôles, pas d'attribution de dossiers, une seule vue pour les deux, et une authentification par liste blanche de deux adresses e-mail. Ce cadrage a inversé l'ordre de réalisation de la section 5 : le registre et le dashboard d'abord, les robots après.

Recherche faite le 10/09/2026 sur les sites officiels. Les pages GRDF refusent les robots de lecture, une partie du parcours gaz a été relevée dans le navigateur et une autre vient de sources secondaires, signalées comme telles.

---

## 1. Ce qui est établi pour chaque filière

### 1.1 RTE, demande de PTF (fiche D2)

C'est la première étape engageante. Contrairement à l'étude exploratoire, **il n'existe pas de formulaire dématérialisé** : la fiche D2 est un PDF de la DTR (article 1.2.4 dans la numérotation unifiée, « DTR 1.4.2 Fiche D2 conso v2 » dans l'ancienne) qui se remplit et s'envoie **par courriel** à `rte-fcent-raccordement-conso-dist@rte-france.com` pour une installation de consommation seule.

| Élément | Règle opposable | Source |
|---|---|---|
| Contenu minimal de la D2 | Dénomination, SIREN et SIRET, coordonnées GPS du point de connexion, puissance de raccordement, nombre et qualification des alimentations, schéma unifilaire | Procédure conso art. 5.1 |
| Pièces complémentaires | Fiche D1 si étude exploratoire antérieure, preuve de virement de la somme forfaitaire, numéro de TVA intracommunautaire et adresse de facturation | Procédure conso art. 5.1 |
| Somme forfaitaire | Fixée dans les conditions générales de la PTF, 42 k€ HT sur nos dossiers, déductible du coût de raccordement, remboursée si PTF sans création d'actifs ou renonciation sous 14 jours après notification de complétude | Procédure conso art. 5.1 |
| Recevabilité | RTE signale les manques sous 8 jours ouvrés, puis notifie la complétude | Procédure conso art. 5.1 |
| Remise de la PTF | 3 mois à compter de la notification de recevabilité, prorogeable avec accord écrit | Procédure conso art. 5.2 |
| Validité de la PTF | 3 mois, prorogeable une fois de 3 mois sur demande sauf situation de concurrence | Procédure conso art. 5.2.3 |
| Acceptation | Conditions particulières signées sans réserve, preuve de maîtrise foncière, acompte, et soit un justificatif d'avancement (annexe 2) soit 1 k€ par MW | Procédure conso art. 5.2.1 |
| Entrée en file d'attente | À la date d'acceptation, notifiée par courriel | Procédure conso art. 6.1 |
| Maintien annuel | À chaque anniversaire, justificatif d'avancement ou 1 k€ par MW, le versement n'étant possible que deux fois (une seule si déjà versé à l'acceptation). Les justificatifs de phase d'étude ne sont acceptés que 24 mois après acceptation | Procédure conso art. 6.2.1 |
| Perte de rang | Défaut de justification, convention non acceptée, modification significative de la solution, absence de soutirage 2 ans après mise à disposition, défaut de paiement | Procédure conso art. 6.3.1 |
| Confirmation de solution | Courriel avec la référence de l'étude exploratoire et la mention « Demande de confirmation de la Solution de Raccordement », réponse sous 15 jours ouvrés | Procédure conso art. 4 |

Deux points nouveaux méritent d'entrer dans le dashboard. D'abord, le **compteur de versements forfaitaires** : la faculté de payer 1 k€ par MW au lieu de justifier l'avancement est limitée à deux occurrences sur toute la vie du dossier, ce qui, à 600 MW, représente 600 k€ par occurrence. Ensuite, le **dispositif « fast-track » datacenter** de RTE : six sites validés, délai de raccordement ramené sous 4 ans, réduction de 30 pour cent sur les liaisons de raccordement principales et sur les contributions aux congestions, en contrepartie d'un permis de construire obtenu sous 15 mois après signature. Ce n'est pas une démarche à automatiser mais une échéance à suivre pour un site qui en bénéficierait.

### 1.2 Enedis, raccordement HTA et alimentation de chantier

Deux parcours distincts, pour deux besoins distincts.

**Le site de moins de 40 MW raccordé en HTA.** Au titre de l'article 105 de l'arrêté du 9 juin 2020, un site sous 40 MW et suffisamment loin du poste de transformation relève d'Enedis, pas de RTE. La demande passe par le **Portail Raccordement** (connect-racco.enedis.fr), qui exige un compte, comme le Portail Services RTE. Le portail entreprise grand public (raccordement-entreprise-enedis.fr) ne traite que la basse tension. Le parcours HTA consommateur, d'après la procédure Enedis « client consommateur HTA », est le suivant.

| Étape | Délai opposable | Remarque |
|---|---|---|
| Qualification de la demande | Le demandeur a 3 mois pour compléter son dossier ; la date de qualification fixe le rang en file d'attente | Autorisation d'urbanisme obligatoire à la qualification, ce qui n'existe pas côté RTE au stade de la PTF |
| Proposition de raccordement (PDR) | 1 mois en cas simple, 3 mois avec étude, comptés depuis la qualification | Équivalent de la PTF RTE |
| Validité de la PDR | 3 mois, sans prorogation | Acompte à l'acceptation, formule progressive (50 pour cent jusqu'à 10 k€, puis dégressive) |
| Convention de raccordement | 9 mois après acceptation en HTA, 12 mois si des ouvrages RTE sont nécessaires | Validité 3 mois |
| Travaux puis mise en service | Délai fixé dans la PDR ; mise en service 10 jours ouvrés, 5 en express ; pénalité de 1 500 € par dépassement en HTA | Attestation CONSUEL NF C 13-100 exigée |

Aucune étude exploratoire gratuite équivalente à celle de RTE n'apparaît dans la procédure consommateur HTA. Enedis propose des prestations d'étude payantes au catalogue et un simulateur en ligne pour les petites puissances, sans valeur d'engagement. Point à vérifier au premier dossier : si Enedis accepte une « pré-étude » informelle par l'Accueil Raccordement régional, comme cela se pratique sur les gros projets tertiaires.

**L'alimentation de chantier et les auxiliaires.** Pour un site raccordé à RTE, la phase travaux a besoin d'un branchement provisoire ou d'un compteur définitif de faible puissance (tarif jaune, moins de 250 kVA). Cela se demande sur le portail entreprise BT d'Enedis, avec le permis, le plan de masse, la puissance et l'échéance. Devis valable 3 mois, acompte à la signature. C'est le parcours le plus simple des quatre, et le seul où une demande anticipée (avant permis) est explicitement prévue pour les zones d'aménagement.

### 1.3 GRDF, raccordement gaz

Le point d'entrée entreprise est le formulaire en ligne `monespace.grdf.fr/demande-raccordement-reseau-gaz/entreprise`. Il est **public, sans compte** : il commence par l'adresse du bâtiment pour contrôler l'éligibilité au réseau, puis déroule les questions sur le projet. GRDF affecte ensuite un interlocuteur, envoie la proposition technique et financière par e-mail, **signable en ligne**, puis coordonne les travaux et réalise la mise en service. À partir de 10 projets par an, une entreprise peut demander un contact privilégié : Castignac y sera vite.

| Élément | Ce qui est établi | Source |
|---|---|---|
| Canal | Formulaire public en ligne, puis échange avec un conseiller ; offre par e-mail, signature électronique | grdf.fr, relevé du 10/09 |
| Délai du devis | De l'ordre de 8 jours ouvrés pour un raccordement standard, environ un mois si étude, sources secondaires | fournisseurs-electricite.com, Selectra |
| Tarifs standard | Forfaits du catalogue des prestations pour un branchement de moins de 35 m : environ 1 740 € TTC pour la classe 16 à 650 Nm3/h ; tout le reste sur devis | Catalogue des prestations GRDF juillet 2026, via source secondaire |
| Travaux | De 10 jours ouvrés à 2 mois selon complexité ; extension de réseau sur devis | Sources secondaires |
| Mise en service | Certificat de conformité Qualigaz ou équivalent, numéro PCE, souscription auprès d'un fournisseur | grdf.fr |

Le catalogue des prestations 2026 est référencé sur grdf.fr mais son lien de téléchargement renvoyait une erreur le 10/09 : les délais et les seuils de débit sont à confirmer sur le PDF quand GRDF l'aura remis en ligne, ou directement avec le conseiller. Point important à garder en tête même si le choix de GRDF est acquis : un groupe de secours ou une cogénération de plusieurs dizaines de MW demande un débit qui dépasse en général la distribution en moyenne pression et relève de GRTgaz. Tant que l'usage du gaz sur les projets n'est pas arrêté, le dashboard prévoit un champ « débit demandé en Nm3/h » qui déclenchera une alerte au-delà d'un seuil à caler avec GRDF.

### 1.4 Ce qui vaut pour les quatre filières

**Aucun des trois opérateurs n'expose d'API de raccordement.** RTE n'a que des API de données de marché, Enedis un Data Hub limité aux données de comptage, GRDF l'API ADICT limitée elle aussi à la consommation. Les seuls canaux sont des formulaires web avec compte (RTE D1, Enedis HTA), un formulaire web public (GRDF), et le courriel (RTE D2, confirmation de solution). Cela fixe la nature de l'automatisation : préparation des dossiers, pré-remplissage par robot navigateur ou génération de PDF et de courriels, suivi des échéances, et **jamais d'envoi automatique**.

---

## 2. Automatisable, manuel, hors de portée

| Filière | Automatisable | Manuel, dernier clic | Hors de portée |
|---|---|---|---|
| RTE étude exploratoire (D1) | Fait : payload, checklist, robot Playwright sur les 5 étapes | Certification et envoi sur le portail | Numéro de dossier après envoi, dépouillement du PDF d'étude |
| RTE PTF (D2) | Génération de la D2 remplie en PDF, contrôle de cohérence avec la D1, brouillon Outlook avec pièces et objet normalisé, échéancier | Virement des 42 k€ HT et envoi du courriel | Contenu de la PTF, prorogations négociées |
| RTE confirmation de solution | Brouillon de courriel avec la référence d'étude et la mention exacte exigée | Envoi | |
| RTE file d'attente | Échéancier anniversaire, compteur de versements forfaitaires, génération du justificatif d'avancement annexe 2 à partir du dashboard | Choix justificatif ou versement, envoi | |
| Enedis HTA | Dossier de qualification, robot sur le Portail Raccordement après relevé des champs, échéancier 3 mois puis 1 ou 3 mois | Envoi, acceptation de la PDR, acompte | Le relevé du formulaire exige un compte Enedis, comme pour RTE |
| Enedis chantier | Pré-remplissage du portail BT entreprise, échéancier | Envoi, signature du devis | |
| GRDF | Pré-remplissage du formulaire public, échéancier, relance à 15 jours sans devis | Envoi, signature électronique de l'offre | Débit exact avant que l'usage du gaz soit arrêté |

Trois enseignements. Le **courriel devient un canal à part entière** : RTE D2 et confirmation de solution ne passent que par là. Le brouillon Outlook, déjà étudié dans le projet d'add-in, est la bonne brique : l'outil crée le brouillon avec les pièces, l'humain relit et envoie. Le **relevé des formulaires** Enedis et GRDF est la seule étape de mise en route bloquante, comme l'était celui du Portail Services RTE : il faut un compte Enedis et une session ouverte pour capturer les sélecteurs, et GRDF se relève sans compte mais avec une adresse réelle. Enfin, la **règle des sélecteurs par libellé, jamais par identifiant**, apprise sur le formulaire Angular de RTE, vaut a priori pour les deux autres portails.

---

## 3. Le dashboard retravaillé

Le dashboard précédent suivait une seule chaîne RTE en 8 étapes, du dossier au maintien en file d'attente. La refonte le fait passer à un modèle **projet × filière** : un projet (un site) porte jusqu'à quatre demandes indépendantes, chacune sur sa propre chaîne avec ses délais. Les demandes existantes sont reprises automatiquement dans la filière RTE étude exploratoire.

| Filière | Chaîne | Échéances calculées |
|---|---|---|
| RTE EE | Préparation, prêt pour validation, déposé, étude en cours, étude reçue, confirmation demandée, clos | Recevabilité 8 j.o., remise 6 semaines et prévisionnel calibré, relance à 6 semaines, confirmation 15 j.o. |
| RTE PTF | Préparation, prêt pour envoi, déposé, en instruction, PTF reçue, acceptée en file d'attente, convention | Recevabilité 8 j.o., remise 3 mois, validité 3 mois (+3 si prorogée), maintien annuel, compteur de versements |
| Enedis | Préparation, prêt pour validation, déposé, qualifiée, PDR reçue, acceptée, convention, mise en service | Dossier complet 3 mois, PDR 1 ou 3 mois, validité 3 mois, convention 9 ou 12 mois |
| GRDF | Préparation, prêt pour envoi, déposé, devis reçu, accepté, travaux, mise en service | Devis 8 j.o. (ou 1 mois si étude), relance à 15 jours, validité du devis |

La page conserve le bandeau d'alertes, la fiche éditable par demande et la base partagée. Elle ajoute la **matrice projet × filière** en tête, des filtres par filière, et pour chaque filière son propre rail d'étapes. La note sur le dernier clic humain vaut désormais pour les quatre filières et pour le courriel.

Pour un suivi à deux sur des dossiers à échéances longues, deux choses manquent encore et sont prévues dans la version serveur : un **journal des changements** (qui a passé quel dossier à quel statut, et quand, ce qui compte quand on calcule un délai opposable face à RTE), et des **alertes envoyées par e-mail** aux deux suiveurs la veille d'une échéance, pour que rien ne dépende de l'ouverture de la page. La vue par projet doit permettre à quelqu'un qui n'a pas ouvert l'outil depuis un mois de comprendre l'état d'un site en une page.

---

## 4. Architecture cible sur le serveur interne

Le principe est de séparer ce qui a besoin d'une session humaine de ce qui n'en a pas besoin.

```
   Poste Windows de l'utilisateur
      robots Playwright (RTE, Enedis, GRDF), profils de navigateur, brouillons Outlook
      lisent les payloads et écrivent les statuts via l'API interne
              |
              v  HTTPS, réseau interne
   Serveur interne Castignac
      API Python (FastAPI) + base SQLite ou PostgreSQL : projets, demandes, échéances, pièces
      dashboard (la page actuelle, le stockage partagé remplacé par l'API)
      tâches planifiées : recalcul des échéances, alertes par e-mail, sauvegardes
              |
              v  Cloudflare Tunnel, aucun port ouvert
   Cloudflare Access : authentification par e-mail @castignac avant d'atteindre la page
```

Trois choix à défendre. Les **robots restent sur le poste** : les portails RTE et Enedis demandent un code par e-mail à la connexion et gardent une session, ce qui exige un navigateur qu'un humain peut voir ; le serveur ne fait pas tourner de navigateur. Le **registre JSON devient une base sur le serveur** derrière une API de quelques routes (projets, demandes, échéances, pièces, journal), le dashboard et les robots parlant à la même source de vérité ; la page actuelle n'a besoin que de remplacer ses appels de stockage par des appels HTTP. L'**exposition passe par Cloudflare Tunnel plus Cloudflare Access** plutôt que par une ouverture de port : le serveur sort vers Cloudflare, rien n'entre, et Access n'admet que les deux adresses e-mail des suiveurs, avec journal des connexions. C'est le montage déjà pratiqué sur le serveur personnel, transposable tel quel. À deux utilisateurs, l'application elle-même n'a ni comptes ni rôles : l'identité vient de l'en-tête que Cloudflare Access ajoute à chaque requête, et sert uniquement à signer le journal des changements.

Les pièces (extraits cadastraux, plans, PDF d'études, PTF) sont stockées sur le serveur dans un dossier par projet, référencées par la base, et jamais exposées sur Internet autrement qu'à travers la page authentifiée.

---

## 5. Ordre de réalisation (révisé le 17/09/2026)

Le suivi d'abord, parce qu'il sert dès le premier jour et que tout le reste s'y branche.

1. **Registre sur le serveur** : base projets × demandes × échéances × pièces × journal, API de quelques routes, calcul des échéanciers par filière côté serveur. Réutilise le noyau du 03/09. Détail dans le cahier des charges du 17/09.
2. **Dashboard branché sur le registre**, exposé par Cloudflare Tunnel et Access sur deux adresses. Journal des changements et alertes e-mail quotidiennes.
3. **RTE PTF** : générateur de fiche D2 PDF et brouillon Outlook, le plus rentable des automatismes car sans robot.
4. **GRDF** : relevé du formulaire public avec une adresse réelle, puis robot. Pas de compte, donc réalisable à tout moment.
5. **Enedis** chantier puis HTA : relevé après ouverture du compte sur le Portail Raccordement.
6. Reprise du robot D1 existant pour qu'il lise ses payloads dans le registre serveur au lieu du JSON local.

---

## Sources

RTE, procédure de traitement des demandes de raccordement des installations de consommation au RPT, DTR article 1.4.1 version 5 du 29 juin 2024 approuvée par la CRE (délibération 2024-96), unifiée depuis à l'article 1.2.2 (délibération 2026-32). RTE, fiche de collecte D2 consommation v2. RTE Portail Services, page « Raccorder une installation au RPT » (étapes, adresses de contact, dispositif fast-track datacenter). Enedis, procédure de raccordement client consommateur HTA, procédure de traitement des demandes de raccordement Enedis-NMO-RES_030E v3 du 25/08/2026, modèle de proposition de raccordement, page « Entreprises, demander le raccordement ». GRDF, page entreprises « Raccordement gaz en 4 étapes », formulaire monespace.grdf.fr, page du catalogue des prestations au 1er juillet 2026. Sources secondaires pour les délais et forfaits GRDF : fournisseurs-electricite.com, entreprises.selectra.info.
