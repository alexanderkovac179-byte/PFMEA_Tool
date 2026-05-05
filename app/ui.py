"""
ui.py – FMEA Tool | CustomTkinter redesign.

Moderná desktopová aplikácia pre AI-asistovanú procesnú FMEA.

Funkcie:
- Sidebar navigácia (Domov / História / Nastavenia)
- Dark / Light / System theme
- Drag-and-drop zóna pre vstupné súbory (tkinterdnd2, fallback na file picker)
- Paralelný progres s fázovým stepper-om + live log viewom
- Akčné tlačidlo mení stav (idle → running → success/error)
- História runov so scorecardmi a "otvoriť Excel" / "otvoriť log"
- Nastavenia: téma, model, paralelizmus

Závislosti:
    pip install customtkinter pillow tkinterdnd2
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog

# Voliteľný drag-and-drop (ak tkinterdnd2 chýba, UI funguje s file pickerom)
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

from app.config import (
    OUTPUT_DIR,
    CLAUDE_MODEL,
    MAX_PARALLEL_STEPS,
)
from app.pipeline import run_fmea_pipeline
from app.preflight_dialog import PreflightDialog, add_tooltip


# ══════════════════════════════════════════════════════════════════════════════
# KONŠTANTY A KONFIGURÁCIA
# ══════════════════════════════════════════════════════════════════════════════

APP_NAME         = "PFMEA Tool"
APP_VERSION      = "0.2"
HISTORY_FILE     = Path("data/.ui_history.json")
SUPPORTED_EXT    = {".pdf", ".docx", ".xlsx", ".txt", ".md"}

# ── DIZAJNOVÝ SYSTÉM (design tokens) ──────────────────────────────────────────
# Tmavé / svetlé odtiene (tuple = (light, dark))

# Hlavné pozadia – jemnejšie ako čistá čierna
BG_APP       = ("#f7f7f9", "#1a1b1e")   # app background
BG_SIDEBAR   = ("#ffffff", "#1f2023")   # sidebar (trochu iný odtieň pre oddelenie)
BG_CARD      = ("#ffffff", "#27282c")   # kartový obsah
BG_CARD_HI   = ("#f3f4f6", "#2f3135")   # hover / zvýraznená karta
BG_SUBTLE    = ("#f3f4f6", "#212225")   # subtílne pozadie (napr. nav button)
BG_SUBTLE_HI = ("#e7e8ec", "#2b2c30")   # hover na subtílnom pozadí
BG_INPUT     = ("#ffffff", "#1c1d20")   # input fields
BG_PROGRESS  = ("#e7e8ec", "#2a2b2f")   # track progress baru

# Rámčeky (borders) – jemné, na oddelenie sekcií
BORDER_SOFT  = ("#e4e4e7", "#35363b")   # štandardný border karty
BORDER_FIRM  = ("#d4d4d8", "#45464b")   # výraznejší border

# Typografia
TEXT_PRIMARY   = ("#18181b", "#f4f4f5")  # primárny text
TEXT_SECONDARY = ("#52525b", "#a1a1aa")  # tlmenejší (popisky, metadata)
TEXT_MUTED     = ("#71717a", "#71717a")  # najjemnejší (timestampy, helpers)

# Akcentové farby – brand (modrá)
COLOR_IDLE          = "#3b82f6"
COLOR_IDLE_HOVER    = "#2563eb"
COLOR_BRAND_MUTED   = "#1d4ed8"   # tmavší variant pre gradient
COLOR_SUCCESS       = "#22c55e"
COLOR_SUCCESS_HOVER = "#16a34a"
COLOR_ERROR         = "#ef4444"
COLOR_ERROR_HOVER   = "#dc2626"
COLOR_WARN          = "#f59e0b"
COLOR_WARN_HOVER    = "#d97706"

# Radius pre rounded corners – konzistentný
RADIUS_SM   = 6
RADIUS_MD   = 10
RADIUS_LG   = 14
RADIUS_XL   = 18

# Typy súborov – farby
FILE_COLORS = {
    ".pdf":  "#ef4444",
    ".docx": "#3b82f6",
    ".xlsx": "#22c55e",
    ".txt":  "#64748b",
    ".md":   "#8b5cf6",
}
FILE_LABELS = {
    ".pdf":  "PDF",
    ".docx": "DOC",
    ".xlsx": "XLSX",
    ".txt":  "TXT",
    ".md":   "MD",
}

# Fázy pipeline-u – rozlíšené podľa kľúčových slov zo status správ
# a/alebo explicitného [XX%] prefixu.
PHASES = [
    ("Dokumenty",    (0, 5),    ["načítav"]),
    ("Názov",        (5, 10),   ["identifikuj", "názov procesu"]),
    ("Kroky",        (10, 40),  ["extrahu", "krokov"]),
    ("Generovanie",  (40, 80),  ["generuj", "hotov"]),
    ("Validácia",    (80, 90),  ["validuj", "počítam"]),
    ("Export",       (90, 100), ["export", "dokončen", "úspešn", "log uložený"]),
]


# ══════════════════════════════════════════════════════════════════════════════
# POMOCNÉ FUNKCIE
# ══════════════════════════════════════════════════════════════════════════════

def load_history() -> dict:
    default = {"input_dirs": [], "output_dir": OUTPUT_DIR, "runs": []}
    if not HISTORY_FILE.exists():
        return default
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        for k, v in default.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return default


def save_history(data: dict) -> None:
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def format_file_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            if unit == "B":
                return f"{size:.0f} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_timestamp_iso(ts_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(ts_iso)
        return dt.strftime("%d.%m.%Y  %H:%M")
    except Exception:
        return ts_iso


def format_relative_time(ts_iso: str) -> str:
    """Vráti relatívny čas typu 'pred 2 h', 'pred 15 min', 'práve teraz'."""
    try:
        dt = datetime.fromisoformat(ts_iso)
        delta = datetime.now() - dt
        if delta.total_seconds() < 60:
            return "práve teraz"
        if delta.days >= 1:
            return f"pred {delta.days} d" if delta.days > 1 else "včera"
        h = delta.seconds // 3600
        m = (delta.seconds % 3600) // 60
        if h >= 1:
            return f"pred {h} h"
        return f"pred {m} min"
    except Exception:
        return "–"


def open_path_in_os(path) -> None:
    """Otvorí súbor alebo priečinok natívnou aplikáciou OS."""
    path = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(path)   # noqa
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception as e:
        print(f"Nemôžem otvoriť {path}: {e}")


def phase_index_for_pct(pct: int) -> int:
    for i, (_, (start, end), _) in enumerate(PHASES):
        if start <= pct < end:
            return i
    return len(PHASES) - 1


def detect_pct_from_message(msg: str) -> int | None:
    """Vytiahne XX% prefix zo status správy ([75%] ...)."""
    m = re.match(r"\s*\[(\d+)\s*%\]", msg)
    if m:
        return int(m.group(1))
    # Fallback – hľadaj podľa kľúčových slov
    low = msg.lower()
    for _name, (_start, end), keywords in PHASES:
        if any(kw in low for kw in keywords):
            return end - 1
    return None


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-DEDIČNOSŤ: CTk + TkinterDnD
# ══════════════════════════════════════════════════════════════════════════════
# tkinterdnd2 vyžaduje registrovať DND rozšírenie do Tcl interpreteru. Keď
# používame customtkinter, musíme to spraviť sami cez mixin. Všetky widgety
# v tomto root-e potom dostanú drop_target_register / dnd_bind metódy.

if _DND_AVAILABLE:
    class _Root(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            try:
                self.TkdndVersion = TkinterDnD._require(self)
            except Exception:
                self.TkdndVersion = None
else:
    class _Root(ctk.CTk):
        pass


# ══════════════════════════════════════════════════════════════════════════════
# WIDGETY
# ══════════════════════════════════════════════════════════════════════════════

class FileBadge(ctk.CTkLabel):
    """Farebný 'pill' badge s názvom typu súboru (PDF/DOC/XLSX/TXT/MD)."""

    def __init__(self, parent, ext: str):
        super().__init__(
            parent,
            text=FILE_LABELS.get(ext, "?"),
            width=52, height=28,
            corner_radius=6,
            fg_color=FILE_COLORS.get(ext, "#64748b"),
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )


class FileRow(ctk.CTkFrame):
    """Jeden riadok v zozname súborov: badge + meno + veľkosť + ✕."""

    BASE_FG  = BG_CARD
    HOVER_FG = BG_CARD_HI

    def __init__(self, parent, path: Path, on_remove, cached_size: int | None = None):
        super().__init__(parent, fg_color=self.BASE_FG, corner_radius=RADIUS_MD, height=50)
        self.path = path
        self.grid_columnconfigure(1, weight=1)
        self.grid_propagate(False)

        ext = path.suffix.lower()
        FileBadge(self, ext).grid(row=0, column=0, padx=(12, 12), pady=10)

        name_lbl = ctk.CTkLabel(
            self,
            text=path.name,
            anchor="w",
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        name_lbl.grid(row=0, column=1, sticky="ew", padx=4, pady=10)

        # Použijeme cache ak je k dispozícii (šetrí stat() pri rebuilde)
        if cached_size is not None:
            size_txt = format_file_size(cached_size)
        elif path.exists():
            size_txt = format_file_size(path.stat().st_size)
        else:
            size_txt = "–"

        size_lbl = ctk.CTkLabel(
            self,
            text=size_txt,
            anchor="e",
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            width=96,
        )
        size_lbl.grid(row=0, column=2, padx=6, pady=10)

        ctk.CTkButton(
            self,
            text="✕", width=32, height=32,
            corner_radius=RADIUS_SM,
            fg_color="transparent",
            hover_color=BG_SUBTLE_HI,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            command=lambda: on_remove(path),
        ).grid(row=0, column=3, padx=(4, 8), pady=6)

        # Hover highlight
        for w in (self, name_lbl, size_lbl):
            w.bind("<Enter>", lambda e: self._hover(True),  add="+")
            w.bind("<Leave>", lambda e: self._hover(False), add="+")

    def _hover(self, on: bool):
        self.configure(fg_color=self.HOVER_FG if on else self.BASE_FG)


class DropZone(ctk.CTkFrame):
    """
    Veľká kliknuteľná/drop-target zóna pre vstupné súbory.
    Pri drag-over zmení farbu borderu na akcentnú.

    Dva módy:
    - full    (default): 180 px, veľká ikona, inštrukcie
    - compact: 60 px, len ikona + "Pridať ďalšie súbory"
    """

    NORMAL_BORDER   = BORDER_FIRM
    ACTIVE_BORDER   = (COLOR_IDLE, COLOR_IDLE)
    NORMAL_FG       = BG_CARD
    ACTIVE_FG       = ("#eff6ff", "#172554")

    HEIGHT_FULL    = 180
    HEIGHT_COMPACT = 68

    def __init__(self, parent, on_files_added):
        super().__init__(
            parent,
            fg_color=self.NORMAL_FG,
            border_color=self.NORMAL_BORDER,
            border_width=2,
            corner_radius=RADIUS_LG,
            height=self.HEIGHT_FULL,
        )
        self.on_files_added = on_files_added
        self.grid_propagate(False)
        self._mode = "full"

        # ── Full mode content (vertikálne centrované) ─────────────────────────
        self.inner_full = ctk.CTkFrame(self, fg_color="transparent")
        self.inner_full.pack(expand=True, fill="both", padx=20, pady=20)

        self.icon = ctk.CTkLabel(
            self.inner_full, text="📁",
            font=ctk.CTkFont(family="Segoe UI Emoji", size=50),
        )
        self.icon.pack(pady=(8, 6))

        self.main_label = ctk.CTkLabel(
            self.inner_full,
            text=("Pretiahni sem súbory na analýzu"
                  if _DND_AVAILABLE else
                  "Klikni pre výber súborov"),
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.main_label.pack()

        self.sub_label = ctk.CTkLabel(
            self.inner_full,
            text=(
                "alebo klikni pre výber · PDF · DOCX · XLSX · TXT · MD"
                if _DND_AVAILABLE else
                "Podporované formáty: PDF · DOCX · XLSX · TXT · MD"
            ),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        )
        self.sub_label.pack(pady=(4, 0))

        # ── Compact mode content (horizontálne) ──────────────────────────────
        self.inner_compact = ctk.CTkFrame(self, fg_color="transparent")

        self.compact_icon = ctk.CTkLabel(
            self.inner_compact, text="➕",
            font=ctk.CTkFont(family="Segoe UI Emoji", size=22),
            text_color=(COLOR_IDLE, "#93c5fd"),
        )
        self.compact_icon.pack(side="left", padx=(22, 14), pady=16)

        self.compact_label = ctk.CTkLabel(
            self.inner_compact,
            text="Pridať ďalšie súbory",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.compact_label.pack(side="left", pady=16)

        self.compact_hint = ctk.CTkLabel(
            self.inner_compact,
            text="— pretiahni alebo klikni",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        )
        self.compact_hint.pack(side="left", padx=(8, 0), pady=16)

        # Kliknutie kdekoľvek vo vnútri dropzóny otvorí file picker
        clickable = (
            self, self.inner_full, self.icon, self.main_label, self.sub_label,
            self.inner_compact, self.compact_icon, self.compact_label, self.compact_hint,
        )
        for w in clickable:
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>",    lambda e: self._hover(True))
            w.bind("<Leave>",    lambda e: self._hover(False))

        # Registrácia DND
        if _DND_AVAILABLE:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<DropEnter>>", lambda e: self._set_active(True))
                self.dnd_bind("<<DropLeave>>", lambda e: self._set_active(False))
                self.dnd_bind("<<Drop>>",      self._on_drop)
            except Exception as e:
                print(f"DND registrácia zlyhala: {e}")

    def set_compact(self, compact: bool):
        """Prepne medzi full a compact módom."""
        new_mode = "compact" if compact else "full"
        if new_mode == self._mode:
            return
        self._mode = new_mode

        if compact:
            self.inner_full.pack_forget()
            self.inner_compact.pack(fill="both", expand=True)
            self.configure(height=self.HEIGHT_COMPACT)
        else:
            self.inner_compact.pack_forget()
            self.inner_full.pack(expand=True, fill="both", padx=20, pady=20)
            self.configure(height=self.HEIGHT_FULL)

    def _hover(self, on):
        if on:
            self.configure(border_color=(COLOR_IDLE, COLOR_IDLE))
        else:
            self.configure(border_color=self.NORMAL_BORDER)

    def _set_active(self, active: bool):
        if active:
            self.configure(
                border_color=self.ACTIVE_BORDER,
                fg_color=self.ACTIVE_FG,
            )
            if self._mode == "full":
                self.main_label.configure(text="Pusti súbory…")
            else:
                self.compact_label.configure(text="Pusti súbory…")
        else:
            self.configure(
                border_color=self.NORMAL_BORDER,
                fg_color=self.NORMAL_FG,
            )
            if self._mode == "full":
                self.main_label.configure(
                    text=("Pretiahni sem súbory na analýzu"
                          if _DND_AVAILABLE else "Klikni pre výber súborov"),
                )
            else:
                self.compact_label.configure(text="Pridať ďalšie súbory")

    def _on_click(self, _event=None):
        paths = filedialog.askopenfilenames(
            title="Vyber vstupné dokumenty",
            filetypes=[
                ("Dokumenty", "*.pdf *.docx *.xlsx *.txt *.md"),
                ("Všetky",    "*.*"),
            ],
        )
        if paths:
            self.on_files_added([Path(p) for p in paths])

    def _on_drop(self, event):
        self._set_active(False)
        # event.data je whitespace-separated list; cesty s medzerami sú
        # v zložených zátvorkách
        raw = event.data
        paths = []
        for chunk in re.findall(r"\{([^}]*)\}|(\S+)", raw):
            p = chunk[0] or chunk[1]
            if not p:
                continue
            pth = Path(p)
            if pth.is_dir():
                for f in pth.rglob("*"):
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXT:
                        paths.append(f)
            elif pth.suffix.lower() in SUPPORTED_EXT:
                paths.append(pth)
        if paths:
            self.on_files_added(paths)


class PhaseStepper(ctk.CTkFrame):
    """Moderný horizontálny stepper fáz pipeline-u.

    Každá fáza = kruh s číslom (pending/running) alebo ✓ (done) + názov pod ním.
    Medzi kruhmi sú farebne progresívne konektory.
    """

    DOT_SIZE = 40

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self.dots        = []
        self.dot_labels  = []
        self.name_labels = []
        self.connects    = []

        # Rovnomerné rozdelenie priestoru medzi fázami
        for i, (name, _, _) in enumerate(PHASES):
            col_idx = i * 2

            # Stĺpec = kruh hore, názov dole
            col = ctk.CTkFrame(self, fg_color="transparent")
            col.grid(row=0, column=col_idx, sticky="n")

            # Samotný kruh
            dot = ctk.CTkFrame(
                col,
                width=self.DOT_SIZE,
                height=self.DOT_SIZE,
                corner_radius=self.DOT_SIZE // 2,
                fg_color=BG_SUBTLE,
            )
            dot.pack()
            dot.pack_propagate(False)
            dot.grid_propagate(False)

            # Text v kruhu (číslo / ✓ / ✕)
            dot_text = ctk.CTkLabel(
                dot, text=str(i + 1),
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color=TEXT_SECONDARY,
            )
            dot_text.place(relx=0.5, rely=0.5, anchor="center")

            # Meno fázy pod kruhom
            name_lbl = ctk.CTkLabel(
                col, text=name,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_SECONDARY,
            )
            name_lbl.pack(pady=(10, 0))

            self.dots.append(dot)
            self.dot_labels.append(dot_text)
            self.name_labels.append(name_lbl)

            # Konektor medzi fázami (okrem poslednej)
            if i < len(PHASES) - 1:
                conn = ctk.CTkFrame(
                    self,
                    height=3, width=52,
                    fg_color=BG_SUBTLE,
                    corner_radius=2,
                )
                # Zarovnaný vertikálne so stredom kruhu
                conn.grid(
                    row=0, column=col_idx + 1,
                    pady=(self.DOT_SIZE // 2 + 1, 0),
                    padx=4, sticky="ew",
                )
                self.connects.append(conn)

    def set_progress(self, pct: int):
        idx = phase_index_for_pct(pct) if pct < 100 else len(PHASES)

        for i in range(len(self.dots)):
            dot   = self.dots[i]
            label = self.dot_labels[i]
            name  = self.name_labels[i]

            if i < idx:
                # Dokončená fáza – zelený kruh s bielym ✓
                dot.configure(fg_color=COLOR_SUCCESS)
                label.configure(
                    text="✓",
                    text_color="white",
                    font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
                )
                name.configure(
                    text_color=COLOR_SUCCESS,
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                )
            elif i == idx and pct < 100:
                # Prebiehajúca fáza – modrý kruh s číslom
                dot.configure(fg_color=COLOR_IDLE)
                label.configure(
                    text=str(i + 1),
                    text_color="white",
                    font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                )
                name.configure(
                    text_color=(COLOR_IDLE, "#93c5fd"),
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                )
            else:
                # Nadchádzajúca fáza – sivý kruh s číslom
                dot.configure(fg_color=BG_SUBTLE)
                label.configure(
                    text=str(i + 1),
                    text_color=TEXT_SECONDARY,
                    font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                )
                name.configure(
                    text_color=TEXT_SECONDARY,
                    font=ctk.CTkFont(family="Segoe UI", size=13),
                )

        for i, conn in enumerate(self.connects):
            if i < idx:
                conn.configure(fg_color=COLOR_SUCCESS)
            else:
                conn.configure(fg_color=BG_SUBTLE)

    def set_error(self, idx: int):
        """Označí daný krok červeným ✕ a nasledujúce nechá šedé."""
        if 0 <= idx < len(self.dots):
            self.dots[idx].configure(fg_color=COLOR_ERROR)
            self.dot_labels[idx].configure(
                text="✕", text_color="white",
                font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            )
            self.name_labels[idx].configure(
                text_color=COLOR_ERROR,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            )

    def reset(self):
        self.set_progress(0)


def _short_model_name(model: str) -> str:
    """claude-opus-4-7 → Opus 4.7 ; claude-sonnet-4-6 → Sonnet 4.6"""
    s = str(model).replace("claude-", "")
    s = s.replace("opus-",   "Opus ")
    s = s.replace("sonnet-", "Sonnet ")
    s = s.replace("haiku-",  "Haiku ")
    return s.replace("-", ".")


class RunCard(ctk.CTkFrame):
    """
    Karta s detailom jedného dokončeného runu v histórii.
    - hover: jemný zelený border + svetlejší fg
    - skrátený model name, okrúhlené trvanie
    - ľavý zelený stripe ako accent
    """

    BASE_FG     = BG_CARD
    HOVER_FG    = BG_CARD_HI
    BASE_BORDER = BORDER_SOFT
    HOVER_BORDER = ("#bbf7d0", "#14532d")

    def __init__(self, parent, run: dict):
        super().__init__(
            parent,
            fg_color=self.BASE_FG,
            corner_radius=12,
            border_width=1,
            border_color=self.BASE_BORDER,
        )
        self.grid_columnconfigure(1, weight=1)

        # Ľavý indikátor
        status_color = COLOR_SUCCESS if run.get("status") == "success" else COLOR_WARN
        ctk.CTkFrame(
            self, width=4, fg_color=status_color, corner_radius=2,
        ).grid(row=0, column=0, rowspan=3, sticky="ns", padx=(8, 0), pady=12)

        # Header riadok
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=1, sticky="ew", padx=18, pady=(14, 0))
        head.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            head, text=run.get("process_name", "Neznámy proces"),
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        ts_iso = run.get("timestamp", "")
        ctk.CTkLabel(
            head, text=format_relative_time(ts_iso),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY,
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        # Metadata riadok
        duration = run.get("duration_sec", 0)
        if duration < 60:
            dur_txt = f"{duration:.0f} s"
        else:
            dur_txt = f"{duration/60:.1f} min"
        meta_txt = (
            f"📊  {run.get('item_count', 0)} položiek    "
            f"📁  {run.get('document_count', 0)} dokumentov    "
            f"⏱  {dur_txt}    "
            f"🤖  {_short_model_name(run.get('model', 'Claude'))}"
        )
        ctk.CTkLabel(
            self, text=meta_txt,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).grid(row=1, column=1, sticky="ew", padx=18, pady=(4, 0))

        # Akcie
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=1, sticky="ew", padx=18, pady=(10, 14))

        output_file = run.get("output_file")
        if output_file and Path(output_file).exists():
            ctk.CTkButton(
                actions, text="📂  Otvoriť Excel",
                height=32, corner_radius=8,
                fg_color=COLOR_SUCCESS, hover_color=COLOR_SUCCESS_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                command=lambda: open_path_in_os(output_file),
            ).pack(side="left", padx=(0, 8))
        else:
            ctk.CTkLabel(
                actions, text="⚠ Excel súbor nenájdený",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=COLOR_WARN,
            ).pack(side="left")

        log_file = run.get("log_file")
        if log_file and Path(log_file).exists():
            ctk.CTkButton(
                actions, text="📝  Log",
                height=32, corner_radius=8, width=90,
                fg_color="transparent", border_width=1,
                border_color=("gray70", "gray30"),
                text_color=("gray20", "gray80"),
                hover_color=BORDER_SOFT,
                command=lambda: open_path_in_os(log_file),
            ).pack(side="left", padx=4)

        if output_file:
            folder = Path(output_file).parent
            ctk.CTkButton(
                actions, text="📁  Priečinok",
                height=32, corner_radius=8, width=110,
                fg_color="transparent", border_width=1,
                border_color=("gray70", "gray30"),
                text_color=("gray20", "gray80"),
                hover_color=BORDER_SOFT,
                command=lambda: open_path_in_os(folder),
            ).pack(side="left", padx=4)

        # Hover state: prebehnúť cez všetky child widgety
        self._bind_hover_recursive(self)

    def _bind_hover_recursive(self, widget):
        widget.bind("<Enter>", lambda e: self._set_hover(True), add="+")
        widget.bind("<Leave>", lambda e: self._set_hover(False), add="+")
        for child in widget.winfo_children():
            self._bind_hover_recursive(child)

    def _set_hover(self, on: bool):
        if on:
            self.configure(
                fg_color=self.HOVER_FG,
                border_color=self.HOVER_BORDER,
            )
        else:
            self.configure(
                fg_color=self.BASE_FG,
                border_color=self.BASE_BORDER,
            )


class Toast(ctk.CTkToplevel):
    """
    Notification, ktorá sa zobrazí v pravom dolnom rohu hlavného okna
    a po `duration_ms` ms zmizne. Používa transparency animáciu.
    """

    KINDS = {
        "success": ("✓", COLOR_SUCCESS, "white"),
        "error":   ("✕", COLOR_ERROR,   "white"),
        "info":    ("ⓘ", COLOR_IDLE,    "white"),
        "warning": ("⚠", COLOR_WARN,    "white"),
    }

    @staticmethod
    def show(parent, message: str, kind: str = "success", duration_ms: int = 3500):
        try:
            t = Toast(parent, message, kind, duration_ms)
            t._slide_in()
        except Exception as e:
            print(f"Toast zlyhal: {e}")

    def __init__(self, parent, message: str, kind: str, duration_ms: int):
        super().__init__(parent)
        self.duration_ms = duration_ms

        # Bezrámová okná – vyzerajú ako reálne notifikácie
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            pass

        icon_char, bg_color, text_color = self.KINDS.get(kind, self.KINDS["info"])

        self.configure(fg_color=bg_color)
        body = ctk.CTkFrame(self, fg_color=bg_color, corner_radius=10)
        body.pack(padx=0, pady=0, fill="both", expand=True)

        ctk.CTkLabel(
            body, text=icon_char, text_color=text_color, width=32,
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
        ).pack(side="left", padx=(14, 6), pady=12)

        ctk.CTkLabel(
            body, text=message, text_color=text_color,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            wraplength=320, justify="left", anchor="w",
        ).pack(side="left", padx=(2, 14), pady=12, fill="x", expand=True)

        # Klik kdekoľvek = zatvor
        for w in (self, body):
            w.bind("<Button-1>", lambda e: self._fade_out())

        # Pozícia
        self.update_idletasks()
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx() + parent.winfo_width() - self.winfo_width() - 24
            py = parent.winfo_rooty() + parent.winfo_height() - self.winfo_height() - 60
            self.geometry(f"+{max(px, 24)}+{max(py, 24)}")
        except Exception:
            pass

    def _slide_in(self, alpha: float = 0.0):
        try:
            alpha = min(0.95, alpha + 0.1)
            self.attributes("-alpha", alpha)
        except Exception:
            pass
        if alpha < 0.95:
            self.after(20, lambda: self._slide_in(alpha))
        else:
            self.after(self.duration_ms, self._fade_out)

    def _fade_out(self, alpha: float = 0.95):
        try:
            alpha = max(0.0, alpha - 0.1)
            self.attributes("-alpha", alpha)
        except Exception:
            self.destroy()
            return
        if alpha > 0.0:
            self.after(20, lambda: self._fade_out(alpha))
        else:
            self.destroy()


class StatusBar(ctk.CTkFrame):
    """
    Tenký pásik dole v okne – ukazuje model, posledný run, API status.
    Štandardný pattern z IDE / pro tools.
    """

    def __init__(self, parent, app: "FmeaStudio"):
        super().__init__(
            parent, height=32,
            fg_color=BG_APP,
            corner_radius=0,
        )
        self.app = app
        self.grid_propagate(False)
        self.pack_propagate(False)

        # Ľavá strana – API status
        api_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
        self.api_dot = ctk.CTkLabel(
            self, text="●", width=14,
            text_color=COLOR_SUCCESS if api_ok else COLOR_ERROR,
            font=ctk.CTkFont(family="Segoe UI", size=13),
        )
        self.api_dot.pack(side="left", padx=(12, 2))

        ctk.CTkLabel(
            self, text="API pripojené" if api_ok else "API nedostupné",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray35", "gray70"),
        ).pack(side="left", padx=(0, 12))

        self._sep(side="left")

        # Model – referenciu si držíme, aby sme mohli refreshnúť pri zmene v Settings
        ctk.CTkLabel(
            self, text="Model:",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(12, 4))
        self.model_lbl = ctk.CTkLabel(
            self, text=self._short_model(self._current_model()),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=("gray25", "gray80"),
        )
        self.model_lbl.pack(side="left")

        # Pravá strana – posledná analýza + verzia
        ctk.CTkLabel(
            self, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray50", "gray50"),
        ).pack(side="right", padx=(0, 12))

        self._sep(side="right")

        self.last_run_lbl = ctk.CTkLabel(
            self, text="Žiadna analýza",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        )
        self.last_run_lbl.pack(side="right", padx=(12, 12))

        ctk.CTkLabel(
            self, text="Posledná:",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
        ).pack(side="right", padx=(12, 4))

        self._sep(side="right")

        self.refresh()

    def _sep(self, side: str):
        ctk.CTkFrame(
            self, width=1, fg_color=("gray80", "gray22"),
        ).pack(side=side, fill="y", pady=6)

    def _current_model(self) -> str:
        """Vráti aktuálne zvolený model z user_state, fallback CLAUDE_MODEL."""
        try:
            return self.app.user_state.get("model", CLAUDE_MODEL)
        except Exception:
            return CLAUDE_MODEL

    def _short_model(self, model: str) -> str:
        s = model.replace("claude-", "")
        s = s.replace("opus-",   "Opus ")
        s = s.replace("sonnet-", "Sonnet ")
        s = s.replace("haiku-",  "Haiku ")
        return s.replace("-", ".")

    def refresh(self):
        runs = self.app.history.get("runs", [])
        if runs:
            ts = runs[0].get("timestamp", "")
            self.last_run_lbl.configure(text=format_relative_time(ts))
        else:
            self.last_run_lbl.configure(text="žiadna")
        # Refresh model tiež – ak user zmenil v Settings
        if hasattr(self, "model_lbl"):
            self.model_lbl.configure(text=self._short_model(self._current_model()))


# ══════════════════════════════════════════════════════════════════════════════
# VIEWS
# ══════════════════════════════════════════════════════════════════════════════

class ResultsSummary(ctk.CTkFrame):
    """
    Karta s výsledkami analýzy – zobrazí sa po úspešnom dokončení namiesto
    progress karty. Obsahuje hero s procesom, metric chips a akčné tlačidlá.
    """

    def __init__(self, parent, on_open_excel, on_open_folder, on_new_analysis):
        super().__init__(
            parent,
            fg_color=BG_CARD,
            corner_radius=RADIUS_LG,
            border_width=1,
            border_color=("#bbf7d0", "#14532d"),
        )
        self._on_open_excel   = on_open_excel
        self._on_open_folder  = on_open_folder
        self._on_new_analysis = on_new_analysis
        self.grid_columnconfigure(0, weight=1)

        # ── Header: zelený kruh + názov ───────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 18))
        header.grid_columnconfigure(1, weight=1)

        check = ctk.CTkFrame(
            header, width=54, height=54,
            corner_radius=27, fg_color=COLOR_SUCCESS,
        )
        check.grid(row=0, column=0, padx=(0, 16), rowspan=2)
        check.grid_propagate(False)
        check.pack_propagate(False)
        ctk.CTkLabel(
            check, text="✓", text_color="white",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            header, text="Analýza dokončená",
            font=ctk.CTkFont(family="Segoe UI", size=19, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=1, sticky="w")
        self.subtitle = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self.subtitle.grid(row=1, column=1, sticky="w", pady=(3, 0))

        # ── Metric chips ──────────────────────────────────────────────────────
        chips = ctk.CTkFrame(self, fg_color="transparent")
        chips.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 18))
        for i in range(4):
            chips.grid_columnconfigure(i, weight=1, uniform="chip")

        self._chip_values = []
        chip_labels = ["POLOŽIEK", "DOKUMENTY", "TRVANIE", "MODEL"]
        for i, label in enumerate(chip_labels):
            left_pad = 0 if i == 0 else 5
            right_pad = 5 if i < 3 else 0

            chip = ctk.CTkFrame(
                chips,
                fg_color=BG_CARD_HI,
                corner_radius=RADIUS_MD,
                border_width=1,
                border_color=BORDER_SOFT,
            )
            chip.grid(row=0, column=i, sticky="ew",
                      padx=(left_pad, right_pad))

            ctk.CTkLabel(
                chip, text=label,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=TEXT_MUTED,
                anchor="w",
            ).pack(anchor="w", padx=14, pady=(13, 2))

            value_lbl = ctk.CTkLabel(
                chip, text="–",
                font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
                text_color=TEXT_PRIMARY,
                anchor="w",
            )
            value_lbl.pack(anchor="w", padx=14, pady=(0, 12))
            self._chip_values.append(value_lbl)

        # ── Akcie ─────────────────────────────────────────────────────────────
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 22))
        actions.grid_columnconfigure(0, weight=1)

        self.open_btn = ctk.CTkButton(
            actions, text="📂  Otvoriť Excel",
            height=50, corner_radius=10,
            fg_color=COLOR_SUCCESS, hover_color=COLOR_SUCCESS_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            command=self._open_excel,
        )
        self.open_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            actions, text="Otvoriť priečinok",
            height=50, width=180, corner_radius=10,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"),
            text_color=("gray20", "gray80"),
            hover_color=BG_CARD_HI,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            command=self._open_folder,
        ).grid(row=0, column=1, padx=8)

        ctk.CTkButton(
            actions, text="Nová analýza",
            height=50, width=170, corner_radius=10,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"),
            text_color=("gray20", "gray80"),
            hover_color=BG_CARD_HI,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            command=self._new_analysis,
        ).grid(row=0, column=2, padx=(8, 0))

    def populate(self, process_name: str, item_count: int,
                 document_count: int, duration_sec: float, model: str):
        self.subtitle.configure(text=process_name)

        dur_txt = (
            f"{duration_sec:.0f} s" if duration_sec < 60
            else f"{duration_sec/60:.1f} min"
        )
        # Skráť dlhé model stringy ako "claude-opus-4-7" → "Opus 4.7"
        model_short = model.replace("claude-", "")
        model_short = model_short.replace("opus-",   "Opus ")
        model_short = model_short.replace("sonnet-", "Sonnet ")
        model_short = model_short.replace("haiku-",  "Haiku ")
        model_short = model_short.replace("-", ".")

        values = [str(item_count), str(document_count), dur_txt, model_short]
        for chip_label, value in zip(self._chip_values, values):
            chip_label.configure(text=value)

    def _open_excel(self):
        if self._on_open_excel:
            self._on_open_excel()

    def _open_folder(self):
        if self._on_open_folder:
            self._on_open_folder()

    def _new_analysis(self):
        if self._on_new_analysis:
            self._on_new_analysis()


class HomeView(ctk.CTkFrame):
    """Hlavná obrazovka: drop zone + zoznam súborov + spúšťacie tlačidlo + progress."""

    def __init__(self, parent, app: "FmeaStudio"):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.files: list[Path] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)   # files list expands

        # ── Titulok ───────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 16))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="Nová PFMEA analýza",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header, text="Pridaj vstupné dokumenty a spusti analýzu",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ── Drop zone ─────────────────────────────────────────────────────────
        self.dropzone = DropZone(self, on_files_added=self._add_files)
        self.dropzone.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 16))

        # ── Zoznam súborov ────────────────────────────────────────────────────
        self.files_section = ctk.CTkFrame(self, fg_color="transparent")
        self.files_section.grid(row=2, column=0, sticky="nsew", padx=32, pady=(0, 16))
        self.files_section.grid_columnconfigure(0, weight=1)
        self.files_section.grid_rowconfigure(1, weight=1)

        files_header = ctk.CTkFrame(self.files_section, fg_color="transparent")
        files_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        files_header.grid_columnconfigure(0, weight=1)

        self.files_label = ctk.CTkLabel(
            files_header, text="Načítané súbory",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            anchor="w",
        )
        self.files_label.grid(row=0, column=0, sticky="w")

        self.clear_btn = ctk.CTkButton(
            files_header, text="Vyčistiť", width=100, height=32, corner_radius=6,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"),
            text_color=("gray30", "gray70"),
            hover_color=BORDER_SOFT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self._clear_files,
        )
        self.clear_btn.grid(row=0, column=1, sticky="e")
        self.clear_btn.grid_remove()

        self.files_list = ctk.CTkScrollableFrame(
            self.files_section, fg_color=BG_SUBTLE,
            corner_radius=14,
            border_width=1,
            border_color=BORDER_SOFT,
        )
        self.files_list.grid(row=1, column=0, sticky="nsew")

        self.empty_label = ctk.CTkLabel(
            self.files_list,
            text="Zatiaľ nie sú pridané žiadne súbory",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=("gray55", "gray45"),
        )
        self.empty_label.pack(pady=20)

        # ── Výstupný priečinok + Štart ────────────────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=32, pady=(0, 24))
        bottom.grid_columnconfigure(0, weight=1)

        # Output ako mini-card (klikateľná cesta + Zmeniť tlačidlo)
        out_card = ctk.CTkFrame(
            bottom,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_SOFT,
        )
        out_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        out_card.grid_columnconfigure(1, weight=1)

        # Ikona priečinka
        ctk.CTkLabel(
            out_card, text="📁", width=44,
            font=ctk.CTkFont(family="Segoe UI Emoji", size=22),
        ).grid(row=0, column=0, rowspan=2, padx=(12, 4), pady=10)

        ctk.CTkLabel(
            out_card, text="Výstupný priečinok",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(10, 0))

        self.out_path_lbl = ctk.CTkLabel(
            out_card, text=self.app.user_state["output_dir"],
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=TEXT_PRIMARY,
            anchor="w",
            cursor="hand2",
        )
        self.out_path_lbl.grid(row=1, column=1, sticky="w", pady=(0, 10))
        self.out_path_lbl.bind(
            "<Button-1>",
            lambda e: open_path_in_os(self.out_path_lbl.cget("text")),
        )

        ctk.CTkButton(
            out_card, text="Zmeniť", width=100, height=36, corner_radius=8,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"),
            text_color=("gray20", "gray80"),
            hover_color=BORDER_SOFT,
            command=self._pick_output_dir,
        ).grid(row=0, column=2, rowspan=2, padx=12, pady=10)

        self.start_btn = ctk.CTkButton(
            bottom, text="▶  Spustiť analýzu",
            height=58, corner_radius=RADIUS_MD,
            fg_color=COLOR_IDLE, hover_color=COLOR_IDLE_HOVER,
            text_color="white",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            command=self._start_analysis,
        )
        self.start_btn.grid(row=1, column=0, sticky="ew")

        # ── Progress sekcia (skrytá, objaví sa pri behu) ──────────────────────
        self.progress_frame = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            corner_radius=RADIUS_LG,
            border_width=1,
            border_color=BORDER_SOFT,
        )
        self.progress_frame.grid(row=4, column=0, sticky="ew", padx=32, pady=(0, 24))
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_frame.grid_remove()

        # Stepper (nahor + nadol viac priestoru pre dobrý dojem karty)
        self.stepper = PhaseStepper(self.progress_frame)
        self.stepper.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 22))

        # Progress bar + % label
        bar_row = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        bar_row.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 14))
        bar_row.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            bar_row, height=10, corner_radius=5,
            progress_color=COLOR_IDLE,
            fg_color=BG_PROGRESS,
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 14))

        self.pct_label = ctk.CTkLabel(
            bar_row, text="0 %", width=66,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="e",
        )
        self.pct_label.grid(row=0, column=1, sticky="e")

        # Status ako pill s ikonou a textom
        self.status_container = ctk.CTkFrame(
            self.progress_frame,
            fg_color=BG_CARD_HI,
            corner_radius=10,
        )
        self.status_container.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 16))

        self.status_icon = ctk.CTkLabel(
            self.status_container, text="●",
            width=24,
            font=ctk.CTkFont(family="Segoe UI", size=15),
            text_color=("gray55", "gray55"),
        )
        self.status_icon.pack(side="left", padx=(14, 8), pady=10)

        self.status_label = ctk.CTkLabel(
            self.status_container,
            text="Čakám…",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True, padx=(0, 14), pady=10)

        # Log toggle – bordered button
        self.log_toggle = ctk.CTkButton(
            self.progress_frame, text="▼  Zobraziť log",
            height=36, corner_radius=8, width=170,
            fg_color="transparent",
            border_width=1,
            border_color=("gray80", "gray25"),
            text_color=("gray40", "gray70"),
            hover_color=BORDER_SOFT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self._toggle_log,
            anchor="w",
        )
        self.log_toggle.grid(row=3, column=0, sticky="w", padx=28, pady=(0, 12))

        # Log viewer – skrytý defaultne, toggleovateľný
        self.log_view = ctk.CTkTextbox(
            self.progress_frame, height=150, corner_radius=8,
            font=ctk.CTkFont(family="Consolas", size=13),
            fg_color=BG_APP,
            border_width=1,
            border_color=BG_SUBTLE_HI,
        )
        self.log_view.grid(row=4, column=0, sticky="ew", padx=28, pady=(0, 20))
        self.log_view.configure(state="disabled")
        self.log_view.grid_remove()
        self._log_shown = False

        # ── Summary karta (po úspešnom dokončení) ─────────────────────────────
        self.summary_frame = ResultsSummary(
            self,
            on_open_excel   = self._open_result,
            on_open_folder  = self._open_result_folder,
            on_new_analysis = self._new_analysis,
        )
        self.summary_frame.grid(row=5, column=0, sticky="ew", padx=32, pady=(0, 24))
        self.summary_frame.grid_remove()
        self._log_shown = False

    # ── Súbory ─────────────────────────────────────────────────────────────────

    def _add_files(self, paths: list[Path]):
        added = 0
        for p in paths:
            if p.suffix.lower() not in SUPPORTED_EXT:
                continue
            if p in self.files:
                continue
            self.files.append(p)
            added += 1
        if added:
            self._refresh_files()

    def _remove_file(self, path: Path):
        self.files = [p for p in self.files if p != path]
        self._refresh_files()

    def _clear_files(self):
        self.files = []
        self._refresh_files()

    def _refresh_files(self):
        for w in self.files_list.winfo_children():
            w.destroy()

        if not self.files:
            self.dropzone.set_compact(False)    # full mode – prázdno, pozvi userov
            empty = ctk.CTkFrame(self.files_list, fg_color="transparent")
            empty.pack(fill="x", expand=True, pady=24)

            ctk.CTkLabel(
                empty,
                text="Zatiaľ nie sú pridané žiadne súbory",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                text_color=TEXT_SECONDARY,
            ).pack(pady=(0, 12))

            tips = [
                "💡  Pridaj pracovný postup a kontrolný plán pre najlepšie výsledky",
                "📑  Podporované sú PDF, DOCX, XLSX, TXT a MD",
                "⌨   Skratka  Ctrl + O  otvorí výber súborov",
            ]
            for tip in tips:
                ctk.CTkLabel(
                    empty, text=tip,
                    font=ctk.CTkFont(family="Segoe UI", size=13),
                    text_color=TEXT_SECONDARY,
                    anchor="w",
                ).pack(anchor="center", pady=2)

            self.files_label.configure(text="Načítané súbory")
            self.clear_btn.grid_remove()
        else:
            self.dropzone.set_compact(True)     # compact mode – súbory už sú
            # Cache veľkostí – jeden stat() per súbor namiesto duplicitných
            # volaní v sum() a v každom FileRow
            sizes_cache: dict = {}
            total_size = 0
            for p in self.files:
                try:
                    if p.exists():
                        sz = p.stat().st_size
                        sizes_cache[p] = sz
                        total_size += sz
                except OSError:
                    sizes_cache[p] = None

            self.files_label.configure(
                text=f"Načítané súbory  ·  {len(self.files)}  ·  {format_file_size(total_size)}"
            )
            self.clear_btn.grid()
            for p in self.files:
                FileRow(
                    self.files_list, p,
                    on_remove=self._remove_file,
                    cached_size=sizes_cache.get(p),
                ).pack(fill="x", padx=6, pady=3)

    # ── Výstupný priečinok ────────────────────────────────────────────────────

    def _pick_output_dir(self):
        folder = filedialog.askdirectory(title="Vyber výstupný priečinok")
        if folder:
            self.out_path_lbl.configure(text=folder)
            self.app.user_state["output_dir"] = folder
            self.app.save_state()

    # ── Spustenie analýzy ─────────────────────────────────────────────────────

    def _start_analysis(self):
        if self.app.is_running:
            return
        if not self.files:
            self._set_status("Pridaj aspoň jeden vstupný dokument.", warn=True)
            return

        # ── Preflight dialog (cena + kvalita + voľba legiend) ─────────────────
        # Dialog sa otvorí asynchrónne – analýza obsahu beží v jeho threade,
        # takže main UI sa neblokuje. Po potvrdení používateľom pokračujeme.
        try:
            current_model = self.app.user_state.get("model") or CLAUDE_MODEL
            dialog = PreflightDialog(
                parent=self.winfo_toplevel(),
                file_paths=self.files,
                model=current_model,
            )
            preflight_result = dialog.show_modal()
        except Exception as e:
            self._set_status(f"Chyba pri otváraní dialógu: {e}", warn=True)
            return

        # Užívateľ zrušil dialóg – nepokračuj
        if preflight_result is None:
            return

        include_legends = preflight_result.get("include_legends", True)
        estimate        = preflight_result.get("estimate")

        output_dir = self.out_path_lbl.cget("text").strip() or OUTPUT_DIR

        # Stage files do dočasného priečinka
        staging = Path(tempfile.mkdtemp(prefix="fmea_input_"))
        try:
            for p in self.files:
                shutil.copy(p, staging / p.name)
        except Exception as e:
            self._set_status(f"Chyba pri kopírovaní súborov: {e}", warn=True)
            shutil.rmtree(staging, ignore_errors=True)
            return

        # UI: prepnúť do running stavu
        self.app.is_running    = True
        self.app.last_output   = None
        self._start_time       = datetime.now()
        self._set_button_state("running")
        self._show_progress()
        self._reset_progress()
        self._append_log(f"=== Spúšťam analýzu – {datetime.now().strftime('%H:%M:%S')} ===")
        self._append_log(f"Vstupné súbory: {len(self.files)}")
        if estimate is not None:
            self._append_log(
                f"Odhadovaná cena: ${estimate.cost_total_usd:.2f} "
                f"(≈ {estimate.cost_total_eur:.2f} €)"
            )
        self._append_log(
            f"Legendy v Exceli: {'áno' if include_legends else 'nie'}"
        )

        threading.Thread(
            target=self._worker, args=(staging, output_dir, include_legends),
            daemon=True,
        ).start()

    def _worker(self, staging: Path, output_dir: str, include_legends: bool = True):
        try:
            # Override modelu a paralelizmu zo Settings (ak boli zmenené)
            model_override = self.app.user_state.get("model")
            if model_override == CLAUDE_MODEL:   # nie je override, default
                model_override = None

            parallel_steps = self.app.user_state.get("parallel_steps")

            result = run_fmea_pipeline(
                raw_data_dir    = str(staging),
                output_dir      = output_dir,
                status_callback = lambda m: self.after(0, self._on_status, m),
                model_override  = model_override,
                parallel_steps  = parallel_steps,
                include_legends = include_legends,
            )
            self.after(0, self._on_success, result)
        except Exception as e:
            self.after(0, self._on_error, str(e))
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _on_status(self, msg: str):
        self._append_log(msg)
        self._set_status_pill(
            icon="●",
            icon_color=(COLOR_IDLE, "#60a5fa"),
            text=msg,
            text_color=("gray25", "gray80"),
            bg=("#eff6ff", "#172554"),
        )
        pct = detect_pct_from_message(msg)
        if pct is not None:
            self._set_pct(pct)

    def _on_success(self, result: dict):
        self.app.is_running  = False
        self.app.last_output = result.get("output_file")
        self._set_pct(100)
        self._append_log(f"=== HOTOVO – {datetime.now().strftime('%H:%M:%S')} ===")

        # zápis do histórie
        try:
            duration = (datetime.now() - self._start_time).total_seconds()
        except Exception:
            duration = 0
        process_name = result.get("metadata", {}).get("nazov_procesu", "Proces")
        stats        = result.get("stats", {})

        # Reálne použitý model (z user_state, override ak bol)
        used_model = self.app.user_state.get("model", CLAUDE_MODEL)

        run_record = {
            "timestamp":      datetime.now().isoformat(timespec="seconds"),
            "process_name":   process_name,
            "item_count":     len(result.get("items", [])),
            "document_count": stats.get("documents_count", 0),
            "output_file":    result.get("output_file"),
            "log_file":       self._find_latest_log(),
            "duration_sec":   round(duration, 1),
            "model":          used_model,
            "status":         "success",
        }
        self.app.history.setdefault("runs", []).insert(0, run_record)
        self.app.history["runs"] = self.app.history["runs"][:50]
        save_history(self.app.history)
        if self.app.history_view:
            self.app.history_view.refresh()
        self.app.refresh_sidebar()

        # Schovaj progress a start button, ukáž summary kartu
        self.progress_frame.grid_remove()
        self.start_btn.grid_remove()
        self.summary_frame.populate(
            process_name   = process_name,
            item_count     = stats.get("items_after_validation", 0),
            document_count = stats.get("documents_count", 0),
            duration_sec   = duration,
            model          = used_model,
        )
        self.summary_frame.grid()

        # Update status baru dole + toast notifikácia
        if self.app.status_bar:
            self.app.status_bar.refresh()
        Toast.show(
            self.app,
            f"Analýza dokončená · {stats.get('items_after_validation', 0)} položiek",
            kind="success",
        )

    def _on_error(self, err: str):
        self.app.is_running = False
        self._set_button_state("error")

        # Preložiť bežné technické chyby na user-friendly hlásenia
        friendly_msg, toast_msg = self._humanize_error(err)

        self._set_status_pill(
            icon="✕",
            icon_color="white",
            text=friendly_msg,
            text_color="white",
            bg=COLOR_ERROR,
        )
        self._append_log(f"!!! CHYBA: {err}")
        Toast.show(
            self.app,
            toast_msg,
            kind="error", duration_ms=6000,
        )

    def _humanize_error(self, err: str) -> tuple[str, str]:
        """
        Preloží bežné technické chyby na priateľské slovenské hlásenia.
        Vracia (status_pill_text, toast_text) – toast môže byť stručnejší.
        """
        err_low = err.lower()

        # Permission denied – Excel súbor je otvorený alebo OneDrive ho drží
        if "permission denied" in err_low or "errno 13" in err_low:
            return (
                "Excel súbor sa nedá prepísať – je otvorený alebo zamknutý. "
                "Zavri Excel / OneDrive sync a skús znova.",
                "Výstupný Excel je otvorený. Zavri ho a skús znova.",
            )

        # File not found / cesta neexistuje
        if "no such file" in err_low or "file not found" in err_low or "errno 2" in err_low:
            return (
                "Vstupný súbor alebo priečinok neexistuje. "
                "Skontroluj cesty v Nastaveniach.",
                "Súbor alebo priečinok neexistuje.",
            )

        # API kľúč chýba alebo je neplatný
        if "api key" in err_low or "anthropic_api_key" in err_low or "authentication" in err_low:
            return (
                "Problém s API kľúčom Anthropic. "
                "Skontroluj ANTHROPIC_API_KEY v .env súbore.",
                "Chyba API kľúča – skontroluj .env súbor.",
            )

        # Rate limit / overloaded
        if "rate limit" in err_low or "429" in err_low or "overloaded" in err_low:
            return (
                "Anthropic API je preťažené alebo si prekročil rate limit. "
                "Počkaj chvíľu a skús znova.",
                "API je preťažené. Skús o chvíľu znova.",
            )

        # Sieťová chyba
        if "connection" in err_low or "network" in err_low or "timeout" in err_low:
            return (
                "Problém s pripojením na Anthropic API. "
                "Skontroluj internet a skús znova.",
                "Problém so sieťou. Skontroluj pripojenie.",
            )

        # Žiadne dokumenty
        if "žiadne vstupné dokumenty" in err_low or "neboli nájdené" in err_low:
            return (
                "Neboli nájdené žiadne vstupné dokumenty. "
                "Pridaj aspoň jeden PDF, DOCX, XLSX alebo TXT.",
                "Pridaj aspoň jeden vstupný dokument.",
            )

        # Fallback – orezať veľmi dlhé chyby
        short = err if len(err) < 140 else err[:137] + "…"
        return (f"Chyba: {short}", f"Analýza zlyhala: {err[:80]}")

    def _find_latest_log(self):
        try:
            logs = sorted(
                Path("data/logs").glob("log_*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            return str(logs[0]) if logs else None
        except Exception:
            return None

    # ── Progress UI helpers ───────────────────────────────────────────────────

    def _show_progress(self):
        self.progress_frame.grid()

    def _reset_progress(self):
        self.stepper.reset()
        self.progress_bar.set(0)
        self.progress_bar.configure(progress_color=COLOR_IDLE)
        self.pct_label.configure(text="0 %", text_color=TEXT_PRIMARY)
        self._set_status_pill(
            icon="●",
            icon_color=(COLOR_IDLE, "#60a5fa"),
            text="Spúšťam…",
            text_color=TEXT_SECONDARY,
            bg=BG_CARD_HI,
        )
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")

    def _set_pct(self, pct: int):
        pct = max(0, min(100, pct))
        self.progress_bar.set(pct / 100)
        self.pct_label.configure(text=f"{pct} %")
        self.stepper.set_progress(pct)
        if pct == 100:
            self.progress_bar.configure(progress_color=COLOR_SUCCESS)
            self.pct_label.configure(text_color=COLOR_SUCCESS)
        else:
            self.progress_bar.configure(progress_color=COLOR_IDLE)

    def _set_status_pill(self, icon: str, icon_color, text: str, text_color, bg):
        """Nastaví ikonu, text a pozadie status pillu."""
        self.status_icon.configure(text=icon, text_color=icon_color)
        self.status_label.configure(text=text, text_color=text_color)
        self.status_container.configure(fg_color=bg)

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}]  {msg}\n"
        self.log_view.configure(state="normal")
        self.log_view.insert("end", line)
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def _toggle_log(self):
        if self._log_shown:
            self.log_view.grid_remove()
            self.log_toggle.configure(text="▼  Zobraziť log")
        else:
            self.log_view.grid()
            self.log_toggle.configure(text="▲  Skryť log")
        self._log_shown = not self._log_shown

    def _set_status(self, msg: str, warn: bool = False):
        self._show_progress()
        if warn:
            self._set_status_pill(
                icon="⚠",
                icon_color="white",
                text=msg,
                text_color="white",
                bg=COLOR_WARN,
            )
        else:
            self._set_status_pill(
                icon="●",
                icon_color=("gray55", "gray55"),
                text=msg,
                text_color=TEXT_SECONDARY,
                bg=BG_CARD_HI,
            )

    # ── Stavy tlačidla ────────────────────────────────────────────────────────

    def _set_button_state(self, state: str):
        if state == "idle":
            self.start_btn.configure(
                text="▶  Spustiť analýzu",
                fg_color=COLOR_IDLE,
                hover_color=COLOR_IDLE_HOVER,
                state="normal",
                command=self._start_analysis,
            )
        elif state == "running":
            self.start_btn.configure(
                text="⏳  Prebieha analýza…",
                fg_color=("gray60", "gray40"),
                hover_color=("gray60", "gray40"),
                state="disabled",
            )
        elif state == "error":
            self.start_btn.configure(
                text="↻  Skúsiť znova",
                fg_color=COLOR_ERROR,
                hover_color=COLOR_ERROR_HOVER,
                state="normal",
                command=self._new_analysis,
            )

    def _open_result(self):
        """Otvorí vygenerovaný Excel natívnou aplikáciou OS."""
        if self.app.last_output:
            open_path_in_os(self.app.last_output)

    def _open_result_folder(self):
        """Otvorí priečinok s vygenerovaným Excelom."""
        if self.app.last_output:
            open_path_in_os(Path(self.app.last_output).parent)

    def _new_analysis(self):
        """Reset do východzieho stavu pripravený na ďalšiu analýzu."""
        self.summary_frame.grid_remove()
        self.progress_frame.grid_remove()
        self._clear_files()
        self._reset_progress()
        self._set_button_state("idle")
        self.start_btn.grid()   # znova zobraz primárne tlačidlo

    def _reset_to_idle(self):
        """Backward-compat ešte pre error state; presmeruje na _new_analysis."""
        self._new_analysis()


class HistoryView(ctk.CTkFrame):
    """Zoznam dokončených analýz so search, filter chip-mi a skupinovaním podľa dňa."""

    FILTER_OPTIONS = ("Všetko", "Dnes", "Tento týždeň", "Tento mesiac")

    def __init__(self, parent, app: "FmeaStudio"):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._search_query = ""
        self._active_filter = "Všetko"

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)   # scrollable area expands

        # ── Header (titulok + Vyčistiť všetko) ───────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 12))
        header.grid_columnconfigure(0, weight=1)

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_block, text="História analýz",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Zoznam dokončených FMEA runov",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        self.clear_all_btn = ctk.CTkButton(
            header, text="🗑  Vyčistiť históriu",
            height=38, corner_radius=8, width=190,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"),
            text_color=("gray35", "gray70"),
            hover_color=("#fee2e2", "#7f1d1d"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self._clear_history,
        )
        self.clear_all_btn.grid(row=0, column=1, sticky="e")

        # ── Toolbar: search + filter chips ────────────────────────────────────
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 14))
        toolbar.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            toolbar, height=40, corner_radius=8,
            placeholder_text="🔍   Hľadať podľa názvu procesu…",
            font=ctk.CTkFont(family="Segoe UI", size=14),
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.search_entry.bind("<KeyRelease>", self._on_search)

        # Filter chips
        chips = ctk.CTkFrame(toolbar, fg_color="transparent")
        chips.grid(row=0, column=1, sticky="e")

        self._chip_buttons = {}
        for opt in self.FILTER_OPTIONS:
            btn = ctk.CTkButton(
                chips, text=opt,
                height=32, corner_radius=16, width=0,
                fg_color="transparent", border_width=1,
                border_color=("gray75", "gray30"),
                text_color=TEXT_SECONDARY,
                hover_color=BORDER_SOFT,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                command=lambda o=opt: self._set_filter(o),
            )
            btn.pack(side="left", padx=3, ipadx=8)
            self._chip_buttons[opt] = btn

        self._apply_chip_styles()

        # ── Scrollovateľný zoznam ────────────────────────────────────────────
        self.scrollable = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
        )
        self.scrollable.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self.scrollable.grid_columnconfigure(0, weight=1)

        self.refresh()

    # ── Filter / Search interakcie ────────────────────────────────────────────

    def _on_search(self, _event=None):
        self._search_query = self.search_entry.get().strip().lower()
        self.refresh()

    def _set_filter(self, name: str):
        self._active_filter = name
        self._apply_chip_styles()
        self.refresh()

    def _apply_chip_styles(self):
        for opt, btn in self._chip_buttons.items():
            if opt == self._active_filter:
                btn.configure(
                    fg_color=COLOR_IDLE,
                    border_color=COLOR_IDLE,
                    text_color="white",
                    hover_color=COLOR_IDLE_HOVER,
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    border_color=("gray75", "gray30"),
                    text_color=TEXT_SECONDARY,
                    hover_color=BORDER_SOFT,
                )

    def _filter_matches(self, run: dict) -> bool:
        # Search
        if self._search_query:
            name = str(run.get("process_name", "")).lower()
            if self._search_query not in name:
                return False

        # Time filter
        if self._active_filter == "Všetko":
            return True
        try:
            ts = datetime.fromisoformat(run.get("timestamp", ""))
        except Exception:
            return self._active_filter == "Všetko"

        now = datetime.now()
        if self._active_filter == "Dnes":
            return ts.date() == now.date()
        if self._active_filter == "Tento týždeň":
            return (now - ts).days < 7
        if self._active_filter == "Tento mesiac":
            return ts.year == now.year and ts.month == now.month
        return True

    # ── Vyčistenie histórie ───────────────────────────────────────────────────

    def _clear_history(self):
        from tkinter import messagebox
        runs = self.app.history.get("runs", [])
        if not runs:
            return
        if not messagebox.askyesno(
            "Vyčistiť históriu",
            f"Naozaj chceš vymazať všetkých {len(runs)} záznamov z histórie?\n\n"
            "Vygenerované Excel súbory sa NEZMAŽÚ – iba sa vyčistí zoznam.",
            parent=self,
        ):
            return
        self.app.history["runs"] = []
        save_history(self.app.history)
        self.refresh()
        self.app.refresh_sidebar()
        if self.app.status_bar:
            self.app.status_bar.refresh()
        Toast.show(self.app, "História vyčistená", kind="info")

    # ── Render ────────────────────────────────────────────────────────────────

    def refresh(self):
        for w in self.scrollable.winfo_children():
            w.destroy()

        runs = self.app.history.get("runs", [])

        # Empty state #1: žiadne runy vôbec
        if not runs:
            self._render_empty_state(onboarding=True)
            self.clear_all_btn.configure(state="disabled")
            return
        else:
            self.clear_all_btn.configure(state="normal")

        filtered = [r for r in runs if self._filter_matches(r)]

        # Empty state #2: filter / search nič nenašli
        if not filtered:
            self._render_empty_state(onboarding=False)
            return

        # Skupinovanie podľa dňa
        groups = self._group_by_day(filtered)
        row_idx = 0
        for group_label, group_runs in groups:
            # Header skupiny
            grp_lbl = ctk.CTkLabel(
                self.scrollable, text=group_label.upper(),
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=TEXT_SECONDARY,
                anchor="w",
            )
            grp_lbl.grid(
                row=row_idx, column=0, sticky="w",
                padx=14, pady=(14 if row_idx > 0 else 4, 6),
            )
            row_idx += 1

            for run in group_runs:
                card = RunCard(self.scrollable, run)
                card.grid(row=row_idx, column=0, sticky="ew", padx=8, pady=5)
                row_idx += 1

    def _group_by_day(self, runs: list[dict]) -> list[tuple[str, list[dict]]]:
        """Vráti zoznam (label, [runs]) skupín v poradí Dnes → Včera → … → Staršie."""
        now = datetime.now()
        today, yesterday, week, month, older = [], [], [], [], []

        for run in runs:
            try:
                ts = datetime.fromisoformat(run.get("timestamp", ""))
            except Exception:
                older.append(run)
                continue
            delta = now - ts
            if ts.date() == now.date():
                today.append(run)
            elif (now.date() - ts.date()).days == 1:
                yesterday.append(run)
            elif delta.days < 7:
                week.append(run)
            elif delta.days < 30:
                month.append(run)
            else:
                older.append(run)

        groups = []
        if today:     groups.append(("Dnes", today))
        if yesterday: groups.append(("Včera", yesterday))
        if week:      groups.append(("Tento týždeň", week))
        if month:     groups.append(("Tento mesiac", month))
        if older:     groups.append(("Staršie", older))
        return groups

    def _render_empty_state(self, onboarding: bool):
        wrap = ctk.CTkFrame(self.scrollable, fg_color="transparent")
        wrap.grid(row=0, column=0, pady=80, padx=40, sticky="ew")
        wrap.grid_columnconfigure(0, weight=1)

        if onboarding:
            ctk.CTkLabel(
                wrap, text="📜",
                font=ctk.CTkFont(family="Segoe UI Emoji", size=60),
            ).pack(pady=(0, 12))
            ctk.CTkLabel(
                wrap, text="Tu sa zobrazí história tvojich analýz",
                font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
                text_color=TEXT_PRIMARY,
            ).pack(pady=(0, 6))
            ctk.CTkLabel(
                wrap, text="Spusti prvú FMEA analýzu a zaznamenám ti všetky runy tu.",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                text_color=TEXT_SECONDARY,
            ).pack(pady=(0, 18))
            ctk.CTkButton(
                wrap, text="▶  Spustiť prvú analýzu",
                height=48, corner_radius=10, width=280,
                fg_color=COLOR_IDLE, hover_color=COLOR_IDLE_HOVER,
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                command=lambda: self.app.show_view("home"),
            ).pack()
        else:
            ctk.CTkLabel(
                wrap, text="🔍",
                font=ctk.CTkFont(family="Segoe UI Emoji", size=48),
            ).pack(pady=(0, 8))
            ctk.CTkLabel(
                wrap, text="Žiadne runy nezodpovedajú filtru",
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color=("gray35", "gray70"),
            ).pack(pady=(0, 4))
            ctk.CTkLabel(
                wrap, text="Skús zmeniť filter alebo vymazať vyhľadávací výraz.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_SECONDARY,
            ).pack()


class SettingsCard(ctk.CTkFrame):
    """
    Pomocná karta pre jednu sekciu v Nastaveniach – header + telo s rows.
    Každý row má label vľavo a control vpravo (classic settings pattern).
    """

    def __init__(self, parent, title: str, subtitle: str = ""):
        super().__init__(
            parent,
            fg_color=BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=BORDER_SOFT,
        )
        self.grid_columnconfigure(0, weight=1)

        # Header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 6))
        head.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            head, text=title,
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        if subtitle:
            ctk.CTkLabel(
                head, text=subtitle,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=TEXT_SECONDARY,
                anchor="w",
            ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Tenký separator
        ctk.CTkFrame(
            self, height=1, fg_color=BORDER_SOFT,
        ).grid(row=1, column=0, sticky="ew", padx=22, pady=(8, 0))

        # Body container – rows sa pridávajú cez add_row()
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=2, column=0, sticky="ew", padx=22, pady=(4, 16))
        self.body.grid_columnconfigure(0, weight=1)
        self._next_row = 0

    def add_row(self, label: str, control, description: str = ""):
        """Pridá label + control. description je jemný text pod labelom."""
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.grid(row=self._next_row, column=0, sticky="ew", pady=8)
        row.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            left, text=label,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")

        if description:
            ctk.CTkLabel(
                left, text=description,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_SECONDARY,
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        # Control vpravo
        control.grid(in_=row, row=0, column=1, sticky="e", padx=(16, 0))
        self._next_row += 1

    def add_custom_row(self, widget):
        """Pridá widget na plnú šírku (napr. pre tlačidlá pod sebou)."""
        widget.grid(in_=self.body, row=self._next_row, column=0, sticky="ew", pady=6)
        self._next_row += 1


# Katalóg dostupných Claude modelov s metadátami pre dropdown
CLAUDE_MODELS = [
    {
        "id": "claude-opus-4-7",
        "label": "Opus 4.7",
        "tagline": "Frontier intelligence · $5 / $25 per 1M tokens",
    },
    {
        "id": "claude-opus-4-6",
        "label": "Opus 4.6",
        "tagline": "Predošlý flagship · $5 / $25 per 1M tokens",
    },
    {
        "id": "claude-sonnet-4-6",
        "label": "Sonnet 4.6",
        "tagline": "Vyvážený výkon/cena · $3 / $15 per 1M tokens",
    },
    {
        "id": "claude-sonnet-4-5",
        "label": "Sonnet 4.5",
        "tagline": "Stabilný default · $3 / $15 per 1M tokens",
    },
    {
        "id": "claude-haiku-4-5",
        "label": "Haiku 4.5",
        "tagline": "Najrýchlejší / najlacnejší · $1 / $5 per 1M tokens",
    },
]


class SettingsView(ctk.CTkFrame):
    """Nastavenia aplikácie – karty so settings pattern (label vľavo, control vpravo)."""

    def __init__(self, parent, app: "FmeaStudio"):
        super().__init__(parent, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 16))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="Nastavenia",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header, text="Konfigurácia aplikácie a AI modelu",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ── Scrollable obsah (karty pod sebou) ───────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
        scroll.grid_columnconfigure(0, weight=1)

        # ── Karta: Vzhľad ────────────────────────────────────────────────────
        appearance_card = SettingsCard(
            scroll,
            title="Vzhľad",
            subtitle="Režim farieb a rozhranie aplikácie",
        )
        appearance_card.grid(row=0, column=0, sticky="ew", padx=8, pady=6)

        self.theme_switch = ctk.CTkSegmentedButton(
            appearance_card.body,
            values=["Svetlý", "Tmavý", "Systém"],
            command=self._change_theme,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            width=260,
        )
        current = ctk.get_appearance_mode()
        self.theme_switch.set(
            {"Dark": "Tmavý", "Light": "Svetlý"}.get(current, "Systém")
        )
        appearance_card.add_row(
            "Režim farieb",
            self.theme_switch,
            description="Svetlý, tmavý alebo podľa systému",
        )

        # ── Karta: AI Model ──────────────────────────────────────────────────
        model_card = SettingsCard(
            scroll,
            title="AI Model",
            subtitle="Model Claude, ktorý generuje FMEA položky",
        )
        model_card.grid(row=1, column=0, sticky="ew", padx=8, pady=6)

        current_label = next(
            (m["label"] for m in CLAUDE_MODELS if m["id"] == CLAUDE_MODEL),
            "Opus 4.7",
        )
        self.model_dropdown = ctk.CTkOptionMenu(
            model_card.body,
            values=[m["label"] for m in CLAUDE_MODELS],
            width=260, height=38, corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self._change_model,
        )
        self.model_dropdown.set(current_label)
        model_card.add_row(
            "Aktívny model",
            self.model_dropdown,
            description="Zmena sa prejaví pri ďalšej analýze",
        )

        # Info o aktuálnom modeli
        self.model_tagline_lbl = ctk.CTkLabel(
            model_card.body,
            text=self._model_tagline(CLAUDE_MODEL),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
            anchor="w",
            justify="left",
        )
        model_card.add_custom_row(self.model_tagline_lbl)

        info_box = ctk.CTkFrame(
            model_card.body,
            fg_color=("#eff6ff", "#172554"),
            corner_radius=8,
        )
        ctk.CTkLabel(
            info_box,
            text="ℹ  Zmena sa uloží do session. Pre trvalú zmenu nastav premennú "
                 "CLAUDE_MODEL v .env súbore.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=(COLOR_IDLE, "#93c5fd"),
            anchor="w", justify="left",
            wraplength=540,
        ).pack(anchor="w", padx=12, pady=10)
        model_card.add_custom_row(info_box)

        # ── Karta: Výkon ─────────────────────────────────────────────────────
        perf_card = SettingsCard(
            scroll,
            title="Výkon",
            subtitle="Nastavenia paralelizácie a výkonu",
        )
        perf_card.grid(row=2, column=0, sticky="ew", padx=8, pady=6)

        # Slider + value label v jednom riadku
        slider_row = ctk.CTkFrame(perf_card.body, fg_color="transparent")

        self.parallel_value_lbl = ctk.CTkLabel(
            slider_row,
            text=str(self.app.user_state.get("parallel_steps", MAX_PARALLEL_STEPS)),
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=(COLOR_IDLE, "#93c5fd"),
            width=32,
        )
        self.parallel_value_lbl.pack(side="right", padx=(10, 0))

        self.parallel_slider = ctk.CTkSlider(
            slider_row, from_=1, to=10, number_of_steps=9,
            width=180, height=16,
            command=self._change_parallelism,
        )
        self.parallel_slider.set(
            self.app.user_state.get("parallel_steps", MAX_PARALLEL_STEPS)
        )
        self.parallel_slider.pack(side="right")

        perf_card.add_row(
            "Paralelné kroky",
            slider_row,
            description="Počet krokov spracovaných súčasne (1–10)",
        )

        # ── Karta: Výstup ────────────────────────────────────────────────────
        output_card = SettingsCard(
            scroll,
            title="Výstup",
            subtitle="Kde sa ukladajú vygenerované Excel súbory a logy",
        )
        output_card.grid(row=3, column=0, sticky="ew", padx=8, pady=6)

        output_row = ctk.CTkFrame(output_card.body, fg_color="transparent")

        self.out_path_setting_lbl = ctk.CTkLabel(
            output_row,
            text=self.app.user_state["output_dir"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_PRIMARY,
            cursor="hand2",
        )
        self.out_path_setting_lbl.pack(side="left", padx=(0, 10))
        self.out_path_setting_lbl.bind(
            "<Button-1>",
            lambda e: open_path_in_os(self.out_path_setting_lbl.cget("text")),
        )

        ctk.CTkButton(
            output_row, text="Zmeniť",
            height=30, width=80, corner_radius=8,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"),
            text_color=("gray20", "gray80"),
            hover_color=BORDER_SOFT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self._pick_output_dir,
        ).pack(side="left")

        output_card.add_row("Výstupný priečinok", output_row)

        ctk.CTkButton(
            output_card.body, text="📁  Otvoriť priečinok s logmi",
            height=32, corner_radius=8, anchor="w",
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"),
            text_color=("gray25", "gray80"),
            hover_color=BORDER_SOFT,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self._open_logs_folder,
        ).grid(in_=output_card.body, row=output_card._next_row,
               column=0, sticky="w", pady=(4, 0), ipadx=10)
        output_card._next_row += 1

        # ── Karta: API ───────────────────────────────────────────────────────
        api_card = SettingsCard(
            scroll,
            title="API",
            subtitle="Pripojenie na Anthropic Claude API",
        )
        api_card.grid(row=4, column=0, sticky="ew", padx=8, pady=6)

        api_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
        status_badge = ctk.CTkFrame(
            api_card.body,
            fg_color=(COLOR_SUCCESS if api_ok else COLOR_ERROR),
            corner_radius=12,
            height=26,
        )
        status_badge.pack_propagate(False)

        ctk.CTkLabel(
            status_badge,
            text=("✓  Pripojené" if api_ok else "✕  Nedostupné"),
            text_color="white",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        ).pack(padx=14, pady=2)

        api_card.add_row(
            "ANTHROPIC_API_KEY",
            status_badge,
            description=(
                "Kľúč je načítaný z .env súboru"
                if api_ok else
                "Pridaj ANTHROPIC_API_KEY= do .env súboru v projekte"
            ),
        )

        # ── Karta: Údaje aplikácie ───────────────────────────────────────────
        data_card = SettingsCard(
            scroll,
            title="Údaje aplikácie",
            subtitle="Správa histórie a uložených nastavení",
        )
        data_card.grid(row=5, column=0, sticky="ew", padx=8, pady=6)

        ctk.CTkButton(
            data_card.body, text="🗑  Vyčistiť históriu analýz",
            height=38, corner_radius=8, anchor="w",
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"),
            text_color=("gray35", "gray70"),
            hover_color=("#fee2e2", "#7f1d1d"),
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self._clear_history,
        ).grid(in_=data_card.body, row=data_card._next_row,
               column=0, sticky="ew", pady=4, ipadx=8)
        data_card._next_row += 1

        # ── Karta: O aplikácii ───────────────────────────────────────────────
        about_card = SettingsCard(
            scroll,
            title="O aplikácii",
        )
        about_card.grid(row=6, column=0, sticky="ew", padx=8, pady=(6, 16))

        ctk.CTkLabel(
            about_card.body,
            text=f"{APP_NAME} v{APP_VERSION}",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(in_=about_card.body, row=about_card._next_row, column=0, sticky="w")
        about_card._next_row += 1

        ctk.CTkLabel(
            about_card.body,
            text="AI-asistovaná procesná FMEA pre automotive.\n"
                 "Powered by Claude (Anthropic).",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY,
            anchor="w", justify="left",
        ).grid(in_=about_card.body, row=about_card._next_row, column=0,
               sticky="w", pady=(4, 0))
        about_card._next_row += 1

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _change_theme(self, value: str):
        mapping = {"Svetlý": "light", "Tmavý": "dark", "Systém": "system"}
        mode = mapping.get(value, "system")
        ctk.set_appearance_mode(mode)
        self.app.user_state["theme"] = mode
        self.app.save_state()
        self.app._update_theme_button_label()

    def _model_tagline(self, model_id: str) -> str:
        for m in CLAUDE_MODELS:
            if m["id"] == model_id:
                return m["tagline"]
        return ""

    def _change_model(self, label: str):
        # Nájdi id podľa labelu
        picked = next((m for m in CLAUDE_MODELS if m["label"] == label), None)
        if not picked:
            return
        self.app.user_state["model"] = picked["id"]
        self.app.save_state()
        self.model_tagline_lbl.configure(text=picked["tagline"])

        # Prejdú sa aj behaviorálne zmeny – sidebar/stavová lišta
        if self.app.status_bar:
            self.app.status_bar.refresh()
        Toast.show(
            self.app,
            f"Model zmenený na {label}. Prejaví sa pri ďalšej analýze.",
            kind="info",
        )

    def _change_parallelism(self, value: float):
        n = int(round(value))
        self.parallel_value_lbl.configure(text=str(n))
        self.app.user_state["parallel_steps"] = n
        self.app.save_state()

    def _pick_output_dir(self):
        folder = filedialog.askdirectory(title="Vyber výstupný priečinok")
        if folder:
            self.out_path_setting_lbl.configure(text=folder)
            self.app.user_state["output_dir"] = folder
            self.app.save_state()
            # Sync aj Domov
            if self.app.home_view and hasattr(self.app.home_view, "out_path_lbl"):
                self.app.home_view.out_path_lbl.configure(text=folder)

    def _open_logs_folder(self):
        logs = Path("data/logs")
        logs.mkdir(parents=True, exist_ok=True)
        open_path_in_os(logs)

    def _clear_history(self):
        from tkinter import messagebox
        runs = self.app.history.get("runs", [])
        if not runs:
            Toast.show(self.app, "História je už prázdna", kind="info")
            return
        if not messagebox.askyesno(
            "Vyčistiť históriu",
            f"Naozaj chceš vymazať všetkých {len(runs)} záznamov z histórie?\n\n"
            "Vygenerované Excel súbory sa NEZMAŽÚ – iba sa vyčistí zoznam.",
            parent=self,
        ):
            return
        self.app.history["runs"] = []
        save_history(self.app.history)
        self.app.refresh_sidebar()
        if self.app.history_view:
            self.app.history_view.refresh()
        if self.app.status_bar:
            self.app.status_bar.refresh()
        Toast.show(self.app, "História vyčistená", kind="success")


# ══════════════════════════════════════════════════════════════════════════════
# HLAVNÁ APLIKÁCIA
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# PRÍRUČKA PRE POUŽÍVATEĽA
# ══════════════════════════════════════════════════════════════════════════════

class GuideView(ctk.CTkFrame):
    """Príručka pre používateľa – stručný popis programu, vstupy, postup, výstup."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 16))

        ctk.CTkLabel(
            header, text="Príručka pre používateľa",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header, text="Stručný popis programu PFMEA Tool a postup jeho používania",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        # ── Scrollable obsah ──────────────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER_SOFT,
            scrollbar_button_hover_color=BG_SUBTLE_HI,
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        scroll.grid_columnconfigure(0, weight=1)

        # ── Sekcie ────────────────────────────────────────────────────────────
        self._add_section(
            scroll, row=0,
            icon="🎯",
            title="Čo je PFMEA Tool",
            body=(
                "PFMEA Tool je desktopová aplikácia, ktorá automaticky generuje návrh "
                "procesnej FMEA (Failure Mode and Effects Analysis) z technických dokumentov "
                "pomocou umelej inteligencie. Aplikácia je určená inžinierom kvality, "
                "technológom a tímom pripravujúcim FMEA dokumentáciu vo výrobných procesoch.\n\n"
                "Program neslúži ako náhrada odbornej FMEA analýzy, ale ako asistent, "
                "ktorý urýchľuje tvorbu prvotného návrhu. Finálny dokument musí vždy "
                "schváliť kvalifikovaný tím v súlade s metodikou AIAG/VDA (vydanie 2019) "
                "a normou IEC 60812:2018."
            ),
        )

        self._add_section(
            scroll, row=1,
            icon="📥",
            title="Vhodné vstupné dokumenty",
            body=(
                "Pre dosiahnutie najlepších výsledkov odporúčame použiť kombináciu "
                "nasledujúcich typov dokumentov:\n\n"
                "•  Pracovné postupy a inštrukcie  (Work Instructions)\n"
                "•  Kontrolné plány  (Control Plans)\n"
                "•  Procesné toky  (Process Flow Charts)\n"
                "•  Záznamy o nezhodách  (Non-conformance Records)\n"
                "•  Existujúce FMEA z podobných procesov\n"
                "•  Plány údržby a kalibrácie\n\n"
                "Podporované formáty: PDF, DOCX, XLSX, TXT a MD. Aplikácia spracuje "
                "viacero dokumentov súčasne a relevantný kontext si vyberie automaticky "
                "pre každý krok procesu zvlášť."
            ),
        )

        self._add_section(
            scroll, row=2,
            icon="⚙️",
            title="Ako program funguje",
            body=(
                "Aplikácia spracúva dokumenty v šiestich postupných fázach:\n\n"
                "1.  Načítanie a extrakcia textu zo všetkých vstupných súborov\n"
                "2.  AI inferencia názvu procesu z prvých niekoľko tisíc znakov\n"
                "3.  AI extrakcia jednotlivých krokov procesu\n"
                "4.  AI generovanie FMEA položiek pre každý krok (paralelne)\n"
                "5.  Validácia a deduplikácia vygenerovaných položiek\n"
                "6.  Deterministický výpočet S / O / D, RPN a klasifikácie CC/SC/HI/OS\n\n"
                "Umelá inteligencia generuje výhradne textový obsah (názvy, opisy chýb, "
                "príčin a opatrení). Číselné hodnotenia závažnosti, výskytu a odhalenia "
                "sa počítajú deterministickými pravidlami v Python module, čo zaručuje "
                "reprodukovateľnosť a auditovateľnosť výsledkov."
            ),
        )

        self._add_section(
            scroll, row=3,
            icon="💰",
            title="Dialóg pred spustením analýzy",
            body=(
                "Po kliknutí na tlačidlo „Spustiť analýzu\" sa otvorí dialóg s tromi sekciami:\n\n"
                "•  Indikátor kvality vstupných dokumentov  – skóre 0–100 podľa toho, "
                "aké typy podkladov ste pridali (pracovný postup, kontrolný plán, záznamy o nezhodách)\n"
                "•  Odhad ceny analýzy  – cena v USD a EUR vypočítaná podľa veľkosti "
                "vstupných dokumentov a aktuálnych cien Anthropic API\n"
                "•  Voľba legiend v Exceli  – možnosť vygenerovať Excel s legendami alebo bez nich\n\n"
                "Tento dialóg vám umožní pred spustením skontrolovať, či sú vstupy "
                "dostatočne kvalitné a aké budú približné náklady na beh."
            ),
        )

        self._add_section(
            scroll, row=4,
            icon="📊",
            title="Výsledok – Excel tabuľka",
            body=(
                "Výstupom analýzy je formátovaný Excel súbor (.xlsx) štruktúrovaný "
                "podľa metodiky AIAG/VDA. Obsahuje:\n\n"
                "•  Hlavičku s metadátami procesu (názov, dátum, revízia)\n"
                "•  FMEA tabuľku s hodnotami S / O / D a vypočítaným RPN\n"
                "•  Klasifikáciu špeciálnych charakteristík CC, OS, SC, HI\n"
                "•  Stĺpec Istota AI (%) s farebným rozlíšením spoľahlivosti návrhu\n"
                "•  Podmienené formátovanie RPN  (zelená < 100,  žltá ≥ 100,  červená ≥ 200)\n"
                "•  Päť listov legiend: Význam, Výskyt, Odhalenie, Klasifikácia, Istota AI\n\n"
                "Vygenerovaný súbor možno priamo otvoriť v Microsoft Exceli, upravovať "
                "ho ručne, alebo použiť ako východiskový bod pre tímové schválenie. "
                "Stĺpec Istota AI pomáha odborníkom rýchlo identifikovať položky, "
                "ktoré si vyžadujú dôkladnejšie preverenie pred finálnym schválením."
            ),
        )

        self._add_section(
            scroll, row=5,
            icon="💡",
            title="Tipy pre najlepšie výsledky",
            body=(
                "•  Pridajte viacero rôznych typov dokumentov  – AI lepšie pochopí kontext\n"
                "•  Používajte dokumenty v slovenčine, češtine alebo angličtine\n"
                "•  Skontrolujte stĺpec Istota AI – červené položky vyžadujú manuálne overenie\n"
                "•  Po vygenerovaní FMEA ju vždy nechajte posúdiť kvalifikovaným tímom\n"
                "•  V Nastaveniach môžete upraviť počet paralelne spracovaných krokov\n"
                "•  História runov uchováva odkazy na všetky predchádzajúce výstupy"
            ),
        )

        self._add_section(
            scroll, row=6,
            icon="ℹ️",
            title="Dôležité upozornenie",
            body=(
                "PFMEA Tool je AI-asistovaný nástroj na podporu tvorby FMEA dokumentácie. "
                "Výstup nie je finálnym auditovateľným záznamom a nenahrádza odbornú "
                "expertízu inžinierov kvality. Hodnoty istoty AI sú orientačné – "
                "vyjadrujú mieru opory výstupu vo vstupných dokumentoch, nie absolútnu "
                "správnosť obsahu.\n\n"
                "Finálne hodnoty S, O, D, klasifikácia špeciálnych charakteristík "
                "a odporúčané opatrenia musia byť vždy schválené kvalifikovaným tímom "
                "FMEA podľa platnej metodiky (AIAG/VDA 2019, IEC 60812:2018)."
            ),
        )

    # ── Pomocná metóda na vytvorenie sekcie ──────────────────────────────────
    def _add_section(self, parent, row: int, icon: str, title: str, body: str):
        card = ctk.CTkFrame(
            parent, fg_color=BG_CARD,
            corner_radius=RADIUS_LG, border_width=1,
            border_color=BORDER_SOFT,
        )
        card.grid(row=row, column=0, sticky="ew", padx=8, pady=8)
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 10))

        ctk.CTkLabel(
            head, text=f"{icon}  {title}",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            card, text=body,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_SECONDARY,
            anchor="w", justify="left",
            wraplength=900,
        ).grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 22))


class FmeaStudio(_Root):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1360x900")
        self.minsize(1120, 760)

        # Stav
        self.history      = load_history()
        # POZOR: NEPOUŽÍVAJ self.state – prekryl by vstavanú Tk.state() metódu
        # (scaling_tracker, titlebar color, ikonifikácia okna to volajú).
        self.user_state   = {
            "output_dir":     self.history.get("output_dir", OUTPUT_DIR),
            "theme":          self.history.get("theme", "system"),
            "model":          self.history.get("model", CLAUDE_MODEL),
            "parallel_steps": self.history.get("parallel_steps", MAX_PARALLEL_STEPS),
        }
        self.is_running   = False
        self.last_output  = None
        self.history_view = None
        self.status_bar   = None

        # Téma
        ctk.set_appearance_mode(self.user_state["theme"])
        ctk.set_default_color_theme("blue")

        # Hlavné pozadie (content area) – jemnejšie ako čistá čierna/biela
        self.configure(fg_color=BG_APP)

        # Layout: row 0 = sidebar | main ; row 1 = status bar (full width)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()
        self._build_status_bar()
        self._bind_shortcuts()
        self._set_window_icon()

        self.show_view("home")

    def _build_status_bar(self):
        """Tenký pásik dole – API status, model, posledný run, verzia."""
        self.status_bar = StatusBar(self, self)
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")

    def _set_window_icon(self):
        """Pokúsi sa nastaviť ikonu okna – modré 'F' logo. Bez ikony sa nič nestane."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import tempfile

            size = 64
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            # Modrý rounded štvorec
            draw.rounded_rectangle(
                [2, 2, size - 2, size - 2], radius=12,
                fill=(59, 130, 246, 255),   # COLOR_IDLE
            )
            # "F" – použi default font, ak Segoe UI Bold nenájde
            try:
                font = ImageFont.truetype("segoeuib.ttf", 38)
            except Exception:
                font = ImageFont.load_default()
            # Centrovanie textu
            bbox = draw.textbbox((0, 0), "F", font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text(
                ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - 2),
                "F", font=font, fill="white",
            )

            tmp = Path(tempfile.gettempdir()) / "fmea_studio_icon.png"
            img.save(tmp)

            from tkinter import PhotoImage
            icon = PhotoImage(file=str(tmp))
            self.iconphoto(True, icon)
            self._icon_ref = icon   # pridržať referenciu aby GC icon nezobral
        except Exception as e:
            print(f"Nastavenie ikony okna zlyhalo: {e}")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        side = ctk.CTkFrame(
            self, width=260, corner_radius=0,
            fg_color=BG_SIDEBAR,
        )
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_rowconfigure(4, weight=1)   # stats karta / empty space expands

        # Subtílny pravý border pre oddelenie sidebar vs. content
        border = ctk.CTkFrame(
            self, width=1, corner_radius=0,
            fg_color=BORDER_SOFT,
        )
        border.grid(row=0, column=0, sticky="nse")
        border.grid_propagate(False)

        # ── Brand: typografické logo ──────────────────────────────────────────
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 8))

        # Logo s tieňom (efekt dosiahnutý cez vrstvený frame)
        logo_wrap = ctk.CTkFrame(brand, fg_color="transparent", width=46, height=46)
        logo_wrap.grid(row=0, column=0, padx=(0, 14), rowspan=2)
        logo_wrap.grid_propagate(False)

        logo = ctk.CTkFrame(
            logo_wrap, width=44, height=44,
            corner_radius=11, fg_color=COLOR_IDLE,
            border_width=1, border_color=COLOR_BRAND_MUTED,
        )
        logo.place(relx=0.5, rely=0.5, anchor="center")
        logo.grid_propagate(False)
        ctk.CTkLabel(
            logo, text="F", text_color="white",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            brand, text=APP_NAME,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            brand, text=f"v{APP_VERSION}  ·  Claude",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_MUTED,
            anchor="w",
        ).grid(row=1, column=1, sticky="w")

        # ── Separator ─────────────────────────────────────────────────────────
        ctk.CTkFrame(
            side, height=1, fg_color=BORDER_SOFT,
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(20, 12))

        # ── Navigácia ─────────────────────────────────────────────────────────
        self.nav_buttons = {}
        self._nav_base_labels = {
            "home":     "🏠   Domov",
            "history":  "📜   História",
            "settings": "⚙️   Nastavenia",
            "guide":    "📖   Príručka",
        }
        nav_frame = ctk.CTkFrame(side, fg_color="transparent")
        nav_frame.grid(row=2, column=0, sticky="ew", padx=12)

        for key, label in self._nav_base_labels.items():
            btn = ctk.CTkButton(
                nav_frame, text=label,
                height=44, corner_radius=RADIUS_MD, anchor="w",
                fg_color="transparent",
                text_color=TEXT_SECONDARY,
                hover_color=BG_SUBTLE_HI,
                font=ctk.CTkFont(family="Segoe UI", size=14),
                command=lambda k=key: self.show_view(k),
            )
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn

        # ── Stats mini-karta ──────────────────────────────────────────────────
        stats_card = ctk.CTkFrame(
            side, fg_color=BG_CARD,
            corner_radius=RADIUS_LG, border_width=1,
            border_color=BORDER_SOFT,
            cursor="hand2",
        )
        stats_card.grid(row=3, column=0, sticky="ew", padx=18, pady=(22, 0))
        self._stats_card = stats_card

        # Hover state – jemné zvýraznenie že karta je klikateľná
        def _stats_enter(_e):
            stats_card.configure(border_color=(COLOR_IDLE, "#60a5fa"))
        def _stats_leave(_e):
            stats_card.configure(border_color=BORDER_SOFT)
        def _stats_click(_e):
            self.show_view("history")

        top_lbl = ctk.CTkLabel(
            stats_card, text="CELKOM ANALÝZ",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
            cursor="hand2",
        )
        top_lbl.pack(anchor="w", padx=16, pady=(14, 2))

        self.stats_count_lbl = ctk.CTkLabel(
            stats_card, text="0",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=(COLOR_IDLE, "#93c5fd"),
            anchor="w",
            cursor="hand2",
        )
        self.stats_count_lbl.pack(anchor="w", padx=16, pady=(0, 0))

        self.stats_last_lbl = ctk.CTkLabel(
            stats_card, text="Zatiaľ žiadne runy",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_SECONDARY,
            anchor="w",
            cursor="hand2",
        )
        self.stats_last_lbl.pack(anchor="w", padx=16, pady=(0, 14))

        for w in (stats_card, top_lbl, self.stats_count_lbl, self.stats_last_lbl):
            w.bind("<Enter>",    _stats_enter)
            w.bind("<Leave>",    _stats_leave)
            w.bind("<Button-1>", _stats_click)

        # ── Bottom: theme toggle ──────────────────────────────────────────────
        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 22))

        ctk.CTkFrame(
            bottom, height=1, fg_color=BORDER_SOFT,
        ).pack(fill="x", pady=(0, 14))

        self.theme_btn = ctk.CTkButton(
            bottom, text="☾  Tmavý režim",
            height=38, corner_radius=RADIUS_MD, anchor="w",
            fg_color="transparent",
            text_color=TEXT_SECONDARY,
            hover_color=BG_SUBTLE_HI,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self._toggle_theme,
        )
        self.theme_btn.pack(fill="x")
        self._update_theme_button_label()

        # Naplň štatistiky z histórie
        self.refresh_sidebar()

    def _toggle_theme(self):
        current = ctk.get_appearance_mode()
        new = "Light" if current == "Dark" else "Dark"
        mode = new.lower()
        ctk.set_appearance_mode(mode)
        self.user_state["theme"] = mode
        self.save_state()
        self._update_theme_button_label()

    def _update_theme_button_label(self):
        current = ctk.get_appearance_mode()
        if current == "Dark":
            self.theme_btn.configure(text="☀  Svetlý režim")
        else:
            self.theme_btn.configure(text="☾  Tmavý režim")

    # ── Main area ─────────────────────────────────────────────────────────────

    def _build_main(self):
        self.main_container = ctk.CTkFrame(self, fg_color=("gray98", "gray9"))
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        self.home_view     = HomeView(self.main_container, self)
        self.history_view  = HistoryView(self.main_container, self)
        self.settings_view = SettingsView(self.main_container, self)
        self.guide_view    = GuideView(self.main_container, self)

        self.views = {
            "home":     self.home_view,
            "history":  self.history_view,
            "settings": self.settings_view,
            "guide":    self.guide_view,
        }

        for v in self.views.values():
            v.grid(row=0, column=0, sticky="nsew")
            v.grid_remove()

    def show_view(self, key: str):
        for k, v in self.views.items():
            if k == key:
                v.grid()
            else:
                v.grid_remove()
        # zvýraznenie nav buttonu – aktívna položka má jemnú akcentovú výplň
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(
                    fg_color=BG_SUBTLE,
                    text_color=(COLOR_IDLE, "#93c5fd"),
                    font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=TEXT_SECONDARY,
                    font=ctk.CTkFont(family="Segoe UI", size=14),
                )
        if key == "history" and self.history_view:
            self.history_view.refresh()

    # ── State persistence ─────────────────────────────────────────────────────

    def save_state(self):
        self.history["output_dir"]     = self.user_state.get("output_dir", OUTPUT_DIR)
        self.history["theme"]          = self.user_state.get("theme", "system")
        self.history["model"]          = self.user_state.get("model", CLAUDE_MODEL)
        self.history["parallel_steps"] = self.user_state.get("parallel_steps", MAX_PARALLEL_STEPS)
        save_history(self.history)

    def refresh_sidebar(self):
        """Prekresli stats kartu a badge v nav podľa aktuálnej histórie."""
        runs = self.history.get("runs", [])
        count = len(runs)

        if hasattr(self, "stats_count_lbl"):
            self.stats_count_lbl.configure(text=str(count))
        if hasattr(self, "stats_last_lbl"):
            if count == 0:
                self.stats_last_lbl.configure(text="Zatiaľ žiadne runy")
            else:
                last = runs[0].get("timestamp", "")
                self.stats_last_lbl.configure(
                    text=f"Posledná {format_relative_time(last)}",
                )

        # Badge v nav: pridá " · N" na label História
        hist_btn = self.nav_buttons.get("history")
        if hist_btn:
            base = self._nav_base_labels["history"]
            hist_btn.configure(
                text=f"{base}   ·   {count}" if count > 0 else base,
            )

    def _bind_shortcuts(self):
        """
        Klávesové skratky. Ctrl+O = pridať súbory, Ctrl+Enter = spustiť,
        Ctrl+L = toggle log, Esc = skryť log.
        """
        self.bind("<Control-o>",       lambda e: self._shortcut_open_files())
        self.bind("<Control-O>",       lambda e: self._shortcut_open_files())
        self.bind("<Control-Return>",  lambda e: self._shortcut_start())
        self.bind("<Control-l>",       lambda e: self._shortcut_toggle_log())
        self.bind("<Control-L>",       lambda e: self._shortcut_toggle_log())
        self.bind("<Escape>",          lambda e: self._shortcut_escape())

    def _shortcut_open_files(self):
        if self.home_view and not self.is_running:
            self.show_view("home")
            self.home_view.dropzone._on_click()

    def _shortcut_start(self):
        if self.home_view and not self.is_running:
            self.show_view("home")
            self.home_view._start_analysis()

    def _shortcut_toggle_log(self):
        if self.home_view:
            self.show_view("home")
            self.home_view._toggle_log()

    def _shortcut_escape(self):
        if self.home_view and self.home_view._log_shown:
            self.home_view._toggle_log()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = FmeaStudio()
    app.mainloop()


if __name__ == "__main__":
    main() 