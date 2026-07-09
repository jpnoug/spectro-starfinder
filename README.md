# spectro-starfinder

Outil de recherche d'**étoiles de référence** pour la spectroscopie amateur.

À partir d'une cible (nom SIMBAD ou coordonnées RA/Dec), l'outil recherche dans un
catalogue les étoiles les plus proches angulairement, avec filtrage optionnel sur
la hauteur au-dessus de l'horizon au moment de l'observation. Il privilégie les
étoiles présentes dans les bibliothèques spectrales de référence **MILES** et
**MELCHIORS**, utiles pour la calibration de la réponse instrumentale.

Ce projet s'inspire largement de
[SpectroStars](https://github.com/serge-golovanow/SpectroStars) par
Serge Golovanow.

## Contenu du dépôt

| Fichier | Rôle |
|---|---|
| `star_finder.py` | Moteur de calcul (résolution SIMBAD, séparation angulaire, alt/az, filtres). Utilisable en ligne de commande. |
| `star_finder_gui2.py` | Interface graphique (Tkinter, thème sombre). |
| `base.csv` | Catalogue d'étoiles (colonnes `Name, RA, Dec, Vmag, SpType, B-V, Ebv, Miles, Sp_s, Melchiors`). |
| `observer.ini` | Position de l'observateur (latitude, longitude, altitude). À adapter à votre lieu. |

## Installation

Nécessite Python 3.9+ et les dépendances suivantes :

```bash
pip install astropy astroquery pandas
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
elevation = 200        ; altitude en mètres
name      = PBO        ; nom libre (optionnel)
```

## Utilisation

### Interface graphique

```bash
python star_finder_gui2.py
```

Au lancement, l'appli charge automatiquement `base.csv` et `observer.ini` s'ils
se trouvent dans le répertoire courant. Renseignez une cible, ajustez les filtres,
puis lancez la recherche.

Fonctionnalités de l'interface :

- **Cible** par nom SIMBAD ou par coordonnées RA/Dec sexagésimales.
- **Date / heure** préremplies (date du jour, 21:00 UTC par défaut) pour le calcul
  de la hauteur ; boutons *Maintenant* et *Effacer*.
- **Filtres** : rayon de recherche, |ΔAlt| max par rapport à la cible, altitude
  minimale, nombre maximum de résultats, et sélection par **type spectral**
  (B et A cochés par défaut).
- **Tableau de résultats** triable par colonne ; les étoiles MILES et MELCHIORS
  sont mises en évidence.
- **Avertissement de rougissement** : un symbole ⚠ signale les étoiles dont
  E(B–V) dépasse 0,3 (rougissement interstellaire notable).
- **Clic droit** sur une ligne : copier le nom de l'étoile, ou ouvrir sa fiche
  SIMBAD dans le navigateur.

### Ligne de commande

Le moteur `star_finder.py` s'utilise aussi seul :

```bash
# Par nom SIMBAD, maintenant
python star_finder.py --target "Vega" --radius 10 --datetime now

# Par nom, date précise (ISO 8601, UTC)
python star_finder.py --target "M27" --radius 5 --datetime "2025-08-15T22:30:00"

# Par coordonnées RA/Dec (degrés décimaux J2000)
python star_finder.py --ra 279.2347 --dec 38.7837 --radius 10 --datetime now

# Filtres de hauteur
python star_finder.py --target "Deneb" --radius 8 --datetime now --min-alt 20
python star_finder.py --target "M27"   --radius 10 --datetime now --max-dalt 5
```

## Colonne E(B–V)

Note : la colonne `Ebv` n'est pas renseignée pour toutes les étoiles MELCHIORS.
Un symbole ⚠ dans l'interface signale les valeurs > 0,3.

## Crédits

Ce projet reprend et adapte largement le travail de Serge Golovanow,
[SpectroStars](https://github.com/serge-golovanow/SpectroStars).

## Licence

Ce projet est distribué sous licence **MIT** (voir le fichier `LICENSE`).
