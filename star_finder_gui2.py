#!/usr/bin/env python3
"""
star_finder_gui.py — Interface graphique pour SpectroStars Star Finder

Dépendances : astropy, astroquery, pandas  (+ tkinter inclus dans Python)
"""

import sys
import threading
import traceback
import warnings
import webbrowser
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from astropy.coordinates import SkyCoord
from astropy import units as u

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Import du moteur de calcul
# ---------------------------------------------------------------------------
try:
    from star_finder import (
        load_catalog, load_observer, parse_datetime,
        resolve_by_name, find_nearby, format_ra, format_dec,
        compute_target_altaz,
    )
except ImportError as e:
    print(f"Erreur import star_finder : {e}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Resolution RA/Dec sexagesimal
# ---------------------------------------------------------------------------

def resolve_by_sexagesimal(ra_str: str, dec_str: str) -> SkyCoord:
    """
    Convertit des coordonnees sexagesimales en SkyCoord.
    RA  : "10:01:04"  ou  "10 01 04"   (heures)
    Dec : "+40:10:20" ou  "+40 10 20"  (degres, signe obligatoire)
    """
    ra_clean  = ra_str.strip().replace(":", " ")
    dec_clean = dec_str.strip().replace(":", " ")
    try:
        coord = SkyCoord(ra=ra_clean, dec=dec_clean,
                         unit=(u.hourangle, u.deg), frame="icrs")
    except Exception as e:
        raise ValueError(
            f"Coordonnees invalides :\n  RA='{ra_str}'  Dec='{dec_str}'\n{e}")
    return coord


# ---------------------------------------------------------------------------
# Colonnes du tableau
# ---------------------------------------------------------------------------

COLUMNS = [
    ("Nom",      "Name",      150, "center"),
    ("Sep (°)",  "Sep_deg",    70, "e"),
    ("ΔAlt (°)", "DAlt_deg",   110, "e"),
    ("Vmag",     "Vmag",       55, "e"),
    ("SpType",   "SpType",     85, "w"),
    ("Cat",    "Miles",      50, "center"),
    ("RA",       "RA",        110, "w"),
    ("Dec",      "Dec",        95, "w"),
    ("B-V",      "B-V",        55, "e"),
    ("Ebv",      "Ebv",        75, "e"),
    ("Alt (°)",  "Alt_deg",    70, "e"),
    ("Az (°)",   "Az_deg",     70, "e"),
]

PAD = {"padx": 6, "pady": 4}


# ---------------------------------------------------------------------------
# Theme sombre
# ---------------------------------------------------------------------------

BG      = "#1e1e2e"
BG2     = "#2a2a3e"
BG3     = "#313145"
BG4     = "#252535"
FG      = "#cdd6f4"
FG2     = "#a6adc8"
ACCENT  = "#89b4fa"
GREEN   = "#a6e3a1"
ENTRY_BG= "#313145"
SEL_BG  = "#45475a"
SEL_RED = "#e64553"   # surbrillance rouge pour la ligne sélectionnée

FONT_UI   = ("DejaVu Sans", 10)
FONT_BOLD = ("DejaVu Sans", 10, "bold")
FONT_MONO = ("DejaVu Sans Mono", 10)
FONT_SM   = ("DejaVu Sans", 9)


def apply_dark_theme(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".",
        background=BG, foreground=FG,
        fieldbackground=ENTRY_BG, font=FONT_UI,
        bordercolor=BG3, darkcolor=BG2, lightcolor=BG2,
        troughcolor=BG2, selectbackground=SEL_BG,
        selectforeground=FG, insertcolor=FG,
    )
    style.configure("TFrame",      background=BG)
    style.configure("TLabelframe", background=BG2, foreground=ACCENT,
                    bordercolor=BG3)
    style.configure("TLabelframe.Label", background=BG2, foreground=ACCENT,
                    font=FONT_BOLD)
    style.configure("TLabel",     background=BG,  foreground=FG)
    style.configure("Dim.TLabel", background=BG,  foreground=FG2, font=FONT_SM)
    style.configure("TEntry",     fieldbackground=ENTRY_BG, foreground=FG,
                    insertcolor=FG, bordercolor=BG3)
    style.configure("TButton",    background=BG3, foreground=FG,
                    bordercolor=BG3, focuscolor=BG3)
    style.map("TButton",
        background=[("active", SEL_BG), ("pressed", BG2)],
        foreground=[("active", ACCENT)],
    )
    style.configure("Accent.TButton", background=ACCENT, foreground=BG,
                    font=FONT_BOLD)
    style.map("Accent.TButton",
        background=[("active", "#74c7ec"), ("pressed", "#5ab4d9")],
    )
    style.configure("TRadiobutton", background=BG, foreground=FG)
    style.map("TRadiobutton",
        background=[("active", BG)],
        foreground=[("active", ACCENT)],
    )
    style.configure("TScrollbar", background=BG3, troughcolor=BG2,
                    bordercolor=BG2, arrowcolor=FG2)
    style.map("TScrollbar", background=[("active", SEL_BG)])

    style.configure("Treeview",
        background=BG4, foreground=FG,
        fieldbackground=BG4, rowheight=22,
        font=FONT_MONO,
    )
    style.configure("Treeview.Heading",
        background=BG2, foreground=ACCENT,
        font=FONT_BOLD, relief="flat", borderwidth=0,
    )
    style.map("Treeview",
        background=[("selected", SEL_RED)],
        foreground=[("selected", "#ffffff")],
    )
    style.map("Treeview.Heading",
        background=[("active", BG3)],
        foreground=[("active", FG)],
    )
    style.configure("Status.TLabel", background=BG2, foreground=FG2,
                    font=FONT_SM, padding=(6, 3))


# ---------------------------------------------------------------------------
# Fenetre principale
# ---------------------------------------------------------------------------

class StarFinderApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("SpectroStars - Star Finder")
        # (v2 : date/heure préremplies, B+A cochés, menu contextuel SIMBAD)
        self.resizable(True, True)
        self.minsize(950, 640)
        self.configure(bg=BG)

        self._catalog      = None
        self._catalog_path = tk.StringVar(value="base.csv")
        self._config_path  = tk.StringVar(value="observer.ini")
        self._sort_col     = None
        self._sort_reverse = False
        self._results_df   = None
        self._sptype_vars  = {}   # cases a cocher SpType

        apply_dark_theme(self)
        self._build_ui()
        self._try_autoload()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Menu
        menu = tk.Menu(self, bg=BG2, fg=FG, activebackground=SEL_BG,
                       activeforeground=ACCENT, relief="flat", bd=0)
        self.config(menu=menu)
        m_file = tk.Menu(menu, tearoff=0, bg=BG2, fg=FG,
                         activebackground=SEL_BG, activeforeground=ACCENT)
        menu.add_cascade(label="Fichiers", menu=m_file)
        m_file.add_command(label="Choisir le catalogue (base.csv)...",
                           command=self._browse_catalog)
        m_file.add_command(label="Choisir la config observateur...",
                           command=self._browse_config)
        m_file.add_separator()
        m_file.add_command(label="Exporter les resultats CSV...",
                           command=self._export_csv)
        m_file.add_separator()
        m_file.add_command(label="Quitter", command=self.destroy)

        # Panneau superieur
        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        # Cible
        frm_target = ttk.LabelFrame(top, text="Cible", padding=8)
        frm_target.pack(side=tk.LEFT, fill=tk.Y, **PAD)

        self._target_mode = tk.StringVar(value="name")

        ttk.Radiobutton(frm_target, text="Nom SIMBAD",
                        variable=self._target_mode, value="name",
                        command=self._update_target_state).grid(
            row=0, column=0, sticky="w")
        self._name_var   = tk.StringVar()
        self._name_entry = ttk.Entry(frm_target, textvariable=self._name_var,
                                      width=18)
        self._name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=4)
        self._name_entry.bind("<Return>", lambda e: self._run_search())

        ttk.Radiobutton(frm_target, text="RA / Dec",
                        variable=self._target_mode, value="radec",
                        command=self._update_target_state).grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(frm_target, text="RA").grid(
            row=1, column=1, sticky="e", padx=(4, 2), pady=(6, 0))
        self._ra_var   = tk.StringVar()
        self._ra_entry = ttk.Entry(frm_target, textvariable=self._ra_var,
                                    width=12, state="disabled")
        self._ra_entry.grid(row=1, column=2, sticky="ew", pady=(6, 0))

        ttk.Label(frm_target, text="Dec").grid(
            row=2, column=1, sticky="e", padx=(4, 2))
        self._dec_var   = tk.StringVar()
        self._dec_entry = ttk.Entry(frm_target, textvariable=self._dec_var,
                                     width=12, state="disabled")
        self._dec_entry.grid(row=2, column=2, sticky="ew")

        ttk.Label(frm_target, text='ex: "10:01:04"  "+40:10:20"',
                  style="Dim.TLabel").grid(
            row=3, column=1, columnspan=2, sticky="w", padx=4, pady=(2, 0))

        # Date / heure
        frm_time = ttk.LabelFrame(top, text="Date / Heure (UTC)", padding=8)
        frm_time.pack(side=tk.LEFT, fill=tk.Y, **PAD)

        # Ligne Date
        ttk.Label(frm_time, text="Date").grid(row=0, column=0, sticky="w")
        self._date_var  = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self._date_entry = ttk.Entry(frm_time, textvariable=self._date_var, width=12)
        self._date_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Label(frm_time, text="YYYY-MM-DD",
                  style="Dim.TLabel").grid(row=1, column=1, sticky="w", padx=(4,0))

        # Ligne Heure
        ttk.Label(frm_time, text="Heure").grid(row=2, column=0, sticky="w", pady=(6,0))
        self._time_var  = tk.StringVar(value="21:00")
        self._time_entry = ttk.Entry(frm_time, textvariable=self._time_var, width=7)
        self._time_entry.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=(6,0))
        ttk.Label(frm_time, text="HH:MM",
                  style="Dim.TLabel").grid(row=3, column=1, sticky="w", padx=(4,0))

        # Boutons
        ttk.Button(frm_time, text="Maintenant",
                   command=self._set_now).grid(row=4, column=0, columnspan=2,
                                               sticky="ew", pady=(8, 0))
        ttk.Button(frm_time, text="Effacer",
                   command=self._clear_datetime).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # Filtres
        frm_filters = ttk.LabelFrame(top, text="Filtres", padding=8)
        frm_filters.pack(side=tk.LEFT, fill=tk.Y, **PAD)

        def filter_row(parent, row, label, var, default, hint=""):
            ttk.Label(parent, text=label).grid(
                row=row, column=0, sticky="w", pady=2)
            var.set(default)
            ttk.Entry(parent, textvariable=var, width=8).grid(
                row=row, column=1, sticky="ew", padx=6)
            if hint:
                ttk.Label(parent, text=hint, style="Dim.TLabel").grid(
                    row=row, column=2, sticky="w")

        self._radius_var = tk.StringVar()
        self._dalt_var   = tk.StringVar()
        self._minalt_var = tk.StringVar()
        self._maxres_var = tk.StringVar()

        filter_row(frm_filters, 0, "Rayon max (°)",  self._radius_var, "10")
        filter_row(frm_filters, 1, "|ΔAlt| max (°)", self._dalt_var,   "5",
                   "vide = inactif")
        filter_row(frm_filters, 2, "Alt min (°)",    self._minalt_var, "",
                   "vide = inactif")
        filter_row(frm_filters, 3, "Nb max resultats", self._maxres_var, "",
                   "vide = tous")

        # Filtre type spectral : cases a cocher
        ttk.Label(frm_filters, text="Type spectral :",
                  style="Dim.TLabel").grid(row=4, column=0, sticky="w", pady=(6,2))
        sp_frame = ttk.Frame(frm_filters)
        sp_frame.grid(row=4, column=1, columnspan=2, sticky="w", pady=(6,2))
        for col_i, letter in enumerate(["O", "B", "A", "F", "G", "K", "M"]):
            var = tk.BooleanVar(value=(letter in ("B", "A")))
            self._sptype_vars[letter] = var
            cb = tk.Checkbutton(sp_frame, text=letter, variable=var,
                                bg=BG3, fg=FG, selectcolor=BG2,
                                activebackground=BG3, activeforeground=ACCENT,
                                relief="flat", bd=0, padx=2)
            cb.grid(row=0, column=col_i, padx=2)

        # Bouton Rechercher
        frm_action = ttk.Frame(top, padding=8)
        frm_action.pack(side=tk.LEFT, fill=tk.Y, **PAD)

        self._search_btn = ttk.Button(frm_action, text="Rechercher",
                                       style="Accent.TButton",
                                       command=self._run_search)
        self._search_btn.pack(pady=4, ipadx=12, ipady=8)
        ttk.Label(frm_action, text="Catalogue :",
                  style="Dim.TLabel").pack(anchor="w")
        ttk.Label(frm_action, textvariable=self._catalog_path,
                  style="Dim.TLabel", wraplength=170).pack(anchor="w")

        # Tableau
        frm_table = ttk.Frame(self, padding=(8, 0, 8, 4))
        frm_table.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        cols_ids = [c[0] for c in COLUMNS]
        self._tree = ttk.Treeview(frm_table, columns=cols_ids,
                                   show="headings", selectmode="browse")

        for label, _, width, anchor in COLUMNS:
            self._tree.heading(label, text=label,
                                command=lambda l=label: self._sort_by(l))
            self._tree.column(label, width=width, anchor=anchor, stretch=False)

        vsb = ttk.Scrollbar(frm_table, orient="vertical",
                             command=self._tree.yview)
        hsb = ttk.Scrollbar(frm_table, orient="horizontal",
                             command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frm_table.rowconfigure(0, weight=1)
        frm_table.columnconfigure(0, weight=1)

        self._tree.tag_configure("odd",   background=BG4)
        self._tree.tag_configure("even",  background=BG3)
        self._tree.tag_configure("miles",    foreground=GREEN)
        self._tree.tag_configure("melchiors", foreground="#fab387")

        # Menu contextuel (clic droit)
        self._ctx_menu = tk.Menu(self, tearoff=0, bg=BG2, fg=FG,
                                 activebackground=SEL_BG, activeforeground=ACCENT,
                                 relief="flat", bd=0)
        self._ctx_menu.add_command(label="Copier le nom de l'étoile",
                                   command=self._ctx_copy_name)
        self._ctx_menu.add_command(label="Ouvrir la page SIMBAD",
                                   command=self._ctx_open_simbad)
        self._ctx_row_name = None
        # Button-3 = clic droit (Button-2 sur macOS)
        self._tree.bind("<Button-3>", self._show_context_menu)
        self._tree.bind("<Button-2>", self._show_context_menu)

        # Barre de statut
        self._status_var = tk.StringVar(value="Pret.")
        ttk.Label(self, textvariable=self._status_var,
                  style="Status.TLabel").pack(side=tk.BOTTOM, fill=tk.X)

    # ------------------------------------------------------------------
    # Chargement automatique
    # ------------------------------------------------------------------

    def _try_autoload(self):
        path = Path(self._catalog_path.get())
        if path.exists():
            self._load_catalog(str(path))

    def _load_catalog(self, path: str):
        try:
            self._catalog = load_catalog(path)
            self._catalog_path.set(Path(path).name)
            self._status(
                f"Catalogue charge : {len(self._catalog)} etoiles  ({path})")
        except SystemExit as e:
            messagebox.showerror("Erreur catalogue", str(e))

    # ------------------------------------------------------------------
    # Actions UI
    # ------------------------------------------------------------------

    def _browse_catalog(self):
        path = filedialog.askopenfilename(
            title="Choisir le catalogue SpectroStars",
            filetypes=[("CSV", "*.csv"), ("Tous", "*.*")])
        if path:
            self._load_catalog(path)

    def _browse_config(self):
        path = filedialog.askopenfilename(
            title="Choisir la config observateur",
            filetypes=[("INI", "*.ini"), ("Tous", "*.*")])
        if path:
            self._config_path.set(path)
            self._status(f"Config observateur : {path}")

    def _set_now(self):
        now = datetime.now(timezone.utc)
        self._date_var.set(now.strftime("%Y-%m-%d"))
        self._time_var.set(now.strftime("%H:%M"))

    def _clear_datetime(self):
        self._date_var.set("")
        self._time_var.set("")

    def _get_datetime_str(self) -> str:
        """Assemble date + heure en chaine ISO 8601 pour parse_datetime."""
        date_s = self._date_var.get().strip()
        time_s = self._time_var.get().strip()
        if not date_s and not time_s:
            return ""
        if not date_s:
            return ""
        # Heure par défaut 00:00 si non renseignée
        if not time_s:
            time_s = "00:00"
        # Ajouter les secondes si absentes
        if time_s.count(":") == 1:
            time_s += ":00"
        return f"{date_s}T{time_s}"

    def _update_target_state(self):
        mode = self._target_mode.get()
        if mode == "name":
            self._name_entry.config(state="normal")
            self._ra_entry.config(state="disabled")
            self._dec_entry.config(state="disabled")
        else:
            self._name_entry.config(state="disabled")
            self._ra_entry.config(state="normal")
            self._dec_entry.config(state="normal")

    def _status(self, msg: str):
        self._status_var.set(msg)
        self.update_idletasks()

    # ------------------------------------------------------------------
    # Recherche
    # ------------------------------------------------------------------

    def _run_search(self):
        if self._catalog is None:
            messagebox.showwarning("Catalogue manquant",
                "Veuillez d'abord charger le catalogue base.csv\n"
                "(menu Fichiers -> Choisir le catalogue).")
            return

        try:
            radius = float(self._radius_var.get())
        except ValueError:
            messagebox.showerror("Parametre invalide",
                                  "Rayon invalide (nombre attendu).")
            return

        dalt_str   = self._dalt_var.get().strip()
        minalt_str = self._minalt_var.get().strip()
        maxres_str = self._maxres_var.get().strip()
        dt_str     = self._get_datetime_str()

        try:
            max_dalt = float(dalt_str)   if dalt_str   else None
            min_alt  = float(minalt_str) if minalt_str else None
            max_res  = int(maxres_str)   if maxres_str else None
        except ValueError as ex:
            messagebox.showerror("Parametre invalide", str(ex))
            return

        if (max_dalt is not None or min_alt is not None) and not dt_str:
            messagebox.showwarning("Date manquante",
                "Les filtres ΔAlt et Alt min necessitent\n"
                "une date/heure d'observation.")
            return

        # Récupérer les types spectraux cochés
        sp_types = [l for l, v in self._sptype_vars.items() if v.get()] or None

        self._search_btn.config(state="disabled")
        self._status("Recherche en cours...")

        def worker():
            try:
                self._do_search(radius, max_dalt, min_alt, max_res, dt_str, sp_types)
            except Exception:
                msg = traceback.format_exc()
                self.after(0, lambda m=msg: messagebox.showerror("Erreur", m))
            finally:
                self.after(0, lambda: self._search_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _do_search(self, radius, max_dalt, min_alt, max_res, dt_str, sp_types=None):
        mode = self._target_mode.get()
        try:
            if mode == "name":
                name = self._name_var.get().strip()
                if not name:
                    self.after(0, lambda: messagebox.showwarning(
                        "Cible manquante", "Entrez un nom d'objet SIMBAD."))
                    return
                self.after(0, lambda: self._status(
                    f"Resolution SIMBAD de '{name}'..."))
                target = resolve_by_name(name)
            else:
                ra_s  = self._ra_var.get().strip()
                dec_s = self._dec_var.get().strip()
                if not ra_s or not dec_s:
                    self.after(0, lambda: messagebox.showwarning(
                        "Cible manquante", "Entrez RA et Dec."))
                    return
                target = resolve_by_sexagesimal(ra_s, dec_s)
        except SystemExit as e:
            self.after(0, lambda m=str(e): messagebox.showerror(
                "Cible introuvable", m))
            return
        except ValueError as e:
            self.after(0, lambda m=str(e): messagebox.showerror(
                "Coordonnees invalides", m))
            return

        obstime  = None
        location = None
        if dt_str:
            try:
                obstime = parse_datetime(dt_str)
            except SystemExit as e:
                self.after(0, lambda m=str(e): messagebox.showerror(
                    "Date invalide", m))
                return
            try:
                location = load_observer(self._config_path.get())
            except SystemExit as e:
                self.after(0, lambda m=str(e): messagebox.showerror(
                    "Config observateur", m))
                return

        ra_s  = target.ra.to_string(unit=u.hourangle, sep="hms",
                                     precision=1, pad=True)
        dec_s = target.dec.to_string(unit=u.deg, sep="dms",
                                      precision=0, alwayssign=True, pad=True)
        if obstime is not None and location is not None:
            talt, taz = compute_target_altaz(target, obstime, location)
            target_info = (f"Cible : {ra_s}  {dec_s}  |  "
                           f"Alt={talt:.1f}°  Az={taz:.1f}°")
        else:
            target_info = f"Cible : {ra_s}  {dec_s}"

        self.after(0, lambda ti=target_info: self._status(
            f"Calcul... {ti}"))

        results = find_nearby(
            self._catalog, target,
            radius_deg=radius,
            min_alt_deg=min_alt,
            max_dalt_deg=max_dalt,
            obstime=obstime,
            location=location,
            sp_types=sp_types,
            max_results=max_res,
        )

        self._results_df = results
        self.after(0, lambda r=results, ti=target_info:
                   self._display_results(r, ti))

    # ------------------------------------------------------------------
    # Affichage du tableau
    # ------------------------------------------------------------------

    def _display_results(self, df: pd.DataFrame, target_info: str):
        for row in self._tree.get_children():
            self._tree.delete(row)

        if df.empty:
            self._status(f"Aucun resultat.  {target_info}")
            return

        has_altaz = "Alt_deg" in df.columns
        has_dalt  = "DAlt_deg" in df.columns

        for i, row in df.iterrows():
            sep  = f"{row['Sep_deg']:.1f}"
            dalt = ""
            if has_dalt and pd.notna(row.get("DAlt_deg")):
                sign = "+" if row["DAlt_deg"] >= 0 else ""
                dalt = f"{sign}{row['DAlt_deg']:.1f}"

            vmag   = f"{row['Vmag']:.2f}"     if pd.notna(row.get("Vmag"))   else ""
            sptype = str(row.get("SpType","")) if pd.notna(row.get("SpType")) else ""
            bv     = f"{row['B-V']:.3f}"       if pd.notna(row.get("B-V"))    else ""
            if pd.notna(row.get("Ebv")):
                ebv_val = row["Ebv"]
                ebv = f"⚠ {ebv_val:.3f}" if ebv_val > 0.3 else f"{ebv_val:.3f}"
            else:
                ebv = ""

            raw_miles = row.get("Miles", "")
            is_miles  = (pd.notna(raw_miles)
                         and str(raw_miles).strip() not in ("", "nan"))
            raw_mel   = row.get("Melchiors", "")
            is_mel    = str(raw_mel).strip() == "oui"
            if is_miles and is_mel:
                ref_str = "M+Mel"
            elif is_miles:
                ref_str = "Miles"
            elif is_mel:
                ref_str = "Melch"
            else:
                ref_str = ""

            ra_str  = format_ra(row["RA"])
            dec_str = format_dec(row["Dec"])

            alt = (f"{row['Alt_deg']:.1f}"
                   if has_altaz and pd.notna(row.get("Alt_deg")) else "")
            az  = (f"{row['Az_deg']:.1f}"
                   if has_altaz and pd.notna(row.get("Az_deg"))  else "")

            values = (str(row["Name"]).strip(), sep, dalt, vmag,
                      sptype[:12], ref_str, ra_str, dec_str,
                      bv, ebv, alt, az)

            tags = ["even" if i % 2 == 0 else "odd"]
            if is_miles:
                tags.append("miles")
            elif is_mel:
                tags.append("melchiors")

            self._tree.insert("", "end", values=values, tags=tags)

        n = len(df)
        self._status(
            f"{n} etoile{'s' if n > 1 else ''} trouvee{'s' if n > 1 else ''}.  "
            f"{target_info}")

    # ------------------------------------------------------------------
    # Tri des colonnes (fleches ASCII ^ et v)
    # ------------------------------------------------------------------

    def _sort_by(self, col_label: str):
        if self._results_df is None:
            return

        if self._sort_col == col_label:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col     = col_label
            self._sort_reverse = False

        col_map = {c[0]: c[1] for c in COLUMNS}
        key = col_map.get(col_label)
        if key is None:
            return

        df = self._results_df.copy()

        numeric_keys = {"Sep_deg", "DAlt_deg", "Vmag", "B-V", "Ebv",
                        "Alt_deg", "Az_deg", "RA", "Dec"}

        if key in numeric_keys and key in df.columns:
            df = df.sort_values(key, ascending=not self._sort_reverse,
                                na_position="last")
        elif key in df.columns:
            df = df.sort_values(
                key, ascending=not self._sort_reverse,
                key=lambda s: s.str.lower() if s.dtype == object else s,
                na_position="last",
            )

        # Fleches ASCII uniquement (evite tout probleme d'encodage)
        for c_label, _, _, _ in COLUMNS:
            arrow = (" v" if self._sort_reverse else " ^") \
                    if c_label == col_label else ""
            self._tree.heading(c_label, text=c_label + arrow)

        self._results_df = df
        parts = self._status_var.get().split("  ", 1)
        ti = parts[1] if len(parts) > 1 else ""
        self._display_results(df, ti)

    # ------------------------------------------------------------------
    # Menu contextuel (clic droit sur une ligne)
    # ------------------------------------------------------------------

    def _show_context_menu(self, event):
        # Identifier la ligne sous le curseur
        row_id = self._tree.identify_row(event.y)
        if not row_id:
            return
        self._tree.selection_set(row_id)
        values = self._tree.item(row_id, "values")
        if not values:
            return
        # La colonne "Nom" est la premiere du tableau
        self._ctx_row_name = str(values[0]).strip()
        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

    def _ctx_copy_name(self):
        if not self._ctx_row_name:
            return
        self.clipboard_clear()
        self.clipboard_append(self._ctx_row_name)
        self._status(f"Nom copié : {self._ctx_row_name}")

    def _ctx_open_simbad(self):
        if not self._ctx_row_name:
            return
        ident = urllib.parse.quote(self._ctx_row_name)
        url = (f"https://simbad.u-strasbg.fr/simbad/sim-basic?Ident={ident}")
        webbrowser.open(url)
        self._status(f"Ouverture SIMBAD : {self._ctx_row_name}")

    # ------------------------------------------------------------------
    # Export CSV
    # ------------------------------------------------------------------

    def _export_csv(self):
        if self._results_df is None or self._results_df.empty:
            messagebox.showinfo("Export", "Aucun resultat a exporter.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="resultats_star_finder.csv",
        )
        if path:
            self._results_df.to_csv(path, index=False)
            self._status(f"Resultats exportes : {path}")


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------

def main():
    app = StarFinderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
