# Amont 0.5 : extraits cadastraux

Note du 27/10/2026. Amont récupère tout seul l'extrait du plan cadastral officiel de chaque site, la pièce sans
laquelle RTE déclare une demande d'étude exploratoire irrecevable sous 8 jours ouvrés.

---

## 1. Le document

« Extrait du plan cadastral » de la DGFiP, celui du bouton « Imprimer > Extrait de plan » de cadastre.gouv.fr :
cartouche officiel (département, commune, section, feuille, échelle, date d'édition, centre des impôts fonciers).
Gratuit, sans compte. Environ 35 ko par parcelle seule, 300 ko pour un site de 10 parcelles (limite RTE : 2 Mo).

Le service ne dessine qu'une commune par impression. Un site sur plusieurs communes donne donc **une page par commune**,
assemblées dans un seul PDF (le portail RTE n'accepte qu'un fichier), la commune du point de raccordement en premier.
Le cadre (A4 ou A3, portrait ou paysage) et l'échelle (1/500 à 1/5000) sont choisis pour contenir les parcelles avec
une marge, au plus détaillé possible.

## 2. Ce qu'il faut dans la fiche du site

| Champ | Exemple |
|---|---|
| Parcelles cadastrales | `AH 367, AH 381` ou, sur plusieurs communes, `Sochaux : AH 367, AH 381 ; Exincourt : AD 45, AD 46` |
| Commune du point de raccordement | Sochaux |
| Département ou code INSEE | 25 ou 25547 |
| Autres communes du site | Exincourt (si les parcelles ne précisent pas leur commune) |

Sans commune devant les parcelles, chacune est cherchée dans toutes les communes du site. Une même référence peut exister
dans deux communes voisines (à Sochaux, AD 46 et AE 27 existent aussi côté Sochaux, alors que celles du site sont à
Exincourt) : Amont garde celle qui touche les autres parcelles et **crée un point « à vérifier »** sur le champ Parcelles.
Écrire la commune devant les parcelles supprime le doute.

## 3. Depuis le site

- **Fiche du site** (Sites, puis le site) : bloc « Extrait cadastral », bouton « Récupérer l'extrait cadastral ».
  Options : centrer sur une parcelle (extrait plus serré autour du point de raccordement), échelle imposée.
- **Fiche d'une demande RTE EE** : bouton sous les pièces, même chose.

Durée : 20 s à 1 min. Le PDF est rangé dans les sources du site (type Cadastre) et joint comme « extrait cadastral »
à chaque demande RTE étude exploratoire du site. Le robot D1 joint au portail **l'extrait le plus récent** de la demande :
retirer les anciens avec × pour garder la liste propre.

## 4. Pour tous les sites d'un coup

Depuis le dossier Amont du poste, Tailscale connecté :

```
python 2026_10_27_amont_extraits_cadastraux.py --liste                # état : extrait fait ou non, parcelles
python 2026_10_27_amont_extraits_cadastraux.py                        # tous les sites qui n'ont pas encore d'extrait
python 2026_10_27_amont_extraits_cadastraux.py --site SOC --forcer    # refaire un site
python 2026_10_27_amont_extraits_cadastraux.py --site SOC --centrer "AH 367" --echelle 2500
```

Sans Amont, directement vers un dossier :

```
python 2026_10_27_amont_extraits_cadastraux.py --parcelles "AH 367, AH 381" --commune Sochaux --departement 25 --sortie .
```

Aujourd'hui, seul Sochaux a ses parcelles dans sa fiche : les six autres sites sont ignorés tant que le champ
« Parcelles cadastrales » est vide (le DatacenterSiteAnalyzer ou le dépôt d'une étude de faisabilité le remplit).

## 5. Si ça échoue

| Message | Piste |
|---|---|
| cadastre.gouv.fr ne répond pas (HTTP 503) | le service renvoie des 503 par intermittence ; Amont réessaie cinq fois sur une minute, puis abandonne. Relancer plus tard |
| aucune parcelle trouvée | référence mal écrite ou mauvaise commune : vérifier sur cadastre.gouv.fr, préciser « Commune : parcelles » |
| commune ambiguë | deux communes du même nom dans le département : écrire le nom exact |
| les parcelles débordent du cadre | site trop étendu pour du 1/5000 en A3 : extrait centré sur la parcelle du point de raccordement |

## 6. Technique

Module `amont_core/cadastre.py`, bibliothèque standard seulement (plus `pypdf` pour assembler les pages, ajouté aux
dépendances du serveur). Parcours relevé le 27/10/2026 : session, recherche par référence cadastrale, carte de la parcelle
(emprise et projection), impression de l'extrait normalisé. Une seconde de pause entre deux requêtes. Si cadastre.gouv.fr
change ses pages, c'est ce module qu'il faudra reprendre.

## 7. Mise à jour du serveur

Depuis PowerShell :

```powershell
$src = "C:\Castignac\Codes castignac(archive nicolas)\Automatisation étude explo\Amont"
$vm = "alexis@100.116.240.111"
scp -r "$src\amont_core" "$src\static" "${vm}:~/amont/"
scp "$src\docker-compose.yml" "$src\amont_config.json" "$src\requirements.txt" "${vm}:~/amont/"
```

Sur la VM :

```bash
cd ~/amont && cp donnees/amont.sqlite donnees/amont_avant_0.5.sqlite && docker compose up -d --build && sleep 5 && curl -s localhost:8010/api/sante ; echo
```

Attendu : `"version":"0.5.0"`. Le conteneur doit pouvoir joindre cadastre.gouv.fr (accès Internet sortant de la VM).
