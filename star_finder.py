#!/usr/bin/env python3
"""
star_finder.py — Sélection d'étoiles proches dans le catalogue SpectroStars (base.csv)

Recherche les étoiles du catalogue les plus proches angulairement d'une cible
donnée, avec filtrage optionnel sur la hauteur (altitude) au-dessus de l'horizon
au moment de l'observation.

La position de l'observateur est lue depuis un fichier INI (observer.ini par défaut).
La date/heure d'observation est passée en argument (format ISO 8601, UTC).

Utilisation :
    # Par nom SIMBAD, maintenant :
    python star_finder.py --target "Vega" --radius 10 --datetime now

    # Par nom, date précise :
    python star_finder.py --target "M27" --radius 5 --datetime "2025-08-15T22:30:00"

    # Par coordonnées RA/Dec (degrés décimaux J2000) :
    python star_finder.py --ra 279.2347 --dec 38.7837 --radius 10 --datetime now

    # Filtrer sur la hauteur minimale :
    python star_finder.py --target "Deneb" --radius 8 --datetime now --min-alt 20

    # Filtrer sur la différence de hauteur avec la cible (±5° par défaut) :
    python star_finder.py --target "M27" --radius 10 --datetime now --max-dalt 5

    # Combinaison des deux filtres :
    python star_finder.py --target "Vega" --radius 10 --datetime now --min-alt 20 --max-dalt 5

    # Fichier de config observateur personnalisé :
    python star_finder.py --target "Vega" --radius 10 --datetime now --config mon_obs.ini

Dépendances :
    pip install astropy astroquery pandas
"""

import argparse
import configparser
import sys
import warnings
from datetime import datetime, timezone

import pandas as pd
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.time import Time
from astropy import units as u

warnings.filterwarnings("ignore")  # supprime les warnings astropy/astroquery verbeux


# ---------------------------------------------------------------------------
# Configuration observateur (observer.ini)
# ---------------------------------------------------------------------------

def load_observer(config_file: str) -> EarthLocation:
    """
    Lit le fichier INI et retourne un EarthLocation astropy.

    Section attendue : [observer]
    Clés : latitude (°), longitude (°), elevation (m).
    """
    cfg = configparser.ConfigParser()
    found = cfg.read(config_file)
    if not found:
        sys.exit(
            f"[ERREUR] Fichier de configuration introuvable : {config_file}\n"
            f"         Créez un fichier '{config_file}' avec la section [observer]\n"
            f"         contenant latitude, longitude et elevation."
        )

    try:
        lat  = cfg.getfloat("observer", "latitude")
        lon  = cfg.getfloat("observer", "longitude")
        elev = cfg.getfloat("observer", "elevation", fallback=0.0)
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        sys.exit(f"[ERREUR] Configuration invalide ({config_file}) : {e}")
    except ValueError as e:
        sys.exit(f"[ERREUR] Valeur numérique invalide dans {config_file} : {e}")

    name = cfg.get("observer", "name", fallback=config_file)
    location = EarthLocation(lat=lat * u.deg, lon=lon * u.deg, height=elev * u.m)
    print(f"[INFO] Observateur : {name}  "
          f"(lat={lat:+.4f}°, lon={lon:+.4f}°, alt={elev:.0f} m)")
    return location


# ---------------------------------------------------------------------------
# Date/heure d'observation
# ---------------------------------------------------------------------------

def parse_datetime(dt_str: str) -> Time:
    """
    Convertit la chaîne de date/heure en objet astropy Time (UTC).

    Formats acceptés :
        "now"                    → heure système courante (UTC)
        "2025-08-15T22:30:00"    → ISO 8601 sans timezone (interprété UTC)
        "2025-08-15T22:30:00Z"   → ISO 8601 explicite UTC
    """
    if dt_str.lower() == "now":
        t = Time(datetime.now(timezone.utc), scale="utc")
        print(f"[INFO] Date/heure : maintenant ({t.iso} UTC)")
        return t

    dt_str_clean = dt_str.rstrip("Zz")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(dt_str_clean, fmt)
            t = Time(dt.replace(tzinfo=timezone.utc), scale="utc")
            print(f"[INFO] Date/heure : {t.iso} UTC")
            return t
        except ValueError:
            continue

    sys.exit(
        f"[ERREUR] Format de date invalide : '{dt_str}'\n"
        f"         Utilisez 'now' ou ISO 8601, ex: '2025-08-15T22:30:00'"
    )


# ---------------------------------------------------------------------------
# Chargement du catalogue
# ---------------------------------------------------------------------------

def load_catalog(csvfile: str) -> pd.DataFrame:
    """
    Charge le base.csv de SpectroStars.

    Le fichier contient les colonnes RA_dec et de_dec (degrés décimaux J2000)
    déjà calculées par l'auteur — on les utilise directement pour éviter tout
    problème de parsing du format sexagésimal européen hétérogène.

    Colonnes utilisées :
        Name, RA_dec, de_dec, V→Vmag, B-V, EB-V→Ebv, Sp→SpType, Sp_s, Miles
    """
    try:
        df = pd.read_csv(csvfile, sep=",", quotechar='"', engine="python",
                         on_bad_lines="skip")
    except FileNotFoundError:
        sys.exit(f"[ERREUR] Catalogue introuvable : {csvfile}")
    except Exception as e:
        sys.exit(f"[ERREUR] Lecture du catalogue : {e}")

    df.columns = [c.strip() for c in df.columns]

    # Vérification des colonnes indispensables
    # Détection du format : base.csv original (RA_dec/de_dec) ou base_merged.csv (RA/Dec)
    if "RA_dec" in df.columns and "de_dec" in df.columns:
        ra_col, dec_col = "RA_dec", "de_dec"
    elif "RA" in df.columns and "Dec" in df.columns:
        ra_col, dec_col = "RA", "Dec"
    else:
        sys.exit(
            f"[ERREUR] Colonnes de coordonnées introuvables dans le catalogue.\n"
            f"         Colonnes trouvées : {list(df.columns)}"
        )

    if "Name" not in df.columns:
        sys.exit(f"[ERREUR] Colonne 'Name' manquante. Colonnes : {list(df.columns)}")

    # Conversion numérique
    df[ra_col]  = pd.to_numeric(df[ra_col],  errors="coerce")
    df[dec_col] = pd.to_numeric(df[dec_col], errors="coerce")
    n_before = len(df)
    df = df.dropna(subset=[ra_col, dec_col]).reset_index(drop=True)
    n_dropped = n_before - len(df)
    if n_dropped:
        print(f"[INFO] {n_dropped} entrée(s) ignorée(s) (coordonnées invalides)")

    # Normalisation : RA et Dec en degrés décimaux
    df["RA"]  = df[ra_col]
    df["Dec"] = df[dec_col]

    # Normalisation des noms de colonnes utiles
    rename = {}
    if "V"    in df.columns and "Vmag"   not in df.columns: rename["V"]    = "Vmag"
    if "Sp"   in df.columns and "SpType" not in df.columns: rename["Sp"]   = "SpType"
    if "EB-V" in df.columns and "Ebv"    not in df.columns: rename["EB-V"] = "Ebv"
    if rename:
        df = df.rename(columns=rename)

    return df


def resolve_by_name(name: str) -> SkyCoord:
    """Résout un nom d'objet via SIMBAD et retourne un SkyCoord ICRS J2000."""
    from astroquery.simbad import Simbad
    print(f"[INFO] Résolution SIMBAD de '{name}'...")
    result = Simbad.query_object(name)
    if result is None:
        sys.exit(f"[ERREUR] Objet '{name}' introuvable dans SIMBAD.")
    # Les versions récentes d'astroquery retournent "ra"/"dec" en minuscules
    cols = {c.lower(): c for c in result.colnames}
    ra_col  = cols.get("ra",  None)
    dec_col = cols.get("dec", None)
    if ra_col is None or dec_col is None:
        sys.exit(f"[ERREUR] Colonnes RA/Dec introuvables dans la réponse SIMBAD.\n"
                 f"         Colonnes disponibles : {result.colnames}")
    # La nouvelle API SIMBAD (TAP, astroquery >= 0.4.6) retourne ra/dec
    # directement en degrés décimaux (float). L'ancienne API renvoyait
    # du sexagésimal en heures pour RA — on détecte le type pour compatibilité.
    ra_val  = result[ra_col][0]
    dec_val = result[dec_col][0]
    try:
        # Nouvelle API : valeurs numériques en degrés décimaux
        ra_val  = float(ra_val)
        dec_val = float(dec_val)
        coord = SkyCoord(ra=ra_val * u.deg, dec=dec_val * u.deg, frame="icrs")
    except (ValueError, TypeError):
        # Ancienne API : chaînes sexagésimales RA en heures, Dec en degrés
        coord = SkyCoord(ra=ra_val, dec=dec_val,
                         unit=(u.hourangle, u.deg), frame="icrs")
    ra_str  = coord.ra.to_string(unit=u.hourangle, sep="hms", precision=1, pad=True)
    dec_str = coord.dec.to_string(unit=u.deg, sep="dms", precision=0, alwayssign=True, pad=True)
    print(f"[INFO] Coordonnées : {ra_str}  {dec_str}")
    return coord


def resolve_by_radec(ra_deg: float, dec_deg: float) -> SkyCoord:
    """Construit un SkyCoord depuis des coordonnées RA/Dec en degrés décimaux."""
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    print(f"[INFO] Cible : RA={coord.ra.deg:.6f}°  Dec={coord.dec.deg:.6f}°")
    return coord


# ---------------------------------------------------------------------------
# Calcul des coordonnées horizontales (Alt/Az)
# ---------------------------------------------------------------------------

def compute_target_altaz(target: SkyCoord,
                         obstime: Time,
                         location: EarthLocation) -> tuple[float, float]:
    """Retourne (altitude_deg, azimut_deg) de la cible à l'instant donné."""
    frame = AltAz(obstime=obstime, location=location)
    altaz = target.transform_to(frame)
    return float(altaz.alt.deg), float(altaz.az.deg)


def compute_altaz(cat_subset: pd.DataFrame,
                  obstime: Time,
                  location: EarthLocation) -> tuple[list[float], list[float]]:
    """
    Calcule l'altitude et l'azimut de chaque étoile du sous-catalogue.

    Convention astropy AltAz :
      - Altitude : 0° = horizon, +90° = zénith
      - Azimut   : 0° = Nord, croissant vers l'Est
    """
    frame = AltAz(obstime=obstime, location=location)
    cat_icrs = SkyCoord(
        ra=cat_subset["RA"].values  * u.deg,
        dec=cat_subset["Dec"].values * u.deg,
        frame="icrs"
    )
    altaz = cat_icrs.transform_to(frame)
    return altaz.alt.deg.tolist(), altaz.az.deg.tolist()


# ---------------------------------------------------------------------------
# Recherche par proximité angulaire + filtre altitude
# ---------------------------------------------------------------------------

def find_nearby(catalog: pd.DataFrame,
                target: SkyCoord,
                radius_deg: float,
                min_alt_deg: float | None,
                max_dalt_deg: float | None,
                obstime: Time | None,
                location: EarthLocation | None,
                sp_types: list | None = None,
                max_results: int | None = None) -> pd.DataFrame:
    """
    Retourne les étoiles dans `radius_deg` autour de `target`,
    filtrées sur l'altitude minimale et/ou la différence d'altitude avec la cible,
    filtrées sur le type spectral si sp_types est fourni (ex: ['A','B']),
    triées par séparation angulaire croissante.
    """
    # Séparations angulaires vectorisées
    cat_coords = SkyCoord(
        ra=catalog["RA"].values  * u.deg,
        dec=catalog["Dec"].values * u.deg,
        frame="icrs"
    )
    separations = target.separation(cat_coords).deg

    result = catalog.copy()
    result["Sep_deg"] = separations

    # Filtre rayon angulaire
    result = result[result["Sep_deg"] <= radius_deg].copy()

    # Filtre type spectral
    if sp_types and "SpType" in result.columns:
        prefixes = tuple(s.upper() for s in sp_types)
        mask = result["SpType"].apply(
            lambda x: isinstance(x, str) and x.strip().upper()[:1] in prefixes
        )
        n_before = len(result)
        result = result[mask].copy()
        n_filtered = n_before - len(result)
        if n_filtered:
            print(f"[INFO] {n_filtered} étoile(s) exclue(s) : type spectral hors {sp_types}")

    # Calcul Alt/Az (si instant et position disponibles)
    if obstime is not None and location is not None:
        # Altitude de la cible elle-même
        target_alt, target_az = compute_target_altaz(target, obstime, location)
        print(f"[INFO] Altitude de la cible : {target_alt:.2f}°  Azimut : {target_az:.2f}°")

        alts, azs = compute_altaz(result, obstime, location)
        result["Alt_deg"]  = alts
        result["Az_deg"]   = azs
        result["DAlt_deg"] = [a - target_alt for a in alts]  # signé : + = plus haut

        # Filtre altitude minimale absolue
        if min_alt_deg is not None:
            n_before = len(result)
            result = result[result["Alt_deg"] >= min_alt_deg].copy()
            n_filtered = n_before - len(result)
            if n_filtered:
                print(f"[INFO] {n_filtered} étoile(s) exclue(s) : altitude < {min_alt_deg}°")

        # Filtre différence d'altitude avec la cible
        if max_dalt_deg is not None:
            n_before = len(result)
            result = result[result["DAlt_deg"].abs() <= max_dalt_deg].copy()
            n_filtered = n_before - len(result)
            if n_filtered:
                print(f"[INFO] {n_filtered} étoile(s) exclue(s) : |ΔAlt| > {max_dalt_deg}°")

    # Tri et limite
    result = result.sort_values("Sep_deg").reset_index(drop=True)
    if max_results is not None:
        result = result.head(max_results)

    return result


# ---------------------------------------------------------------------------
# Affichage des résultats
# ---------------------------------------------------------------------------

def format_ra(deg: float) -> str:
    c = SkyCoord(ra=deg * u.deg, dec=0 * u.deg, frame="icrs")
    return c.ra.to_string(unit=u.hourangle, sep="hms", precision=1, pad=True)


def format_dec(deg: float) -> str:
    c = SkyCoord(ra=0 * u.deg, dec=deg * u.deg, frame="icrs")
    return c.dec.to_string(unit=u.deg, sep=":", precision=0, alwayssign=True, pad=True)


def print_results(results: pd.DataFrame,
                  radius_deg: float,
                  min_alt_deg: float | None,
                  max_dalt_deg: float | None) -> None:
    """Affiche le tableau de résultats formaté."""
    filtres = []
    if min_alt_deg is not None:
        filtres.append(f"altitude ≥ {min_alt_deg}°")
    if max_dalt_deg is not None:
        filtres.append(f"|ΔAlt| ≤ {max_dalt_deg}°")
    filtre_info = (", " + ", ".join(filtres)) if filtres else ""

    if results.empty:
        print(f"\nAucune étoile trouvée (rayon {radius_deg}°{filtre_info}).")
        return

    print(f"\n{len(results)} étoile(s) trouvée(s) "
          f"(rayon {radius_deg}°{filtre_info}) :\n")

    has_altaz  = "Alt_deg"  in results.columns
    has_dalt   = "DAlt_deg" in results.columns
    opt = {col: col in results.columns for col in ["Vmag", "SpType", "B-V", "Ebv", "Miles", "Melchiors"]}

    hdr  = f"{'#':>3}  {'Nom':<15} {'Sep':>5}"
    if has_dalt:
        hdr += f"  {'ΔAlt':>6}"
    hdr += f"  {'Vmag':>5}  {'SpType':<10}  {'Ref':<8}"
    hdr += f"  {'RA':>12}  {'Dec':>12}"
    hdr += f"  {'B-V':>6}  {'Ebv':>6}"
    if has_altaz:
        hdr += f"  {'Alt':>6}  {'Az':>6}"
    print(hdr)
    print("-" * len(hdr))

    for i, row in results.iterrows():
        vmag   = f"{row['Vmag']:.2f}"    if opt["Vmag"]   and pd.notna(row.get("Vmag"))   else "-"
        sptype = str(row["SpType"])[:10] if opt["SpType"] and pd.notna(row.get("SpType")) else "-"
        bv     = f"{row['B-V']:.3f}"    if opt["B-V"]    and pd.notna(row.get("B-V"))    else "-"
        ebv    = f"{row['Ebv']:.3f}"    if opt["Ebv"]    and pd.notna(row.get("Ebv"))    else "-"

        # Miles : non-vide = spectre dans la bibliothèque MILES
        if opt["Miles"]:
            raw = row.get("Miles")
            is_miles = pd.notna(raw) and str(raw).strip() not in ("", "nan")
            miles_flag = "oui" if is_miles else ""
        else:
            miles_flag = ""
        # Melchiors
        if "Melchiors" in results.columns:
            mel_val = row.get("Melchiors", "")
            mel_flag = "oui" if str(mel_val).strip() == "oui" else ""
        else:
            mel_flag = ""

        ra_str  = format_ra(row["RA"])
        dec_str = format_dec(row["Dec"])

        line = f"{i+1:>3}  {str(row['Name']):<15} {row['Sep_deg']:>5.1f}°"
        if has_dalt:
            sign = "+" if row["DAlt_deg"] >= 0 else ""
            line += f"  {sign}{row['DAlt_deg']:>4.1f}°"
        # Colonne Ref : Miles / Melchiors / Les deux / vide
        if is_miles and mel_flag == "oui":
            ref_flag = "M+Mel"
        elif is_miles:
            ref_flag = "Miles"
        elif mel_flag == "oui":
            ref_flag = "Melch"
        else:
            ref_flag = ""
        line += (f"  {vmag:>5}  {sptype:<10}  {ref_flag:<8}"
                 f"  {ra_str:>12}  {dec_str:>12}"
                 f"  {bv:>6}  {ebv:>6}")
        if has_altaz:
            line += f"  {row['Alt_deg']:>5.1f}°  {row['Az_deg']:>5.1f}°"
        print(line)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Sélectionne les étoiles proches d'une cible dans le catalogue SpectroStars.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python star_finder.py --target "Vega"  --radius 10 --datetime now
  python star_finder.py --target "M27"   --radius 10 --datetime "2025-08-15T22:30:00" --max-dalt 5
  python star_finder.py --target "Deneb" --radius 8  --datetime now --min-alt 20 --max-dalt 5
  python star_finder.py --ra 279.23 --dec 38.78 --radius 8 --datetime now --max 10
  python star_finder.py --target "Vega"  --radius 10 --datetime now --config ~/obs.ini
        """
    )

    # --- Cible ---
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--target", "-t", metavar="NOM",
                       help="Nom résolu via SIMBAD (ex: 'Vega', 'M27', 'HD 187811')")
    group.add_argument("--ra", type=float, metavar="DEG",
                       help="RA en degrés décimaux J2000")
    parser.add_argument("--dec", type=float, metavar="DEG",
                        help="Dec en degrés décimaux J2000 (requis avec --ra)")

    # --- Paramètres de recherche ---
    parser.add_argument("--radius", "-r", type=float, default=5.0, metavar="DEG",
                        help="Rayon de recherche en degrés (défaut : 5.0)")
    parser.add_argument("--max", "-n", type=int, default=None, metavar="N",
                        help="Nombre maximum de résultats (défaut : tous)")

    # --- Catalogue ---
    parser.add_argument("--catalog", "-c", default="base.csv", metavar="FICHIER",
                        help="Chemin du fichier base.csv (défaut : ./base.csv)")

    # --- Observateur & temps ---
    parser.add_argument("--config", default="observer.ini", metavar="FICHIER",
                        help="Fichier INI de l'observateur (défaut : observer.ini)")
    parser.add_argument("--datetime", dest="obstime", metavar="DATETIME",
                        help="Date/heure UTC : 'now' ou '2025-08-15T22:30:00'")
    parser.add_argument("--min-alt", dest="min_alt", type=float, default=None,
                        metavar="DEG",
                        help="Altitude minimale en degrés (ex: 20). Requiert --datetime.")
    parser.add_argument("--max-dalt", dest="max_dalt", type=float, default=None,
                        metavar="DEG",
                        help="Différence maximale d'altitude avec la cible, en degrés "
                             "(ex: 5 → garde les étoiles à ±5° de hauteur de la cible). "
                             "Requiert --datetime.")
    parser.add_argument("--sp-type", dest="sp_types", nargs="+", default=None,
                        metavar="LETTRE",
                        help="Filtre sur le type spectral : une ou plusieurs lettres (ex: O B A). "
                             "Seules les étoiles dont le SpType commence par ces lettres sont gardées.")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.ra is not None and args.dec is None:
        sys.exit("[ERREUR] --dec est requis quand --ra est spécifié.")

    if args.min_alt is not None and args.obstime is None:
        sys.exit("[ERREUR] --min-alt requiert --datetime.")

    if args.max_dalt is not None and args.obstime is None:
        sys.exit("[ERREUR] --max-dalt requiert --datetime.")

    # 1. Catalogue
    print(f"[INFO] Chargement du catalogue : {args.catalog}")
    catalog = load_catalog(args.catalog)
    print(f"[INFO] {len(catalog)} étoiles chargées.")

    # 2. Cible
    if args.target:
        target_coord = resolve_by_name(args.target)
    else:
        target_coord = resolve_by_radec(args.ra, args.dec)

    # 3. Observateur & instant (optionnels sans filtre altitude)
    obstime  = None
    location = None
    if args.obstime:
        obstime  = parse_datetime(args.obstime)
        location = load_observer(args.config)

    # 4. Recherche
    print(f"[INFO] Recherche dans un rayon de {args.radius}°"
          + (f", altitude ≥ {args.min_alt}°" if args.min_alt is not None else "")
          + (f", |ΔAlt| ≤ {args.max_dalt}°" if args.max_dalt is not None else "")
          + (f", SpType {args.sp_types}" if args.sp_types else "")
          + "...")
    results = find_nearby(
        catalog, target_coord,
        radius_deg=args.radius,
        min_alt_deg=args.min_alt,
        max_dalt_deg=args.max_dalt,
        obstime=obstime,
        location=location,
        sp_types=args.sp_types,
        max_results=args.max,
    )

    # 5. Affichage
    print_results(results, args.radius, args.min_alt, args.max_dalt)


if __name__ == "__main__":
    main()
