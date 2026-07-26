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

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
from matplotlib.ticker import MultipleLocator
from matplotlib.patches import Rectangle

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Import du moteur de calcul
# ---------------------------------------------------------------------------
try:
    from star_finder import (
        load_catalog, load_observer, parse_datetime,
        resolve_by_name, find_nearby, format_ra, format_dec,
        compute_target_altaz, find_by_target_height,
    )
except ImportError as e:
    print(f"Erreur import star_finder : {e}")
    sys.exit(1)

try:
    import fits_target as ft
except ImportError as e:
    ft = None
    print(f"[AVERT] Module fits_target indisponible : {e}")


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
    ("Sep (°)",  "Sep_deg",    48, "e"),
    ("Az (°)",   "Az_deg",     55, "e"),
    ("Alt (°)",  "Alt_deg",    60, "e"),
    ("Δh (°)",   "DHvise_deg", 65, "e"),
    ("Airmass",  "Airmass",    65, "e"),
    ("Vmag",     "Vmag",       55, "e"),
    ("SpType",   "SpType",     85, "w"),
    ("Cat",      "Miles",      50, "center"),
    ("RA",       "RA",         95, "w"),
    ("Dec",      "Dec",        95, "w"),
    ("B-V",      "B-V",        55, "e"),
    ("Ebv",      "Ebv",        70, "e"),
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
    style.configure("Status.TLabel", background=BG3, foreground=ACCENT,
                    font=FONT_SM, padding=(8, 5))


# ---------------------------------------------------------------------------
# Fenetre principale
# ---------------------------------------------------------------------------

class StarFinderApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Spectro reference star finder")
        self.resizable(True, True)
        self.minsize(950, 640)
        self.geometry("1200x860")
        self.configure(bg=BG)

        self._catalog      = None
        self._catalog_path = tk.StringVar(value="base.csv")
        self._site_info    = tk.StringVar(value="observer.ini")
        self._config_path  = tk.StringVar(value="observer.ini")
        self._sort_col     = None
        self._sort_reverse = False
        self._results_df   = None
        self._sptype_vars  = {}   # cases a cocher SpType

        # --- Cible depuis FITS -------------------------------------------
        self._trajectory   = None            # TargetTrajectory
        self._fits_target  = None            # cible des FITS (SkyCoord mémorisé)
        self._fits_trajectory = None         # trajectoire FITS mémorisée
        self._fits_mean_alt = None           # h moyen de la cible FITS
        self._h_target     = tk.StringVar()  # hauteur visée (°) éditable
        self._h_mean_lbl   = tk.StringVar(value="—")
        self._fits_info     = tk.StringVar(value="Aucun FITS chargé.")
        self._use_h_target = tk.BooleanVar(value=False)  # piloter la recherche
        self._traj_canvas  = None
        self._traj_ax      = None
        self._traj_hline   = None            # ligne matplotlib h visée
        self._selected_star = None           # étoile sélectionnée (overlay graphe)

        apply_dark_theme(self)
        self._build_ui()
        self._try_autoload()

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------

    def _update_sptype_color(self, letter):
        # Texte lisible : noir/sombre sur bleu quand sélectionné, gris clair
        # sur fond sombre sinon.
        btn = self._sptype_btns.get(letter)
        if btn is None:
            return
        if self._sptype_vars[letter].get():
            btn.config(fg=BG)          # sombre sur bleu (sélectionné)
        else:
            btn.config(fg=FG2)         # gris clair sur fond sombre

    def _build_ui(self):
        # Menu contextuel « Fichier » (plus de bandeau de menu en haut, pour
        # gagner de la hauteur pour les graphes). Ouvert par un bouton.
        self._file_menu = tk.Menu(self, tearoff=0, bg=BG2, fg=FG,
                                  activebackground=SEL_BG,
                                  activeforeground=ACCENT)
        self._file_menu.add_command(label="Choisir le catalogue (base.csv)...",
                                    command=self._browse_catalog)
        self._file_menu.add_command(label="Choisir la config observateur...",
                                    command=self._browse_config)
        self._file_menu.add_separator()
        self._file_menu.add_command(label="Charger des FITS de la cible...",
                                    command=self._browse_fits_files)
        self._file_menu.add_separator()
        self._file_menu.add_command(label="Exporter les resultats CSV...",
                                    command=self._export_csv)
        self._file_menu.add_separator()
        self._file_menu.add_command(label="Quitter", command=self.destroy)

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

        # Mode « cible depuis FITS » : coché automatiquement au chargement de
        # FITS, il indique que la recherche utilise la cible des FITS.
        self._fits_radio = ttk.Radiobutton(
            frm_target, text="Depuis FITS",
            variable=self._target_mode, value="fits",
            command=self._update_target_state, state="disabled")
        self._fits_radio.grid(row=3, column=0, columnspan=3, sticky="w",
                              pady=(6, 0))

        # Cible depuis FITS (trajectoire / masse d'air) — entre Cible et Date
        frm_fits = ttk.LabelFrame(top, text="Cible depuis FITS", padding=8)
        frm_fits.pack(side=tk.LEFT, fill=tk.Y, **PAD)
        # largeur de panneau maîtrisée : les colonnes ne s'étirent pas
        frm_fits.grid_columnconfigure(0, weight=0)
        frm_fits.grid_columnconfigure(1, weight=0)
        frm_fits.grid_columnconfigure(2, weight=0)

        ttk.Button(frm_fits, text="Choisir des FITS...",
                   command=self._browse_fits_files).grid(
            row=0, column=0, columnspan=3, sticky="ew")

        # info sur 3 colonnes, largeur fixe -> ne pousse pas les colonnes
        ttk.Label(frm_fits, textvariable=self._fits_info,
                  style="Dim.TLabel", wraplength=240, justify="left").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(4, 4))

        ttk.Label(frm_fits, text="h moyen :").grid(
            row=2, column=0, sticky="w")
        ttk.Label(frm_fits, textvariable=self._h_mean_lbl,
                  style="Dim.TLabel").grid(row=2, column=1, columnspan=2,
                                            sticky="w")
        ttk.Label(frm_fits,
                  text="h visée : ligne rouge déplaçable sur le graphe",
                  style="Dim.TLabel", wraplength=240, justify="left").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))

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

        # Boutons compacts sur une seule ligne
        btns = ttk.Frame(frm_time)
        btns.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(btns, text="Maintenant", width=11,
                   command=self._set_now).pack(side=tk.LEFT)
        ttk.Button(btns, text="Effacer", width=8,
                   command=self._clear_datetime).pack(side=tk.LEFT, padx=(4, 0))

        # Filtres
        frm_filters = ttk.LabelFrame(top, text="Filtres", padding=8)
        frm_filters.pack(side=tk.LEFT, fill=tk.Y, **PAD)

        def filter_row(parent, row, label, var, default, hint=""):
            ttk.Label(parent, text=label).grid(
                row=row, column=0, sticky="w", pady=2)
            var.set(default)
            ttk.Entry(parent, textvariable=var, width=5).grid(
                row=row, column=1, sticky="w", padx=4)
            if hint:
                ttk.Label(parent, text=hint, style="Dim.TLabel").grid(
                    row=row, column=2, sticky="w")

        self._radius_var = tk.StringVar()
        self._dalt_var   = tk.StringVar()
        self._minalt_var = tk.StringVar()
        self._maxres_var = tk.StringVar()   # conservé en interne (toujours vide)

        filter_row(frm_filters, 0, "Rayon max (°)",  self._radius_var, "30")
        filter_row(frm_filters, 1, "|Δh| max (°)", self._dalt_var,   "10",
                   "vide = inactif")
        filter_row(frm_filters, 2, "Alt min (°)",    self._minalt_var, "",
                   "vide = inactif")

        # Filtre type spectral : petits boutons-bascule (sans case à cocher,
        # donc sans le damier disgracieux), avec « Type : » devant, alignés à
        # gauche sur une seule ligne.
        sp_frame = ttk.Frame(frm_filters)
        sp_frame.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 2))
        ttk.Label(sp_frame, text="Type :",
                  style="Dim.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self._sptype_btns = {}
        for letter in ["O", "B", "A", "F", "G", "K", "M"]:
            var = tk.BooleanVar(value=(letter in ("B", "A")))
            self._sptype_vars[letter] = var
            cb = tk.Checkbutton(
                sp_frame, text=letter, variable=var,
                indicatoron=False, width=2,
                bg=BG3, fg=FG2, selectcolor=ACCENT,
                activebackground=SEL_BG, activeforeground=BG,
                relief="flat", bd=0, padx=1,
                command=lambda l=letter: self._update_sptype_color(l))
            cb.pack(side=tk.LEFT, padx=1)
            self._sptype_btns[letter] = cb
            self._update_sptype_color(letter)   # état initial

        # Bouton Rechercher
        frm_action = ttk.Frame(top, padding=8)
        frm_action.pack(side=tk.LEFT, fill=tk.Y, **PAD)

        self._search_btn = ttk.Button(frm_action, text="Rechercher",
                                       style="Accent.TButton",
                                       command=self._run_search)
        self._search_btn.pack(pady=4, ipadx=12, ipady=8)
        # Bouton Fichier (remplace le bandeau de menu), style standard
        self._file_btn = ttk.Button(frm_action, text="Fichier ▾",
                                     command=self._show_file_menu)
        self._file_btn.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(frm_action, text="Catalogue :",
                  style="Dim.TLabel").pack(anchor="w")
        ttk.Label(frm_action, textvariable=self._catalog_path,
                  style="Dim.TLabel", wraplength=170).pack(anchor="w")
        ttk.Label(frm_action, text="Site :",
                  style="Dim.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(frm_action, textvariable=self._site_info,
                  style="Dim.TLabel", wraplength=170).pack(anchor="w")

        # Graphe de trajectoire — masqué tant qu'aucun FITS n'est chargé.
        # Deux sous-graphes côte à côte : cible (gauche), étoile de
        # référence sélectionnée (droite).
        self._frm_graph = ttk.Frame(self, padding=(8, 0, 8, 4))
        # (packé dynamiquement dans _display_trajectory)
        self._fig = Figure(figsize=(7.2, 3.4), dpi=100)
        self._fig.patch.set_facecolor(BG)
        self._ax_target = self._fig.add_subplot(1, 2, 1)
        self._ax_ref    = self._fig.add_subplot(1, 2, 2)
        self._traj_ax   = self._ax_target   # compat. clic h visée
        self._style_axes(self._ax_target)
        self._style_axes(self._ax_ref)
        self._traj_canvas = FigureCanvasTkAgg(self._fig, master=self._frm_graph)
        self._traj_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        # Ligne h visée déplaçable à la souris sur le graphe de gauche
        self._dragging_hline = False
        self._traj_canvas.mpl_connect("button_press_event",
                                      self._on_graph_press)
        self._traj_canvas.mpl_connect("motion_notify_event",
                                      self._on_graph_motion)
        self._traj_canvas.mpl_connect("button_release_event",
                                      self._on_graph_release)

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
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
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
        self._ctx_menu.add_command(label="Type spectral (Skiff) dans VizieR",
                                   command=self._ctx_query_vizier)
        self._ctx_row_name = None
        # Button-3 = clic droit (Button-2 sur macOS)
        # Sous X11 (Linux), lier au relachement du bouton evite que le menu
        # disparaisse des le relachement. On memorise juste la ligne a l'appui.
        self._tree.bind("<Button-3>", self._on_ctx_press)
        self._tree.bind("<ButtonRelease-3>", self._show_context_menu)
        self._tree.bind("<Button-2>", self._on_ctx_press)
        self._tree.bind("<ButtonRelease-2>", self._show_context_menu)
        self._tree.bind("<<TreeviewSelect>>", self._on_star_select)

        # Barre de statut (tk.Label plutôt que ttk : couleurs fiables sur
        # toutes les plateformes, notamment Windows)
        self._status_var = tk.StringVar(value="Prêt.")
        self._status_bar = tk.Label(self, textvariable=self._status_var,
                                    anchor="w", bg=BG3, fg=ACCENT,
                                    font=("Segoe UI", 10, "bold"),
                                    padx=10, pady=6, height=1)
        self._status_bar.pack(side=tk.BOTTOM, fill=tk.X)

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
        elif mode == "radec":
            self._name_var.set("")          # effacer le nom SIMBAD
            self._name_entry.config(state="disabled")
            self._ra_entry.config(state="normal")
            self._dec_entry.config(state="normal")
        else:  # fits : coordonnées issues des FITS chargés
            self._name_var.set("")          # effacer le nom SIMBAD
            self._name_entry.config(state="disabled")
            # readonly (pas disabled) : les coordonnées FITS restent bien
            # lisibles, sans être modifiables
            self._ra_entry.config(state="readonly")
            self._dec_entry.config(state="readonly")
            # resynchroniser h visée sur le h moyen de la cible FITS
            fma = getattr(self, "_fits_mean_alt", None)
            if fma is not None:
                self._h_target.set(f"{fma:.1f}")

    def _status(self, msg: str):
        self._status_var.set(msg)
        self.update_idletasks()

    # ------------------------------------------------------------------
    # Recherche
    # ------------------------------------------------------------------

    def _run_search(self):
        # En mode FITS, tri par proximité à h visée ; sinon proximité angulaire
        self._use_h_target.set(self._target_mode.get() == "fits")
        self._launch_search()

    def _launch_search(self):
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

        # IMPORTANT : lire TOUTES les valeurs de widgets ici, dans le thread
        # principal. Tkinter interdit l'accès aux widgets depuis un thread
        # secondaire ; le worker ne doit manipuler que des valeurs simples.
        params = {
            "radius": radius,
            "max_dalt": max_dalt,
            "min_alt": min_alt,
            "max_res": max_res,
            "dt_str": dt_str,
            "sp_types": sp_types,
            "mode": self._target_mode.get(),
            "name": self._name_var.get().strip(),
            "ra_s": self._ra_var.get().strip(),
            "dec_s": self._dec_var.get().strip(),
            "config_path": self._config_path.get(),
            "use_h": self._use_h_target.get(),
            "h_target": self._get_h_target(),
        }

        self._search_btn.config(state="disabled")
        self._status("Recherche en cours...")

        def worker():
            try:
                self._do_search(params)
            except Exception:
                msg = traceback.format_exc()
                self.after(0, lambda m=msg: messagebox.showerror("Erreur", m))
            finally:
                self.after(0, lambda: self._search_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _do_search(self, params):
        # Toutes les valeurs de widgets ont été lues dans le thread principal
        # et passées via params (voir _launch_search).
        radius   = params["radius"]
        max_dalt = params["max_dalt"]
        min_alt  = params["min_alt"]
        max_res  = params["max_res"]
        dt_str   = params["dt_str"]
        sp_types = params["sp_types"]
        mode     = params["mode"]

        try:
            if mode == "fits":
                # Cible issue des FITS chargés (mémorisée séparément pour
                # survivre à une éventuelle recherche nom/RA-Dec entre-temps)
                target = getattr(self, "_fits_target", None)
                if target is None:
                    self.after(0, lambda: messagebox.showwarning(
                        "Cible FITS manquante",
                        "Chargez d'abord des FITS avec une cible identifiable."))
                    return
                # restaurer la trajectoire FITS pour le graphe
                if getattr(self, "_fits_trajectory", None) is not None:
                    self._trajectory = self._fits_trajectory
            elif mode == "name":
                name = params["name"]
                if not name:
                    self.after(0, lambda: messagebox.showwarning(
                        "Cible manquante", "Entrez un nom d'objet SIMBAD."))
                    return
                self.after(0, lambda: self._status(
                    f"Resolution SIMBAD de '{name}'..."))
                target = resolve_by_name(name)
            else:
                ra_s  = params["ra_s"]
                dec_s = params["dec_s"]
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

        # Remplir les champs RA/Dec avec les coordonnées résolues (mode nom
        # SIMBAD ou FITS), pour information et bascule éventuelle.
        if mode in ("name", "fits"):
            ra_fill  = target.ra.to_string(unit=u.hourangle, sep=":",
                                           precision=1, pad=True)
            dec_fill = target.dec.to_string(unit=u.deg, sep=":",
                                            precision=0, alwayssign=True,
                                            pad=True)
            self.after(0, lambda r=ra_fill, d=dec_fill: (
                self._ra_var.set(r), self._dec_var.set(d)))

        # Provenance du site : en mode FITS, celui de la trajectoire FITS ;
        # sinon (nom/RA-Dec) c'est observer.ini.
        if mode == "fits":
            traj = getattr(self, "_fits_trajectory", None)
            src = ("entête FITS" if (traj is not None and
                                     getattr(traj, "site_from_header", False))
                   else "observer.ini")
            self.after(0, lambda s=src: self._site_info.set(s))
        else:
            self.after(0, lambda: self._site_info.set("observer.ini"))

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
                location = load_observer(params["config_path"])
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

        use_h = params["use_h"]
        h_target = params["h_target"]

        if use_h and h_target is not None:
            if obstime is None or location is None:
                self.after(0, lambda: messagebox.showwarning(
                    "Date/site manquants",
                    "La recherche à hauteur visée nécessite une date/heure\n"
                    "et une position observateur."))
                return
            results = find_by_target_height(
                self._catalog, target,
                obstime=obstime,
                location=location,
                h_target_deg=h_target,
                radius_deg=radius,
                max_dh_deg=None,
                min_alt_deg=min_alt,
                sp_types=sp_types,
                max_results=None,          # on plafonne après le filtre Δh
            )
            target_info += f"  |  h visée={h_target:.1f}°"
        else:
            results = find_nearby(
                self._catalog, target,
                radius_deg=radius,
                min_alt_deg=min_alt,
                max_dalt_deg=None,         # filtre Δh appliqué plus bas
                obstime=obstime,
                location=location,
                sp_types=sp_types,
                max_results=None,
            )

        # Colonne masse d'air (dérivée de l'altitude) pour affichage/tri
        if "Alt_deg" in results.columns and ft is not None:
            results = results.copy()
            results["Airmass"] = results["Alt_deg"].apply(
                lambda a: ft.airmass_from_alt(a) if pd.notna(a) else None)

        # h visée par défaut selon le mode (position avant déplacement) :
        #  - FITS : h moyen de la cible (déjà dans le champ h visée)
        #  - nom/RA-Dec : altitude de la cible à l'heure choisie
        h_now = params["h_target"]
        if mode in ("name", "radec") and obstime is not None and location is not None:
            try:
                talt, _ = compute_target_altaz(target, obstime, location)
                h_now = round(float(talt), 1)
                self.after(0, lambda v=h_now: self._h_target.set(f"{v:.1f}"))
            except Exception:
                pass

        # Δh piloté par h visée dans TOUS les modes : Δh = alt_étoile - h_visée
        if h_now is not None and "Alt_deg" in results.columns:
            results = results.copy()
            results["DHvise_deg"] = results["Alt_deg"] - h_now
            # Filtre |Δh| max appliqué ICI, sur la même quantité que la colonne
            # affichée (donc toujours cohérent, y compris après déplacement).
            if max_dalt is not None:
                results = results[
                    results["DHvise_deg"].abs() <= max_dalt].copy()
            # Tri par défaut : proximité à h visée (|Δh| croissant), tous modes
            results = results.reindex(
                results["DHvise_deg"].abs().sort_values(
                    kind="mergesort").index)
            self._sort_col = "Δh (°)"
            self._sort_reverse = False
        # plafond du nombre de résultats après filtrage
        if max_res is not None:
            results = results.head(max_res)

        self._results_df = results

        # Le graphe de la cible doit refléter la cible qui vient d'être
        # recherchée par nom/RA-Dec : une recherche explicite prime sur une
        # trajectoire FITS chargée auparavant. Exceptions (on garde la
        # trajectoire FITS) : mode « Depuis FITS », ou recherche à hauteur
        # visée (bouton du panneau FITS) — les deux relèvent du flux FITS.
        fits_loaded = (self._trajectory is not None and
                       not getattr(self._trajectory, "synthetic", False))
        keep_fits = (mode == "fits" or use_h) and fits_loaded
        if not keep_fits and obstime is not None and location is not None:
            syn = ft.make_synthetic_trajectory(
                target, obstime, location,
                object_name=(params["name"] if mode == "name" else None))
            self._trajectory = syn
            self._selected_star = None
            self.after(0, self._display_trajectory)
        elif keep_fits:
            # on conserve la trajectoire FITS : rafraîchir le graphe au cas où
            # il affichait une cible synthétique auparavant
            self._selected_star = None
            self.after(0, self._display_trajectory)

        self.after(0, lambda r=results, ti=target_info:
                   self._display_results(r, ti))

    # ------------------------------------------------------------------
    # Affichage du tableau
    # ------------------------------------------------------------------

    def _display_results(self, df: pd.DataFrame, target_info: str):
        # nouvelle liste : on retire l'éventuelle trajectoire d'étoile
        # sélectionnée précédemment
        if self._selected_star is not None:
            self._selected_star = None
            if self._trajectory is not None:
                self._display_trajectory()

        for row in self._tree.get_children():
            self._tree.delete(row)

        if df.empty:
            self._status(f"Aucun resultat.  {target_info}")
            return

        has_altaz = "Alt_deg" in df.columns
        has_dalt  = "DAlt_deg" in df.columns
        has_dhv   = "DHvise_deg" in df.columns

        for i, row in df.iterrows():
            sep  = f"{row['Sep_deg']:.1f}"

            # Colonne Δh unique :
            #  - mode FITS recherche par hauteur : écart à h visée (DHvise_deg)
            #  - sinon : écart d'altitude étoile - cible (DAlt_deg)
            dh = ""
            if has_dhv and pd.notna(row.get("DHvise_deg")):
                val = row["DHvise_deg"]
                dh = f"{'+' if val >= 0 else ''}{val:.1f}"
            elif has_dalt and pd.notna(row.get("DAlt_deg")):
                val = row["DAlt_deg"]
                dh = f"{'+' if val >= 0 else ''}{val:.1f}"

            # Altitude, azimut (sans fraction), masse d'air
            alt = az = airmass = ""
            if has_altaz and pd.notna(row.get("Alt_deg")):
                alt = f"{row['Alt_deg']:.1f}"
            if pd.notna(row.get("Airmass")):
                airmass = f"{row['Airmass']:.2f}"
            if has_altaz and pd.notna(row.get("Az_deg")):
                az = f"{row['Az_deg']:.0f}"

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

            # RA sans fraction de seconde, Dec en degrés
            ra_str = SkyCoord(ra=row["RA"] * u.deg, dec=0 * u.deg).ra.to_string(
                unit=u.hourangle, sep="hms", precision=0, pad=True)
            dec_str = format_dec(row["Dec"])

            # Ordre : Nom, Sep, Az, Alt, Δh, Airmass, Vmag, SpType, Cat,
            #         RA, Dec, B-V, Ebv
            values = (str(row["Name"]).strip(), sep, az, alt, dh, airmass,
                      vmag, sptype[:12], ref_str, ra_str, dec_str, bv, ebv)

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

    def _sort_by(self, col_label: str, keep_dir: bool = False):
        if self._results_df is None:
            return

        if keep_dir:
            self._sort_col = col_label
        elif self._sort_col == col_label:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col     = col_label
            self._sort_reverse = False

        col_map = {c[0]: c[1] for c in COLUMNS}
        key = col_map.get(col_label)
        if key is None:
            return

        df = self._results_df.copy()

        numeric_keys = {"Sep_deg", "DAlt_deg", "DHvise_deg", "Airmass",
                        "Vmag", "B-V", "Ebv", "Alt_deg", "Az_deg", "RA", "Dec"}

        if key in numeric_keys and key in df.columns:
            df = df.sort_values(key, ascending=not self._sort_reverse,
                                na_position="last")
        elif key in df.columns:
            df = df.sort_values(
                key, ascending=not self._sort_reverse,
                key=lambda s: s.str.lower() if s.dtype == object else s,
                na_position="last",
            )

        # Pas de flèche dans les en-têtes (rendu inégal selon les polices) ;
        # le tri reste actif dans un sens puis l'autre à chaque clic.
        self._results_df = df
        parts = self._status_var.get().split("  ", 1)
        ti = parts[1] if len(parts) > 1 else ""
        self._display_results(df, ti)

    # ------------------------------------------------------------------
    # Menu contextuel (clic droit sur une ligne)
    # ------------------------------------------------------------------

    def _show_file_menu(self):
        # Ouvre le menu Fichier juste sous le bouton
        b = self._file_btn
        x = b.winfo_rootx()
        y = b.winfo_rooty() + b.winfo_height()
        try:
            self._file_menu.tk_popup(x, y)
        finally:
            self._file_menu.grab_release()

    def _on_ctx_press(self, event):
        # A l'appui : selectionner la ligne sous le curseur et memoriser le nom.
        row_id = self._tree.identify_row(event.y)
        if not row_id:
            self._ctx_row_name = None
            return
        self._tree.selection_set(row_id)
        values = self._tree.item(row_id, "values")
        # La colonne "Nom" est la premiere du tableau
        self._ctx_row_name = str(values[0]).strip() if values else None

    def _show_context_menu(self, event):
        # Au relachement : afficher le menu. Sous X11, ne PAS appeler
        # grab_release() immediatement, sinon le menu se ferme aussitot.
        if not getattr(self, "_ctx_row_name", None):
            return
        self._ctx_menu.tk_popup(event.x_root, event.y_root)

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

    def _ctx_query_vizier(self):
        # Lance directement une requete VizieR sur l'etoile selectionnee dans
        # le catalogue Skiff « Catalogue of Stellar Spectral Classifications »
        # (B/mk/mktypes). Le nom est resolu en coordonnees par Sesame (-c).
        if not self._ctx_row_name:
            return
        target = urllib.parse.quote(self._ctx_row_name)
        url = (
            "https://vizier.cds.unistra.fr/viz-bin/VizieR-3"
            "?-source=B/mk/mktypes"
            f"&-c={target}"
            "&-c.rs=5"
            "&-out.max=50"
            "&-out.form=HTML+Table"
            "&-out.add=_r"
            "&-out.add=_RAJ,_DEJ"
            "&-sort=_r"
            "&-oc.form=sexa"
        )
        webbrowser.open(url)
        self._status(f"Requête VizieR (Skiff) : {self._ctx_row_name}")

    # ------------------------------------------------------------------
    # Cible depuis FITS : chargement, trajectoire, graphe
    # ------------------------------------------------------------------

    def _style_axes(self, ax):
        ax.set_facecolor(BG4)
        for spine in ax.spines.values():
            spine.set_color(BG3)
        ax.tick_params(colors=FG2, labelsize=8)
        ax.xaxis.label.set_color(FG2)
        ax.yaxis.label.set_color(FG2)
        # Grille lisible : lignes d'altitude tous les 5°
        ax.yaxis.set_major_locator(MultipleLocator(5))
        ax.grid(True, which="major", color=FG2, linewidth=0.6, alpha=0.35)

    def _browse_fits_files(self):
        if ft is None:
            messagebox.showerror(
                "Module manquant",
                "Le module fits_target n'est pas disponible.")
            return
        paths = filedialog.askopenfilenames(
            title="Fichiers FITS d'acquisition de la cible",
            filetypes=[("FITS", "*.fits *.fit *.fts"), ("Tous", "*.*")])
        if paths:
            self._load_fits(list(paths))

    def _load_fits(self, paths_or_dir):
        self._status("Lecture des entêtes FITS...")
        config_path = self._config_path.get()   # lu dans le thread principal

        def worker():
            try:
                location = None
                try:
                    location = load_observer(config_path)
                except SystemExit:
                    location = None
                traj = ft.read_trajectory(
                    paths_or_dir,
                    fallback_location=location,
                    resolver=resolve_by_name,
                    prefer_header_site=True,
                )
            except Exception:
                msg = traceback.format_exc()
                self.after(0, lambda m=msg: messagebox.showerror(
                    "Erreur lecture FITS", m))
                return
            self.after(0, lambda t=traj: self._on_trajectory_loaded(t))

        threading.Thread(target=worker, daemon=True).start()

    def _on_trajectory_loaded(self, traj):
        self._trajectory = traj
        if traj.n == 0:
            self._fits_info.set("Aucune pose exploitable.")
            self._h_mean_lbl.set("—")
            msg = "\n".join(traj.warnings) or "Aucune pose exploitable."
            messagebox.showwarning("FITS", msg)
            return

        name = traj.object_name or "cible"
        span_start = traj.t_start.to_datetime().strftime("%H:%M")
        span_end   = traj.t_end.to_datetime().strftime("%H:%M")
        self._fits_info.set(
            f"{traj.n} poses · {name} · {span_start}–{span_end} UTC")

        # Provenance du site utilisé pour les calculs
        self._site_info.set("entête FITS" if traj.site_from_header
                            else "observer.ini")

        mean_alt = traj.mean_alt()
        mean_X   = traj.mean_airmass()
        if mean_alt is not None:
            xlbl = f"  (X≈{mean_X:.2f})" if mean_X else ""
            self._h_mean_lbl.set(f"{mean_alt:.1f}°{xlbl}")
            # h visée = h moyen de la cible FITS (mémorisé pour resynchro)
            self._fits_mean_alt = mean_alt
            self._h_target.set(f"{mean_alt:.1f}")
        else:
            self._h_mean_lbl.set("—")
            self._fits_mean_alt = None

        # Cible depuis FITS : activer et sélectionner le mode « Depuis FITS »,
        # et remplir aussi RA/Dec (à titre indicatif / bascule manuelle).
        if traj.target is not None and not getattr(traj, "synthetic", False):
            ra_s  = traj.target.ra.to_string(unit=u.hourangle, sep=":",
                                              precision=1, pad=True)
            dec_s = traj.target.dec.to_string(unit=u.deg, sep=":",
                                               precision=0, alwayssign=True,
                                               pad=True)
            self._fits_target = traj.target          # cible FITS mémorisée
            self._fits_trajectory = traj             # trajectoire FITS mémorisée
            self._fits_radio.config(state="normal")
            # remplir RA/Dec pendant que les champs sont actifs, puis passer
            # en mode FITS (sinon l'affichage des Entry désactivés ne se
            # rafraîchit pas toujours)
            self._ra_entry.config(state="normal")
            self._dec_entry.config(state="normal")
            self._ra_var.set(ra_s)
            self._dec_var.set(dec_s)
            self._ra_entry.update_idletasks()
            self._dec_entry.update_idletasks()
            self._target_mode.set("fits")
            self._update_target_state()

        # Date/heure alignées sur les FITS (utile pour réanalyser d'anciennes
        # données) : date = jour d'observation, heure = dernière pose.
        if traj.t_end is not None:
            last = traj.t_end.to_datetime()
            self._date_var.set(last.strftime("%Y-%m-%d"))
            self._time_var.set(last.strftime("%H:%M"))

        if traj.warnings:
            self._status(f"FITS chargés : {traj.n} poses "
                         "(voir avertissements).")
            # Signaler sans rien retirer (sélection hétérogène, DATE-OBS
            # manquant sur certains fichiers, etc.).
            messagebox.showinfo(
                "FITS chargés",
                f"{traj.n} pose(s) utilisée(s).\n\n"
                + "\n".join(f"• {w}" for w in traj.warnings))
        else:
            self._status(f"FITS chargés : {traj.n} poses, {name}.")

        self._display_trajectory()

    def _autoscale(self, ax, all_times, all_alts, force_ylim=None):
        """Échelle Y resserrée + X sur l'étendue tracée, pour un axe donné.

        Si force_ylim=(lo,hi) est fourni, cette échelle Y est imposée (sert
        à partager la même échelle d'altitude entre les deux panneaux).
        Retourne le (lo, hi) appliqué en Y.
        """
        if force_ylim is not None:
            lo, hi = force_ylim
            ax.set_ylim(lo, hi)
        elif all_alts:
            amin, amax = min(all_alts), max(all_alts)
            pad = max(2.0, (amax - amin) * 0.12)
            lo = max(0.0, amin - pad)
            hi = min(90.0, amax + pad)
            if hi - lo < 5:
                mid = 0.5 * (lo + hi)
                lo, hi = max(0.0, mid - 2.5), min(90.0, mid + 2.5)
            ax.set_ylim(lo, hi)
        else:
            lo, hi = 0, 90
            ax.set_ylim(lo, hi)
        if all_times:
            tmin, tmax = min(all_times), max(all_times)
            span = tmax - tmin
            if span.total_seconds() > 0:
                margin = span * 0.05
                ax.set_xlim(tmin - margin, tmax + margin)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        return ax.get_ylim()

    def _display_trajectory(self):
        traj = self._trajectory
        if traj is None or traj.n == 0:
            return

        # afficher la zone graphe si nécessaire
        if not self._frm_graph.winfo_ismapped():
            self._frm_graph.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True,
                                 before=self._status_label())

        # Fenêtre du panneau CIBLE (gauche) — 1h30 de large (±45 min).
        # Et instant de référence t_ref pour les repères du panneau de droite.
        if getattr(traj, "synthetic", False):
            # Cible saisie (nom/RA-Dec) : centrée sur l'heure spécifiée.
            t_ref = traj.obstime if traj.obstime is not None else traj.t_start
            t_center = t_ref
        else:
            # Cible issue de FITS : graphe centré sur la pose médiane ;
            # la référence temporelle pour l'étoile de comparaison est la fin
            # de la dernière pose (moment où on enchaînerait dessus).
            mid_idx = len(traj.poses) // 2
            t_center = traj.poses[mid_idx].t_mid
            t_ref = traj.t_end
        t0 = t_center - 45 * 60 * u.s
        t1 = t_center + 45 * 60 * u.s
        # Fenêtre du panneau RÉFÉRENCE (droite), centrée sur t_ref (1h30)
        tR0 = t_ref - 45 * 60 * u.s
        tR1 = t_ref + 45 * 60 * u.s

        # =============================================================
        #  Panneau GAUCHE : trajectoire de la cible
        # =============================================================
        axL = self._ax_target
        axL.clear()
        self._style_axes(axL)

        pose_times = [p.t_mid.to_datetime(timezone=timezone.utc)
                      for p in traj.poses]
        pose_alts  = [p.alt_deg for p in traj.poses]
        L_times = list(pose_times)
        L_alts  = [a for a in pose_alts if a is not None]

        if traj.target is not None and traj.site is not None:
            try:
                dts, alts = ft.altitude_curve(traj.target, traj.site,
                                              t0, t1, margin_min=0.0,
                                              n_points=150)
                axL.plot(dts, alts, color=ACCENT, linewidth=1.5)
                L_times += dts
                L_alts  += list(alts)
            except Exception:
                pass

        synthetic = getattr(traj, "synthetic", False)
        mean_alt = None if synthetic else traj.mean_alt()
        target_alt_ref = None   # altitude de la cible à l'heure choisie (synth.)

        if synthetic:
            # marquer l'instant de référence (heure du panneau Date/Heure)
            p0 = traj.poses[0] if traj.poses else None
            if p0 is not None and p0.alt_deg is not None:
                ts = p0.t_mid.to_datetime(timezone=timezone.utc)
                Xt = ft.airmass_from_alt(p0.alt_deg)
                target_alt_ref = p0.alt_deg
                axL.scatter([ts], [p0.alt_deg], s=45, marker="o",
                            color=GREEN, zorder=5)
                # ligne horizontale à l'altitude de la cible à l'heure choisie
                axL.axhline(p0.alt_deg, color=GREEN, linewidth=1.0,
                            linestyle="-", alpha=0.7,
                            label=f"cible à l'heure choisie : {p0.alt_deg:.1f}°"
                                  + (f"  X={Xt:.2f}" if Xt else ""))
                L_alts.append(p0.alt_deg)
        else:
            # Boîtes de durée de pose : largeur = temps d'exposition,
            # hauteur = plage d'altitude balayée pendant la pose.
            X_mean = traj.mean_airmass()
            drawn_box = False
            for p in traj.poses:
                exp = p.exptime or 0.0
                if exp <= 0 or traj.target is None or traj.site is None:
                    continue
                tb = p.t_mid - (exp / 2.0) * u.s
                te = p.t_mid + (exp / 2.0) * u.s
                try:
                    ab, _ = ft.altaz_at(traj.target, tb, traj.site)
                    ae, _ = ft.altaz_at(traj.target, te, traj.site)
                except Exception:
                    continue
                x0 = mdates.date2num(tb.to_datetime(timezone=timezone.utc))
                x1 = mdates.date2num(te.to_datetime(timezone=timezone.utc))
                y0, y1 = min(ab, ae), max(ab, ae)
                # hauteur minimale visuelle pour les poses très courtes
                if y1 - y0 < 0.05:
                    y0 -= 0.05
                    y1 += 0.05
                lbl = None
                if not drawn_box:
                    lbl = "poses" + (f" (X moyen={X_mean:.2f})" if X_mean else "")
                    drawn_box = True
                axL.add_patch(Rectangle(
                    (x0, y0), x1 - x0, y1 - y0,
                    facecolor=GREEN, alpha=0.30,
                    edgecolor=GREEN, linewidth=1.1, zorder=4, label=lbl))
                L_alts.extend([y0, y1])
            # repli : si aucune boîte (pas d'exptime), points simples
            if not drawn_box and any(a is not None for a in pose_alts):
                axL.scatter(pose_times, pose_alts, s=20, color=GREEN, zorder=5,
                            label="poses"
                                  + (f" (X moyen={X_mean:.2f})" if X_mean else ""))
            if mean_alt is not None:
                X_ma = ft.airmass_from_alt(mean_alt)
                axL.axhline(mean_alt, color=FG2, linewidth=0.8, linestyle=":",
                            label=f"h moyen {mean_alt:.1f}°"
                                  + (f"  X={X_ma:.2f}" if X_ma else ""))
                L_alts.append(mean_alt)

        # h visée : affichée dans TOUS les modes, déplaçable à la souris.
        h_vise = self._get_h_target()
        if h_vise is not None:
            X_hv = ft.airmass_from_alt(h_vise) if ft else None
            self._traj_hline = axL.axhline(
                h_vise, color=SEL_RED, linewidth=1.4, linestyle="--",
                label=f"h visée {h_vise:.1f}°"
                      + (f"  X={X_hv:.2f}" if X_hv else ""))
            L_alts.append(h_vise)

        name = traj.object_name or "cible"
        axL.set_title(f"Cible : {name}", color=FG, fontsize=8)
        axL.set_ylabel("Altitude (°)")
        self._target_ylim = self._autoscale(axL, L_times, L_alts)
        legL = axL.legend(loc="best", fontsize=7, framealpha=0.2)
        if legL:
            for txt in legL.get_texts():
                txt.set_color(FG)

        # =============================================================
        #  Panneau DROITE : trajectoire de l'étoile de référence choisie
        # =============================================================
        axR = self._ax_ref
        axR.clear()
        self._style_axes(axR)

        sel = getattr(self, "_selected_star", None)
        if sel is not None and traj.site is not None:
            R_times, R_alts = [], []
            try:
                dts_s, alts_s = ft.altitude_curve(sel["coord"], traj.site,
                                                  tR0, tR1, margin_min=0.0,
                                                  n_points=160)
                axR.plot(dts_s, alts_s, color="#fab387", linewidth=1.5)
                R_times += dts_s
                R_alts  += list(alts_s)
            except Exception:
                pass

            # Repères horaires à partir de l'instant de référence :
            # +0, +15, +30 min, chacun annoté avec sa masse d'air.
            marker_colors = ["#a6e3a1", "#94e2d5", "#fab387", "#f38ba8"]
            for k, dm in enumerate((0, 10, 20, 30)):
                tk_ = t_ref + dm * 60 * u.s
                try:
                    alt_k, _ = ft.altaz_at(sel["coord"], tk_, traj.site)
                except Exception:
                    continue
                if alt_k is None:
                    continue
                ts_k = tk_.to_datetime(timezone=timezone.utc)
                X_k = ft.airmass_from_alt(alt_k)
                axR.scatter([ts_k], [alt_k], s=55, marker="o",
                            color=marker_colors[k], zorder=6,
                            edgecolors=BG, linewidths=0.6,
                            label=f"+{dm:>2d} min : {alt_k:.1f}°"
                                  + (f"  X={X_k:.2f}" if X_k else ""))
                R_times.append(ts_k)
                R_alts.append(alt_k)

            # Ligne h visée (rouge) : référence qui pilote Δh, dans tous les
            # modes. En mode saisi, on garde aussi la ligne verte « cible ».
            if synthetic and target_alt_ref is not None:
                Xr = ft.airmass_from_alt(target_alt_ref)
                axR.axhline(target_alt_ref, color=GREEN, linewidth=1.0,
                            linestyle="-", alpha=0.5,
                            label=f"cible : {target_alt_ref:.1f}°"
                                  + (f"  X={Xr:.2f}" if Xr else ""))
                R_alts.append(target_alt_ref)
            if h_vise is not None:
                axR.axhline(h_vise, color=SEL_RED, linewidth=1.4,
                            linestyle="--")   # ligne sans légende
                R_alts.append(h_vise)

            axR.set_title(f"Réf. : {sel['name']}", color=FG, fontsize=8)
            # échelle X propre au panneau droit, échelle Y = union des deux
            ref_ylim = self._autoscale(axR, R_times, R_alts)
            tgt_ylim = getattr(self, "_target_ylim", ref_ylim)
            shared = (min(tgt_ylim[0], ref_ylim[0]),
                      max(tgt_ylim[1], ref_ylim[1]))
            axL.set_ylim(shared)
            axR.set_ylim(shared)
            legR = axR.legend(loc="best", fontsize=7, framealpha=0.2)
            if legR:
                for txt in legR.get_texts():
                    txt.set_color(FG)
        else:
            # aucune étoile sélectionnée : panneau en attente
            axR.set_title("Réf. : (cliquez une étoile)", color=FG2,
                          fontsize=8)
            axR.set_xlim(axL.get_xlim())
            axR.set_ylim(axL.get_ylim())
            axR.text(0.5, 0.5, "Sélectionnez une étoile\ndans le tableau",
                     transform=axR.transAxes, ha="center", va="center",
                     color=FG2, fontsize=8)

        self._fig.tight_layout()
        self._traj_canvas.draw_idle()

    def _status_label(self):
        # widget de statut (dernier packé en bas) — sert d'ancre 'before'
        return self._status_bar

    def _get_h_target(self):
        s = self._h_target.get().strip().replace(",", ".")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    def _on_star_select(self, event=None):
        """Affiche la trajectoire de l'étoile sélectionnée sur le graphe."""
        if self._trajectory is None or self._results_df is None:
            return
        sel = self._tree.selection()
        if not sel:
            return
        values = self._tree.item(sel[0], "values")
        if not values:
            return
        star_name = str(values[0]).strip()

        # retrouver la ligne dans le dataframe de résultats
        df = self._results_df
        match = df[df["Name"].astype(str).str.strip() == star_name]
        if match.empty:
            return
        row = match.iloc[0]

        try:
            coord = SkyCoord(ra=float(row["RA"]) * u.deg,
                             dec=float(row["Dec"]) * u.deg, frame="icrs")
        except Exception:
            return

        # instant de recherche courant (pour placer le repère de l'étoile)
        obstime = None
        try:
            obstime = parse_datetime(self._get_datetime_str())
        except Exception:
            obstime = self._trajectory.t_end

        alt = row["Alt_deg"] if "Alt_deg" in df.columns and pd.notna(
            row.get("Alt_deg")) else None

        self._selected_star = {
            "name": star_name,
            "coord": coord,
            "obstime": obstime,
            "alt": float(alt) if alt is not None else None,
        }
        self._display_trajectory()

    def _on_graph_press(self, event):
        # démarrer le glissement si on clique près de la ligne h visée
        if event.inaxes is not self._ax_target or event.ydata is None:
            return
        h = self._get_h_target()
        if h is None:
            return
        # tolérance de préhension : ~4 % de la hauteur visible de l'axe
        lo, hi = self._ax_target.get_ylim()
        tol = max(1.0, 0.04 * (hi - lo))
        if abs(float(event.ydata) - h) <= tol:
            self._dragging_hline = True
            self._traj_canvas.get_tk_widget().config(cursor="sb_v_double_arrow")

    def _on_graph_motion(self, event):
        if not self._dragging_hline:
            return
        if event.inaxes is not self._ax_target or event.ydata is None:
            return
        h = max(0.0, min(90.0, float(event.ydata)))
        # mise à jour en direct : champ + ligne (graphe), sans recalcul lourd
        self._h_target.set(f"{h:.1f}")
        self._display_trajectory()
        X = ft.airmass_from_alt(h) if ft else None
        self._status(f"h visée = {h:.1f}°"
                     + (f"  (X≈{X:.2f})" if X else ""))

    def _on_graph_release(self, event):
        if not self._dragging_hline:
            return
        self._dragging_hline = False
        self._traj_canvas.get_tk_widget().config(cursor="")
        # au relâchement : recalcul de la colonne Δh et re-tri du tableau
        self._recompute_dh_and_refresh()

    def _recompute_dh_and_refresh(self):
        """Recalcule Δh = alt - h visée pour tous les résultats et rafraîchit
        le tableau (appelé au relâchement du glissement de la ligne)."""
        df = self._results_df
        if df is None or df.empty or "Alt_deg" not in df.columns:
            return
        h = self._get_h_target()
        if h is None:
            return
        df = df.copy()
        df["DHvise_deg"] = df["Alt_deg"] - h
        # conserver le tri courant s'il porte sur Δh, sinon garder l'ordre
        self._results_df = df
        if getattr(self, "_sort_col", None) in ("Δh (°)",):
            self._sort_by(self._sort_col, keep_dir=True)
        else:
            parts = self._status_var.get().split("  ", 1)
            ti = parts[1] if len(parts) > 1 else ""
            self._display_results(df, ti)

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
