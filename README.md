# spectro-starfinder

Outil de recherche d'**étoiles de référence** pour la spectroscopie amateur.

À partir d'une cible (nom SIMBAD, coordonnées RA/Dec, ou **entêtes FITS d'une
séquence d'acquisition**), l'outil recherche dans un catalogue les étoiles
utilisables pour la calibration de la réponse instrumentale, en privilégiant
celles présentes dans les bibliothèques spectrales **MILES** et **MELCHIORS**.

La sélection ne se fait pas seulement par proximité angulaire : l'outil calcule
l'**altitude et la masse d'air** de chaque candidate à l'instant considéré, et
les classe par écart à une **hauteur visée** — celle à laquelle la cible a
réellement été observée. C'est cette égalité de masse d'air qui conditionne la
qualité de la correction d'extinction atmosphérique.

Ce projet s'inspire largement de
[SpectroStars](https://github.com/serge-golovanow/SpectroStars) par
Serge Golovanow.

## Contenu du dépôt

| Fichier | Rôle |
|---|---|
| `star_finder.py` | Moteur de calcul (résolution SIMBAD, séparation angulaire, alt/az, filtres). Utilisable en ligne de commande. |
| `star_finder_gui.py` | Interface graphique (Tkinter, thème sombre) avec graphes de trajectoire. |
| `fits_target.py` | Lecture des entêtes FITS d'acquisition, trajectoire altitude/masse d'air de la cible. |
| `base.csv` | Catalogue d'étoiles (colonnes `Name, RA, Dec, Vmag, SpType, B-V, Ebv, Miles, Sp_s, Melchiors`). |
| `observer.ini` | Position de l'observateur (latitude, longitude, altitude). À adapter à votre lieu. |

## Installation

Nécessite Python 3.9+ et les dépendances suivantes :

```bash
pip install astropy astroquery pandas numpy matplotlib
```

Tkinter est inclus avec la plupart des distributions Python. Sous Linux, il peut
être nécessaire de l'installer séparément :

```bash
# Debian / Ubuntu
sudo apt install python3-tk
```

## Configuration de l'observateur

Éditez `observer.ini` pour renseigner votre lieu d'observation :

```ini
[observer]
latitude  = 42.936    ; degrés décimaux, positif = Nord
longitude = 0.143     ; degrés décimaux, positif = Est
elevation = 2880      ; altitude en mètres
name      = Pic du Midi   ; nom libre (optionnel)
```

Si les entêtes FITS chargés contiennent un site (`SITELAT` / `SITELONG` /
`SITEELEV`), celui-ci est utilisé **de préférence** à `observer.ini`. La source
retenue est indiquée dans le panneau de droite (« Site : entête FITS » ou
« observer.ini »).

## Utilisation

### Interface graphique

```bash
python star_finder_gui.py
```

Au lancement, l'appli charge automatiquement `base.csv` et `observer.ini` s'ils
se trouvent dans le répertoire courant.

#### Choix de la cible

Trois modes, sélectionnables dans le panneau *Cible* :

- **Nom SIMBAD** — résolution en ligne du nom saisi ;
- **RA / Dec** — coordonnées sexagésimales (`10:01:04` / `+40:10:20`) ;
- **Depuis FITS** — activé automatiquement après chargement d'une séquence
  d'acquisition (voir ci-dessous).

#### Cible depuis les FITS

*Fichier ▾ → Charger des FITS de la cible…* (ou le bouton **Choisir des FITS…**)
lit les entêtes d'un lot de poses et en déduit la trajectoire réelle de la cible.

Mots-clés exploités : `DATE-OBS`, `EXPTIME`, `OBJCTRA` / `OBJCTDEC` (ou `RA` /
`DEC`), `OBJECT`, `SITELAT` / `SITELONG` / `SITEELEV`, et à titre indicatif
`OBJCTALT` / `AIRMASS`. Le format est celui écrit par CCDciel (entêtes
INDI/ASCOM standards) ; d'autres logiciels passent en général sans adaptation.

Ce que fait le chargement :

- calcul de l'altitude, de l'azimut et de la **masse d'air** au milieu de chaque
  pose (`DATE-OBS` + `EXPTIME`/2) ;
- affichage du nombre de poses, du nom de l'objet, de la plage horaire, de la
  **hauteur moyenne** et de la masse d'air moyenne correspondante ;
- préremplissage de la **hauteur visée** avec cette hauteur moyenne ;
- alignement de la date/heure de recherche sur la dernière pose, et des champs
  RA/Dec sur la cible lue ;
- aucun filtrage automatique des fichiers : tous ceux que vous sélectionnez sont
  utilisés. Si les pointages diffèrent de plus de 0,5°, un avertissement signale
  que la sélection mélange probablement plusieurs cibles — sans rien retirer.

La masse d'air est calculée par la formule de **Kasten & Young (1989)**, qui
reste valable près de l'horizon là où sec(z) diverge.

#### Filtres

- **Rayon max (°)** — séparation angulaire maximale à la cible (30° par défaut).
- **|Δh| max (°)** — écart maximal entre l'altitude de l'étoile et la hauteur
  visée (10° par défaut ; vide = inactif).
- **Alt min (°)** — altitude minimale au-dessus de l'horizon (vide = inactif).
- **Type** — boutons-bascule `O B A F G K M` (B et A actifs par défaut).

Les filtres de hauteur nécessitent une date/heure d'observation. Les boutons
*Maintenant* et *Effacer* agissent sur le couple date/heure (UTC).

#### Hauteur visée et colonne Δh

La **hauteur visée** est la référence de tout le classement : `Δh = altitude de
l'étoile − hauteur visée`. Le tableau est trié par |Δh| croissant, donc par
masse d'air la plus proche de celle de la cible.

Elle vaut par défaut :

- en mode FITS : la hauteur moyenne des poses ;
- en mode nom/RA-Dec : l'altitude de la cible à l'heure choisie.

Elle se règle ensuite **à la souris**, en faisant glisser la ligne rouge
pointillée sur le graphe de gauche. Le champ et la barre de statut affichent en
direct la hauteur et la masse d'air correspondante ; au relâchement, la colonne
Δh est recalculée et le tableau re-trié. Pratique pour explorer « et si je vise
plutôt 45° ? » sans relancer la recherche.

#### Graphes de trajectoire

Deux panneaux apparaissent sous les filtres dès qu'une recherche ou un
chargement FITS a eu lieu :

- **Gauche — la cible.** Arc d'altitude sur ±45 min. En mode FITS, chaque pose
  est dessinée comme un rectangle dont la largeur est le temps d'exposition et
  la hauteur la plage d'altitude balayée pendant la pose ; la hauteur moyenne
  apparaît en pointillés. En mode nom/RA-Dec, un point marque l'instant choisi.
  La ligne rouge pointillée est la hauteur visée, déplaçable.
- **Droite — l'étoile de référence** sélectionnée dans le tableau (un simple
  clic sur une ligne). L'arc est centré sur l'instant de référence (fin de la
  dernière pose en mode FITS, heure choisie sinon), avec des repères à
  **+0, +10, +20 et +30 min** annotés de leur masse d'air : de quoi juger si
  l'étoile sera encore à la bonne hauteur le temps d'aller la pointer et de
  poser dessus.

Les deux panneaux partagent la même échelle d'altitude, la comparaison visuelle
est donc directe.

#### Tableau de résultats

Colonnes : `Nom`, `Sep (°)`, `Az (°)`, `Alt (°)`, `Δh (°)`, `Airmass`, `Vmag`,
`SpType`, `Cat`, `RA`, `Dec`, `B-V`, `Ebv`. Toutes triables par clic sur
l'en-tête.

- La colonne **Cat** indique l'appartenance aux bibliothèques : `Miles`,
  `Melch`, ou `M+Mel`. Les étoiles MILES sont affichées en vert, MELCHIORS en
  orange.
- Un symbole **⚠** signale les valeurs de E(B–V) supérieures à 0,3.

#### Menu contextuel (clic droit sur une ligne)

- **Copier le nom de l'étoile**
- **Ouvrir la page SIMBAD**
- **Type spectral (Skiff) dans VizieR** — interroge directement le catalogue
  `B/mk/mktypes` (*Catalogue of Stellar Spectral Classifications*, Skiff) dans
  un rayon de 5″ autour de l'étoile, pour vérifier ou affiner un type spectral
  douteux.

#### Menu Fichier

Le bandeau de menu a été remplacé par un bouton **Fichier ▾** (plus de place
pour les graphes) :

- choisir le catalogue (`base.csv`) ;
- choisir la config observateur (`observer.ini`) ;
- charger des FITS de la cible ;
- exporter les résultats au format CSV ;
- quitter.

### Ligne de commande

Le moteur `star_finder.py` s'utilise aussi seul (recherche par proximité
angulaire ; les fonctions de masse d'air et de hauteur visée sont propres à
l'interface graphique) :

```bash
# Par nom SIMBAD, maintenant
python star_finder.py --target "Vega" --radius 10 --datetime now

# Par nom, date précise (ISO 8601, UTC)
python star_finder.py --target "M27" --radius 5 --datetime "2025-08-15T22:30:00"

# Par coordonnées RA/Dec (degrés décimaux J2000)
python star_finder.py --ra 279.2347 --dec 38.7837 --radius 10 --datetime now

# Filtres de hauteur et de type spectral
python star_finder.py --target "Deneb" --radius 8 --datetime now --min-alt 20
python star_finder.py --target "M27"   --radius 10 --datetime now --max-dalt 5
python star_finder.py --target "Vega"  --radius 10 --datetime now --sp-type B A
```

Options principales : `--target` / `--ra` + `--dec`, `--radius`, `--max`,
`--catalog`, `--config`, `--datetime`, `--min-alt`, `--max-dalt`, `--sp-type`.

## À propos de la colonne E(B–V)

`Ebv` est l'**excès de couleur** dû au rougissement interstellaire :
E(B–V) = (B–V)<sub>observé</sub> − (B–V)<sub>intrinsèque</sub>.

Le symbole ⚠ au-delà de 0,3 est **informatif, pas disqualifiant** : les spectres
MILES sont des spectres *observés*, non dérougis, et la réponse instrumentale
déduite d'une étoile MILES rougie reste correcte puisque le rougissement est
déjà présent dans le spectre de référence. L'indication sert surtout à
comprendre la pente du continuum observé et à repérer les cas où l'étoile
servirait de référence via un modèle de type spectral plutôt que via son spectre
tabulé.

Note : la colonne `Ebv` n'est pas renseignée pour toutes les étoiles MELCHIORS.

## Crédits

Ce projet reprend et adapte largement le travail de Serge Golovanow,
[SpectroStars](https://github.com/serge-golovanow/SpectroStars).

## Licence

Ce projet est distribué sous licence **MIT** (voir le fichier `LICENSE`).
