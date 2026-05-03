# SpectroStars Finder

**SpectroStars Finder** est un outil de recherche d'étoiles proches conçu pour faciliter la sélection d'étoiles de référence spectroscopiques. Il permet de filtrer les étoiles d'un catalogue en fonction de leur position, de leur altitude locale et de leur proximité avec une cible donnée.

### Usage rapide
* **Ligne de commande** : `python star_finder.py --help`
* **Interface graphique** : `python star_finder_gui.py`

*Logiciel propulsé par Astropy, Astroquery et Pandas.*

---

### Crédits et Sources

Ce programme est basé sur le catalogue et la méthodologie de **François Teyssier** et **Serge Golovanow** : [https://spectro-starfinder.net](https://spectro-starfinder.net). 

Le catalogue `base.csv` a été mis à jour avec la liste d'étoiles **Melchior** du projet **Staros** : [https://search.staros-projects.org/](https://search.staros-projects.org/) 

---

## Installation

Assurez-vous d'avoir Python installé, puis installez les bibliothèques nécessaires : pip install pandas astropy astroquery

Spécificité Linux (interface graphique) : sur certaines distributions vous devrez peut-être installer le support Tkinter manuellement :
apt install python3-tk

Pour que le programme fonctionne, les fichiers suivants doivent rester dans le même répertoire :

    star_finder.py : Le moteur de calcul (CLI).

    star_finder_gui.py : L'interface utilisateur (GUI).

    base.csv : Le catalogue d'étoiles (Melchior/SpectroStars). En cas de modification du catalogue, veillez à conserver la structure des colonnes pour assurer la compatibilité avec le moteur de recherche.  

    observer.ini : Vos paramètres d'observation. Éditez ce fichier avec un éditeur de texte pour définir votre position géographique exacte.

Dépannage

    Le programme se ferme immédiatement : Vérifiez que base.csv et observer.ini sont bien présents dans le dossier.  

    Erreur SIMBAD : Une connexion internet est requise pour résoudre le nom des cibles (ex: "Vega") via Astroquery.  

    Permissions (Linux) : Si vous utilisez une version compilée, n'oubliez pas le chmod +x.