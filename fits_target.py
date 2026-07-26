#!/usr/bin/env python3
"""
fits_target.py — Lecture des entêtes FITS d'acquisition (CCDciel) et calcul
de la trajectoire de la cible (altitude / masse d'air) au fil du temps.

Sert à choisir une étoile de référence à une hauteur — donc une masse d'air —
proche de celle à laquelle la cible a réellement été observée.

Dépendances : astropy, numpy  (matplotlib seulement côté GUI)
"""

from __future__ import annotations

import glob
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.time import Time
from astropy import units as u


# ---------------------------------------------------------------------------
# Mots-clés d'entête (CCDciel écrit des entêtes standards INDI/ASCOM)
# ---------------------------------------------------------------------------

# Instant de début de pose (UTC). CCDciel : DATE-OBS.
KW_DATEOBS = ("DATE-OBS", "DATE_OBS")
KW_EXPTIME = ("EXPTIME", "EXPOSURE")

# Position de la cible. CCDciel : OBJCTRA/OBJCTDEC (sexagésimal),
# parfois RA/DEC (degrés décimaux).
KW_OBJCTRA = ("OBJCTRA", "OBJ-RA")
KW_OBJCTDEC = ("OBJCTDEC", "OBJ-DEC")
KW_RA = ("RA",)
KW_DEC = ("DEC",)
KW_OBJECT = ("OBJECT",)

# Altitude / airmass déjà calculés par la monture (si présents).
KW_ALT = ("OBJCTALT", "ALTITUDE", "ALT")
KW_AZ = ("OBJCTAZ", "AZIMUTH", "AZ")
KW_AIRMASS = ("AIRMASS", "SECZ")

# Site (surclasse éventuellement observer.ini).
KW_SITELAT = ("SITELAT", "LAT-OBS", "OBSGEO-B")
KW_SITELONG = ("SITELONG", "LONG-OBS", "OBSGEO-L")
KW_SITEELEV = ("SITEELEV", "ALT-OBS", "OBSGEO-H")

# Type d'image (CCDciel : IMAGETYP = Light/Flat/Dark/Bias ; parfois FRAME).
# Lu à titre informatif seulement ; aucun filtrage automatique n'est appliqué.
KW_IMAGETYP = ("IMAGETYP", "IMAGETYPE", "FRAME", "FRAMETYP")

FITS_EXTENSIONS = (".fits", ".fit", ".fts",
                   ".FITS", ".FIT", ".FTS")


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass
class Pose:
    """Une pose individuelle lue depuis un fichier FITS."""
    path: str
    filename: str
    t_mid: Time                 # instant milieu de pose (UTC)
    exptime: float | None       # secondes
    alt_deg: float | None = None   # altitude calculée
    az_deg: float | None = None
    airmass: float | None = None
    alt_hdr: float | None = None   # altitude lue dans l'entête (si présente)
    airmass_hdr: float | None = None
    imagetyp: str | None = None    # IMAGETYP brut (Light/Flat/...)
    target_key: str | None = None  # clé d'identification de la cible


@dataclass
class TargetTrajectory:
    """Résultat agrégé de la lecture d'un lot de FITS."""
    poses: list = field(default_factory=list)
    target: SkyCoord | None = None
    object_name: str | None = None
    site: EarthLocation | None = None       # site lu dans les entêtes
    site_from_header: bool = False
    warnings: list = field(default_factory=list)
    synthetic: bool = False            # True = cible saisie (nom/RA-Dec), sans FITS
    obstime: Time | None = None        # instant de référence (mode synthétique)

    # --- agrégats de hauteur --------------------------------------------

    @property
    def n(self) -> int:
        return len(self.poses)

    @property
    def t_start(self) -> Time | None:
        return self.poses[0].t_mid if self.poses else None

    @property
    def t_end(self) -> Time | None:
        return self.poses[-1].t_mid if self.poses else None

    def mean_alt(self) -> float | None:
        vals = [p.alt_deg for p in self.poses if p.alt_deg is not None]
        return float(np.mean(vals)) if vals else None

    def mean_airmass(self) -> float | None:
        vals = [p.airmass for p in self.poses if p.airmass is not None]
        return float(np.mean(vals)) if vals else None

    def alt_range(self) -> tuple[float, float] | None:
        vals = [p.alt_deg for p in self.poses if p.alt_deg is not None]
        return (min(vals), max(vals)) if vals else None


# ---------------------------------------------------------------------------
# Masse d'air (Kasten-Young 1989 : robuste près de l'horizon, sec(z) diverge)
# ---------------------------------------------------------------------------

def airmass_from_alt(alt_deg: float) -> float | None:
    """Masse d'air à partir de l'altitude (degrés). None sous l'horizon."""
    if alt_deg is None or alt_deg <= 0:
        return None
    z = 90.0 - alt_deg                      # distance zénithale
    denom = math.cos(math.radians(z)) + 0.50572 * (96.07995 - z) ** -1.6364
    if denom <= 0:
        return None
    return 1.0 / denom


# ---------------------------------------------------------------------------
# Helpers d'extraction d'entête
# ---------------------------------------------------------------------------

def _get(header, keys):
    for k in keys:
        if k in header:
            v = header[k]
            if v not in (None, ""):
                return v
    return None


def _parse_dateobs(val, exptime):
    """DATE-OBS -> Time UTC au *milieu* de pose (ajoute EXPTIME/2 si dispo)."""
    if val is None:
        return None
    try:
        t0 = Time(str(val), format="isot", scale="utc")
    except Exception:
        try:
            t0 = Time(str(val), scale="utc")
        except Exception:
            return None
    if exptime:
        try:
            t0 = t0 + (float(exptime) / 2.0) * u.s
        except Exception:
            pass
    return t0


def _parse_target(header):
    """Retourne (SkyCoord | None, object_name | None)."""
    obj = _get(header, KW_OBJECT)
    obj = str(obj).strip() if obj is not None else None

    # 1) RA/DEC en degrés décimaux — pleine précision (CCDciel écrit les deux ;
    #    OBJCTRA/OBJCTDEC sont arrondis à la seconde, donc moins précis).
    ra = _get(header, KW_RA)
    dec = _get(header, KW_DEC)
    if ra is not None and dec is not None:
        try:
            c = SkyCoord(ra=float(ra) * u.deg, dec=float(dec) * u.deg,
                         frame="icrs")
            return c, obj
        except (TypeError, ValueError):
            pass

    # 2) OBJCTRA/OBJCTDEC — sexagésimal (RA en heures, Dec en degrés)
    ra = _get(header, KW_OBJCTRA)
    dec = _get(header, KW_OBJCTDEC)
    if ra is not None and dec is not None:
        try:
            c = SkyCoord(ra=str(ra).replace(":", " "),
                         dec=str(dec).replace(":", " "),
                         unit=(u.hourangle, u.deg), frame="icrs")
            return c, obj
        except Exception:
            pass

    return None, obj


def _parse_site(header):
    lat = _get(header, KW_SITELAT)
    lon = _get(header, KW_SITELONG)
    elev = _get(header, KW_SITEELEV)
    if lat is None or lon is None:
        return None

    def _to_deg(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            # format sexagésimal éventuel
            try:
                a = str(v).replace(":", " ").split()
                sign = -1 if a[0].startswith("-") else 1
                nums = [abs(float(x)) for x in a]
                return sign * (nums[0] + nums[1] / 60 + (nums[2] if len(nums) > 2 else 0) / 3600)
            except Exception:
                return None

    lat_d = _to_deg(lat)
    lon_d = _to_deg(lon)
    if lat_d is None or lon_d is None:
        return None
    try:
        elev_m = float(elev) if elev is not None else 0.0
    except (TypeError, ValueError):
        elev_m = 0.0
    try:
        return EarthLocation(lat=lat_d * u.deg, lon=lon_d * u.deg,
                             height=elev_m * u.m)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Lecture d'un lot de fichiers
# ---------------------------------------------------------------------------

def collect_fits_paths(paths_or_dir) -> list:
    """Accepte un dossier, un fichier, ou une liste ; renvoie les .fits triés."""
    from astropy.io import fits  # noqa (garde l'import local)
    out = []
    items = paths_or_dir if isinstance(paths_or_dir, (list, tuple)) else [paths_or_dir]
    for it in items:
        if os.path.isdir(it):
            for ext in FITS_EXTENSIONS:
                out.extend(glob.glob(os.path.join(it, "*" + ext)))
        elif os.path.isfile(it):
            out.append(it)
    # dédoublonnage en préservant l'ordre
    seen, uniq = set(), []
    for p in out:
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def make_synthetic_trajectory(target: SkyCoord,
                              obstime: Time,
                              site: EarthLocation,
                              object_name: str | None = None) -> "TargetTrajectory":
    """
    Construit une trajectoire pour une cible saisie (nom SIMBAD ou RA/Dec),
    sans FITS, autour de l'instant `obstime`. Sert à afficher l'arc de la
    cible dans le graphe même quand aucun fichier n'est chargé.
    """
    traj = TargetTrajectory()
    traj.target = target
    traj.object_name = object_name
    traj.site = site
    traj.synthetic = True
    traj.obstime = obstime
    # une pose unique à l'instant de référence, pour l'altitude ponctuelle
    try:
        alt, az = altaz_at(target, obstime, site)
    except Exception:
        alt, az = None, None
    p = Pose(path="", filename="(cible saisie)", t_mid=obstime,
             exptime=None, alt_deg=alt, az_deg=az,
             airmass=airmass_from_alt(alt) if alt is not None else None)
    traj.poses = [p]
    return traj


def read_trajectory(paths_or_dir,
                    fallback_location: EarthLocation | None = None,
                    resolver=None,
                    prefer_header_site: bool = True) -> TargetTrajectory:
    """
    Lit les entêtes FITS et construit la trajectoire de la cible.

    Paramètres
    ----------
    paths_or_dir : dossier, fichier, ou liste de chemins FITS.
    fallback_location : EarthLocation à utiliser si les entêtes ne portent pas
        de site (typiquement le observer.ini de l'appli).
    resolver : callable(name) -> SkyCoord, pour résoudre OBJECT via SIMBAD
        quand aucune coordonnée n'est présente dans l'entête. Optionnel.
    prefer_header_site : si True et qu'un site figure dans l'entête, il est
        utilisé de préférence au fallback.

    Retour
    ------
    TargetTrajectory (poses triées par instant milieu de pose).
    """
    from astropy.io import fits

    traj = TargetTrajectory()
    files = collect_fits_paths(paths_or_dir)
    if not files:
        traj.warnings.append("Aucun fichier FITS trouvé.")
        return traj

    poses: list[Pose] = []
    header_site: EarthLocation | None = None

    for path in files:
        try:
            with fits.open(path, memmap=False) as hdul:
                header = hdul[0].header
        except Exception as e:
            traj.warnings.append(f"Illisible : {os.path.basename(path)} ({e})")
            continue

        dateobs = _get(header, KW_DATEOBS)
        exptime = _get(header, KW_EXPTIME)
        t_mid = _parse_dateobs(dateobs, exptime)
        if t_mid is None:
            traj.warnings.append(
                f"Pas de DATE-OBS exploitable : {os.path.basename(path)}")
            continue

        # coordonnées / nom propres à CETTE pose (pour info / signalement)
        coord, obj = _parse_target(header)

        # site depuis l'entête (le premier trouvé)
        if header_site is None:
            header_site = _parse_site(header)

        try:
            exp = float(exptime) if exptime is not None else None
        except (TypeError, ValueError):
            exp = None

        p = Pose(
            path=path,
            filename=os.path.basename(path),
            t_mid=t_mid,
            exptime=exp,
            alt_hdr=_to_float(_get(header, KW_ALT)),
            airmass_hdr=_to_float(_get(header, KW_AIRMASS)),
            imagetyp=str(_get(header, KW_IMAGETYP)).strip()
                     if _get(header, KW_IMAGETYP) is not None else None,
            target_key=_target_key(coord, obj),
        )
        p._coord = coord        # type: ignore[attr-defined]
        p._object = obj         # type: ignore[attr-defined]
        poses.append(p)

    if not poses:
        traj.warnings.append(
            "Aucune pose exploitable (DATE-OBS manquant).")
        return traj

    # On utilise TOUS les fichiers pointés par l'utilisateur, tels quels.
    # Aucun filtrage automatique : c'est lui qui choisit. On se contente de
    # signaler, sans rien retirer, si les pointages sont vraiment hétérogènes.
    #
    # Le regroupement se fait par SÉPARATION ANGULAIRE, pas par arrondi de
    # coordonnées : la dérive de suivi d'une même cible (quelques dizaines
    # d'arcsec) ne doit pas être vue comme des cibles différentes. Deux
    # pointages à plus de GROUP_TOL_DEG l'un de l'autre sont considérés
    # distincts.
    GROUP_TOL_DEG = 0.5
    coords = [getattr(p, "_coord", None) for p in poses]
    valid = [c for c in coords if c is not None]
    if len(valid) >= 2:
        ref = valid[0]
        seps = ref.separation(SkyCoord(valid)).deg
        max_sep = float(max(seps))
        if max_sep > GROUP_TOL_DEG:
            traj.warnings.append(
                f"Attention : pointages hétérogènes (écart max "
                f"{max_sep:.2f}°). La sélection semble mélanger plusieurs "
                f"cibles — vérifiez si ce n'est pas voulu.")

    poses.sort(key=lambda p: p.t_mid.jd)

    # cible et nom retenus : premier pointage rencontré (pour préremplir la
    # recherche). N'affecte pas quelles poses sont tracées.
    target = None
    object_name = None
    for p in poses:
        c = getattr(p, "_coord", None)
        if c is not None and target is None:
            target = c
        o = getattr(p, "_object", None)
        if o and object_name is None:
            object_name = o
        if target is not None and object_name is not None:
            break

    # Résolution éventuelle par nom si pas de coordonnées dans l'entête
    if target is None and object_name and resolver is not None:
        try:
            target = resolver(object_name)
        except Exception as e:
            traj.warnings.append(
                f"Résolution SIMBAD de '{object_name}' échouée ({e}).")

    # Choix du site
    site = None
    site_from_header = False
    if header_site is not None and prefer_header_site:
        site, site_from_header = header_site, True
    elif fallback_location is not None:
        site = fallback_location
    elif header_site is not None:
        site, site_from_header = header_site, True

    # Calcul altitude/azimut/airmass pour chaque pose
    if target is not None and site is not None:
        times = Time([p.t_mid for p in poses])
        frame = AltAz(obstime=times, location=site)
        altaz = target.transform_to(frame)
        for p, alt, az in zip(poses, altaz.alt.deg, altaz.az.deg):
            p.alt_deg = float(alt)
            p.az_deg = float(az)
            p.airmass = airmass_from_alt(float(alt))
    else:
        # à défaut, on retombe sur ce que l'entête fournit
        for p in poses:
            if p.alt_hdr is not None:
                p.alt_deg = p.alt_hdr
                p.airmass = p.airmass_hdr or airmass_from_alt(p.alt_hdr)
        if target is None:
            traj.warnings.append(
                "Pas de coordonnées cible (ni entête, ni résolution) : "
                "altitude issue des entêtes si disponible.")
        if site is None:
            traj.warnings.append(
                "Pas de site (ni entête, ni observer.ini) : "
                "impossible de recalculer l'altitude.")

    traj.poses = poses
    traj.target = target
    traj.object_name = object_name
    traj.site = site
    traj.site_from_header = site_from_header
    return traj


def _target_key(coord, object_name):
    """
    Clé pour regrouper les poses d'une même cible.
    Priorité aux coordonnées (arrondi ~0.05°), sinon au nom d'objet.
    """
    if coord is not None:
        return f"{round(coord.ra.deg, 2)}/{round(coord.dec.deg, 2)}"
    if object_name:
        return object_name.strip().lower()
    return None


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Courbe de trajectoire (pour le graphe) : altitude sur la fenêtre + marge
# ---------------------------------------------------------------------------

def altitude_curve(target: SkyCoord,
                   site: EarthLocation,
                   t_start: Time,
                   t_end: Time,
                   margin_min: float = 30.0,
                   n_points: int = 120) -> tuple[list, list]:
    """
    Échantillonne l'altitude de la cible entre t_start et t_end (+ marge),
    pour tracer une courbe lisse. Retourne (datetimes_utc, altitudes_deg).
    """
    span_s = (t_end - t_start).sec + 2 * margin_min * 60.0
    span_s = max(span_s, 600.0)
    t0 = t_start - margin_min * 60.0 * u.s
    dt = np.linspace(0.0, span_s, n_points)
    times = t0 + dt * u.s
    frame = AltAz(obstime=times, location=site)
    altaz = target.transform_to(frame)
    dts = [t.to_datetime(timezone=timezone.utc) for t in times]
    return dts, altaz.alt.deg.tolist()


def altaz_at(target: SkyCoord, t: Time, site: EarthLocation):
    """Altitude, azimut (deg) de la cible à un instant donné."""
    aa = target.transform_to(AltAz(obstime=t, location=site))
    return float(aa.alt.deg), float(aa.az.deg)


def alt_for_airmass(airmass: float) -> float:
    """Altitude (deg) correspondant à une masse d'air (inverse Kasten-Young)."""
    # inversion numérique simple
    lo, hi = 1.0, 90.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        X = airmass_from_alt(mid)
        if X is None:
            lo = mid
            continue
        if X > airmass:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
