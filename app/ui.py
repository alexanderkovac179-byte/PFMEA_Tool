"""
ui.py – FMEA Studio s drag & drop, zoznamom súborov,
        históriou priečinkov a toast notifikáciami.

Závislosti (voliteľné):
    pip install tkinterdnd2   ← povolí drag & drop
"""

import json
import os
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND = True
except ImportError:
    _DND = False

from app.config import RAW_DATA_DIR, OUTPUT_DIR
from app.pipeline import run_fmea_pipeline

# ── Paleta ─────────────────────────────────────────────────────────────────────
C = {
    "bg":          "#080c14",
    "surface":     "#0e1621",
    "surface2":    "#141e2e",
    "surface3":    "#1a2640",
    "border":      "#1e2d47",
    "accent":      "#2f81f7",
    "accent_dark": "#1f6feb",
    "success":     "#3fb950",
    "success_dim": "#1a3a22",
    "warning":     "#d29922",
    "warning_dim": "#3a2c10",
    "error":       "#f85149",
    "error_dim":   "#3a1a1a",
    "text":        "#e6edf3",
    "text_muted":  "#8b949e",
    "text_dim":    "#3d4d5e",
    "purple":      "#a371f7",
}
FONT = "Segoe UI"
HISTORY_FILE = Path("data/.ui_history.json")
SUPPORTED_EXT = {".pdf", ".docx", ".txt", ".md"}
FILE_ICONS = {".pdf": "📄", ".docx": "📝", ".txt": "📃", ".md": "📃"}
PHASES = [
    ("načítav", 8), ("identifikuj", 15), ("extrahu", 20),
    ("generuj", 55), ("validáci", 72), ("export", 93),
    ("dokončen", 100), ("úspešn", 100),
]


# ── História ───────────────────────────────────────────────────────────────────

def load_history():
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"input_dirs": [], "output_dir": OUTPUT_DIR}


def save_history(data):
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── Widgets ────────────────────────────────────────────────────────────────────

def card(parent, bg=None, border=None, pad=14):
    bg     = bg     or C["surface"]
    border = border or C["border"]
    outer  = tk.Frame(parent, bg=border, padx=1, pady=1)
    inner  = tk.Frame(outer, bg=bg, padx=pad, pady=pad)
    inner.pack(fill="both", expand=True)
    return outer, inner


class HoverButton(tk.Button):
    def __init__(self, master, nbg, hbg, nfg=None, hfg=None, **kwargs):
        nfg = nfg or C["text"]
        hfg = hfg or C["text"]
        kwargs.setdefault("font", (FONT, 10, "bold"))
        super().__init__(master, bg=nbg, fg=nfg,
                         activebackground=hbg, activeforeground=hfg,
                         relief="flat", borderwidth=0, cursor="hand2", **kwargs)
        self._nbg, self._hbg = nbg, hbg
        self.bind("<Enter>", lambda _: self._hover(True))
        self.bind("<Leave>", lambda _: self._hover(False))

    def _hover(self, on):
        if str(self["state"]) != "disabled":
            self.config(bg=self._hbg if on else self._nbg)


class ProgressBar(tk.Frame):
    def __init__(self, parent, height=8, **kw):
        bg = kw.pop("bg", C["surface2"])
        super().__init__(parent, bg=bg, height=height, **kw)
        self.configure(height=height)
        self.propagate(False)
        self._val = 0.0
        self._tgt = 0.0
        self._running = False
        tk.Frame(self, bg=C["surface3"]).place(relx=0, rely=0, relwidth=1, relheight=1)
        self._fill = tk.Frame(self, bg=C["accent"])
        self._fill.place(relx=0, rely=0, relwidth=0, relheight=1)

    def set(self, v):
        self._tgt = max(0.0, min(100.0, v))
        if not self._running:
            self._running = True
            self._tick()

    def reset(self):
        self._val = self._tgt = 0.0
        self._running = False
        self._fill.place(relwidth=0)

    def _tick(self):
        if abs(self._val - self._tgt) < 0.3:
            self._val = self._tgt
            self._running = False
        else:
            self._val += (self._tgt - self._val) * 0.12
            self.after(16, self._tick)
        self._fill.place(relwidth=self._val / 100.0)


class Toast:
    _KINDS = {
        "success": (C["success"],  C["success_dim"], "✔"),
        "error":   (C["error"],    C["error_dim"],   "✖"),
        "warning": (C["warning"],  C["warning_dim"], "⚠"),
        "info":    (C["accent"],   C["surface2"],    "ℹ"),
    }

    @staticmethod
    def show(root, message, kind="info", duration=3500):
        try:
            fg, bg, icon = Toast._KINDS.get(kind, Toast._KINDS["info"])
            win = tk.Toplevel(root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=C["border"])
            f = tk.Frame(win, bg=bg, padx=16, pady=12)
            f.pack(padx=1, pady=1)
            tk.Label(f, text=f"{icon}  {message}",
                     font=(FONT, 10), bg=bg, fg=fg,
                     wraplength=340, justify="left").pack()
            root.update_idletasks()
            rw = root.winfo_width() or 1200
            rh = root.winfo_height() or 840
            rx = root.winfo_x()
            ry = root.winfo_y()
            win.update_idletasks()
            ww = win.winfo_reqwidth()
            wh = win.winfo_reqheight()
            x = rx + rw - ww - 24
            y = ry + rh - wh - 24
            win.geometry(f"+{x}+{y}")
            win.after(duration, lambda: win.destroy() if win.winfo_exists() else None)
        except Exception:
            pass   # toast nikdy nesmie zrútiť aplikáciu


# ── Základná trieda – bezpečný fallback pre DnD ────────────────────────────────

if _DND:
    _Base = TkinterDnD.Tk
else:
    _Base = tk.Tk


# ── Hlavná aplikácia ───────────────────────────────────────────────────────────

class FMEAApp(_Base):
    def __init__(self):
        super().__init__()
        self.title("AI-assisted procesná FMEA")
        self.geometry("1240x900")
        self.minsize(1060, 740)
        self.configure(bg=C["bg"])

        self._history     = load_history()
        self._files       = []          # list[Path]

        self.out_dir_var          = tk.StringVar(value=self._history.get("output_dir", OUTPUT_DIR))
        self.process_name_var     = tk.StringVar(value="—")
        self.docs_count_var       = tk.StringVar(value="—")
        self.steps_count_var      = tk.StringVar(value="—")
        self.items_count_var      = tk.StringVar(value="—")
        self.output_file_var      = tk.StringVar(value="—")
        self.status_var           = tk.StringVar(value="Pripravené na spustenie.")
        self.phase_var            = tk.StringVar(value="Idle")
        self.pct_var              = tk.StringVar(value="")

        self.is_running       = False
        self.last_output_file = None
        self._progress_val    = 0.0

        self._setup_style()
        self._build_ui()

    # ── Style ──────────────────────────────────────────────────────────────────

    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Vertical.TScrollbar",
                    background=C["surface2"], troughcolor=C["surface"],
                    bordercolor=C["surface"], arrowcolor=C["text_muted"])

    # ── Root layout ────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True)
        self._build_sidebar(body)
        self._build_main(body)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        tk.Frame(self, bg="#1a6ef5", height=1).pack(fill="x")
        tk.Frame(self, bg=C["accent"], height=2).pack(fill="x")
        tk.Frame(self, bg="#1f5dc4", height=1).pack(fill="x")

        hdr = tk.Frame(self, bg=C["surface"], padx=28, pady=14)
        hdr.pack(fill="x")

        left = tk.Frame(hdr, bg=C["surface"])
        left.pack(side="left")

        tr = tk.Frame(left, bg=C["surface"])
        tr.pack(anchor="w")
        tk.Label(tr, text="⬡", font=(FONT, 18), bg=C["surface"],
                 fg=C["accent"]).pack(side="left", padx=(0, 8))
        tk.Label(tr, text="FMEA Studio",
                 font=(FONT, 18, "bold"), bg=C["surface"],
                 fg=C["text"]).pack(side="left")
        tk.Label(left,
                 text="AI-assisted procesná analýza poruchových módov a ich následkov",
                 font=(FONT, 9), bg=C["surface"], fg=C["text_muted"]).pack(
                     anchor="w", pady=(3, 0))

        badge = tk.Frame(hdr, bg=C["surface3"], padx=14, pady=6)
        badge.pack(side="right", anchor="center")
        tk.Label(badge, text="● AI Engine aktívny",
                 font=(FONT, 9, "bold"), bg=C["surface3"],
                 fg=C["accent"]).pack()

        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=C["surface"], width=250)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)
        tk.Frame(sb, bg=C["border"], width=1).pack(side="right", fill="y")

        inn = tk.Frame(sb, bg=C["surface"], padx=16, pady=20)
        inn.pack(fill="both", expand=True)

        self.run_btn = HoverButton(
            inn, nbg=C["accent"], hbg=C["accent_dark"],
            text="▶  Spustiť analýzu", command=self.start_analysis,
            font=(FONT, 11, "bold"), padx=0, pady=12)
        self.run_btn.pack(fill="x", pady=(0, 8))

        self.open_btn = HoverButton(
            inn, nbg=C["surface2"], hbg=C["surface3"],
            text="⬡  Otvoriť Excel", command=self.open_output,
            state="disabled", font=(FONT, 10), padx=0, pady=9)
        self.open_btn.pack(fill="x", pady=(0, 6))

        HoverButton(inn, nbg=C["surface"], hbg=C["surface2"],
                    nfg=C["text_muted"],
                    text="✕  Vymazať výpis", command=self.clear_log,
                    font=(FONT, 9), padx=0, pady=8).pack(fill="x")

        tk.Frame(inn, bg=C["border"], height=1).pack(fill="x", pady=16)

        self._lbl(inn, "VÝSTUPNÝ PRIEČINOK")
        self._path_entry(inn, self.out_dir_var, self._pick_out_dir)

        tk.Frame(inn, bg=C["border"], height=1).pack(fill="x", pady=16)

        self._lbl(inn, "FÁZY SPRACOVANIA")
        self._steps_widgets = []
        for label in ["Načítanie dokumentov", "Extrakcia textu",
                      "AI analýza", "Generovanie FMEA", "Validácia", "Excel export"]:
            row = tk.Frame(inn, bg=C["surface"])
            row.pack(fill="x", pady=2)
            dot = tk.Label(row, text="○", font=(FONT, 9),
                           bg=C["surface"], fg=C["text_dim"], width=2)
            dot.pack(side="left")
            lbl = tk.Label(row, text=label, font=(FONT, 9),
                           bg=C["surface"], fg=C["text_dim"], anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            self._steps_widgets.append((dot, lbl))

    def _lbl(self, parent, text):
        tk.Label(parent, text=text, font=(FONT, 7, "bold"),
                 bg=C["surface"], fg=C["text_dim"]).pack(anchor="w", pady=(0, 6))

    def _path_entry(self, parent, var, cmd):
        wrap = tk.Frame(parent, bg=C["border"], padx=1, pady=1)
        wrap.pack(fill="x")
        inn = tk.Frame(wrap, bg=C["surface2"])
        inn.pack(fill="x")
        tk.Entry(inn, textvariable=var, font=("Consolas", 8),
                 bg=C["surface2"], fg=C["text_muted"], relief="flat",
                 insertbackground=C["text"], highlightthickness=0).pack(
                     side="left", fill="x", expand=True, padx=8, ipady=5)
        HoverButton(inn, nbg=C["surface2"], hbg=C["accent"],
                    nfg=C["text_muted"], text="…", command=cmd,
                    font=(FONT, 10, "bold"), padx=10, pady=3).pack(side="right")

    # ── Hlavný obsah ──────────────────────────────────────────────────────────

    def _build_main(self, parent):
        main = tk.Frame(parent, bg=C["bg"])
        main.pack(side="left", fill="both", expand=True, padx=20, pady=16)
        self._build_dropzone(main)
        self._build_progress(main)
        self._build_metrics(main)
        self._build_log(main)

    # ── Drag & Drop zóna ──────────────────────────────────────────────────────

    def _build_dropzone(self, parent):
        outer, c = card(parent, bg=C["surface"], pad=0)
        outer.pack(fill="x", pady=(0, 12))

        # Hlavička
        top = tk.Frame(c, bg=C["surface"], padx=16, pady=10)
        top.pack(fill="x")
        tk.Label(top, text="📂  Vstupné súbory",
                 font=(FONT, 11, "bold"), bg=C["surface"],
                 fg=C["text"]).pack(side="left")

        btn_row = tk.Frame(top, bg=C["surface"])
        btn_row.pack(side="right")
        HoverButton(btn_row, nbg=C["accent"], hbg=C["accent_dark"],
                    text="+ Vybrať súbory", command=self._pick_files,
                    font=(FONT, 9), padx=10, pady=4).pack(side="left", padx=(0, 6))
        HoverButton(btn_row, nbg=C["surface2"], hbg=C["surface3"],
                    nfg=C["text_muted"],
                    text="Vybrať priečinok", command=self._pick_folder,
                    font=(FONT, 9), padx=10, pady=4).pack(side="left")

        # Drop plocha
        self._drop_frame = tk.Frame(
            c, bg=C["surface2"],
            highlightthickness=2,
            highlightbackground=C["border"],
            highlightcolor=C["accent"],
            cursor="hand2")
        self._drop_frame.pack(fill="x", padx=16, pady=(0, 4))

        dnd_hint = (
            "⬇  Pretiahni PDF, DOCX alebo TXT súbory sem"
            if _DND else
            "⬇  Klikni na '+ Vybrať súbory' alebo 'Vybrať priečinok'"
        )
        self._drop_lbl = tk.Label(
            self._drop_frame, text=dnd_hint,
            font=(FONT, 10), bg=C["surface2"],
            fg=C["text_dim"], pady=20, cursor="hand2")
        self._drop_lbl.pack(fill="x")
        self._drop_lbl.bind("<Button-1>", lambda _: self._pick_files())

        # Registrácia DnD
        if _DND:
            for w in (self._drop_frame, self._drop_lbl):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>",      self._on_drop)
                w.dnd_bind("<<DragEnter>>", lambda e: self._set_drop_highlight(True))
                w.dnd_bind("<<DragLeave>>", lambda e: self._set_drop_highlight(False))

        # Zoznam súborov
        self._file_list = tk.Frame(c, bg=C["surface"])
        self._file_list.pack(fill="x", padx=16, pady=(0, 4))

        # Posledné priečinky
        recent = self._history.get("input_dirs", [])
        if recent:
            rec = tk.Frame(c, bg=C["surface"], padx=16, pady=(0, 10))
            rec.pack(fill="x")
            tk.Label(rec, text="Posledné:", font=(FONT, 8),
                     bg=C["surface"], fg=C["text_dim"]).pack(side="left", padx=(0, 8))
            for p in recent[:3]:
                short = ("…/" + Path(p).name) if len(p) > 32 else p
                HoverButton(rec, nbg=C["surface"], hbg=C["surface2"],
                            nfg=C["text_muted"], text=short,
                            command=lambda d=p: self._load_from_dir(d),
                            font=(FONT, 8), padx=6, pady=2).pack(side="left", padx=2)

    def _set_drop_highlight(self, on):
        color = C["accent"] if on else C["border"]
        self._drop_frame.configure(highlightbackground=color)

    def _on_drop(self, event):
        self._set_drop_highlight(False)
        paths = self.tk.splitlist(event.data)
        added = 0
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.suffix.lower() in SUPPORTED_EXT:
                        self._add_file(f); added += 1
            elif p.suffix.lower() in SUPPORTED_EXT:
                self._add_file(p); added += 1
        if added:
            Toast.show(self, f"Pridaných {added} súbor(ov)", "success")
        else:
            Toast.show(self, "Žiadne podporované súbory (.pdf .docx .txt)", "warning")

    def _add_file(self, path):
        if path not in self._files:
            self._files.append(path)
            self._refresh_files()

    def _remove_file(self, path):
        if path in self._files:
            self._files.remove(path)
            self._refresh_files()

    def _refresh_files(self):
        for w in self._file_list.winfo_children():
            w.destroy()

        if not self._files:
            self._drop_lbl.configure(
                text="⬇  Pretiahni PDF, DOCX alebo TXT súbory sem"
                     if _DND else
                     "⬇  Klikni na '+ Vybrať súbory' alebo 'Vybrať priečinok'",
                fg=C["text_dim"])
            return

        self._drop_lbl.configure(
            text=f"✔  {len(self._files)} súbor(ov) pripravených na analýzu",
            fg=C["success"])

        for path in self._files:
            row = tk.Frame(self._file_list, bg=C["surface2"], padx=10, pady=6)
            row.pack(fill="x", pady=2)

            icon = FILE_ICONS.get(path.suffix.lower(), "📄")
            try:
                size_kb = path.stat().st_size // 1024
                size_str = f"{size_kb} KB"
            except Exception:
                size_str = ""

            tk.Label(row, text=icon, font=(FONT, 10),
                     bg=C["surface2"], fg=C["text_muted"]).pack(side="left", padx=(0, 8))
            tk.Label(row, text=path.name, font=(FONT, 9),
                     bg=C["surface2"], fg=C["text"]).pack(side="left")
            tk.Label(row, text=size_str, font=(FONT, 8),
                     bg=C["surface2"], fg=C["text_dim"]).pack(side="left", padx=(8, 0))
            HoverButton(row, nbg=C["surface2"], hbg=C["error_dim"],
                        nfg=C["text_dim"], hfg=C["error"],
                        text="✕", command=lambda p=path: self._remove_file(p),
                        font=(FONT, 9), padx=6, pady=0).pack(side="right")

        # Vymazať všetky
        cl = tk.Frame(self._file_list, bg=C["surface"])
        cl.pack(fill="x", pady=(4, 6))
        HoverButton(cl, nbg=C["surface"], hbg=C["surface2"],
                    nfg=C["text_dim"],
                    text="✕  Odstrániť všetky",
                    command=self._clear_files,
                    font=(FONT, 8), padx=8, pady=3).pack(side="right")

    def _clear_files(self):
        self._files.clear()
        self._refresh_files()

    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Vyber vstupné súbory",
            filetypes=[
                ("Podporované súbory", "*.pdf *.docx *.txt *.md"),
                ("PDF", "*.pdf"), ("Word", "*.docx"),
                ("Text", "*.txt *.md"), ("Všetky", "*.*"),
            ])
        for p in paths:
            self._add_file(Path(p))

    def _pick_folder(self):
        path = filedialog.askdirectory(title="Vyber priečinok so súbormi")
        if path:
            self._load_from_dir(path)

    def _load_from_dir(self, folder):
        added = 0
        for f in Path(folder).rglob("*"):
            if f.suffix.lower() in SUPPORTED_EXT:
                self._add_file(f); added += 1
        dirs = self._history.get("input_dirs", [])
        if folder not in dirs:
            dirs.insert(0, folder)
        self._history["input_dirs"] = dirs[:5]
        save_history(self._history)
        if added:
            Toast.show(self, f"Načítaných {added} súbor(ov)", "success")
        else:
            Toast.show(self, "Priečinok neobsahuje podporované súbory", "warning")

    # ── Progress ──────────────────────────────────────────────────────────────

    def _build_progress(self, parent):
        outer, c = card(parent, bg=C["surface"], pad=20)
        outer.pack(fill="x", pady=(0, 12))

        top = tk.Frame(c, bg=C["surface"])
        top.pack(fill="x")

        left = tk.Frame(top, bg=C["surface"])
        left.pack(side="left", fill="x", expand=True)

        self._phase_badge = tk.Label(
            left, text="  ●  Idle  ",
            font=(FONT, 8, "bold"),
            bg=C["surface3"], fg=C["text_muted"],
            padx=10, pady=4)
        self._phase_badge.pack(side="left")
        tk.Label(left, text="Stav spracovania", font=(FONT, 9),
                 bg=C["surface"], fg=C["text_dim"]).pack(side="left", padx=(10, 0))

        tk.Label(top, textvariable=self.pct_var,
                 font=(FONT, 12, "bold"),
                 bg=C["surface"], fg=C["accent"]).pack(side="right")

        tk.Label(c, textvariable=self.status_var,
                 font=(FONT, 11), bg=C["surface"],
                 fg=C["text"]).pack(anchor="w", pady=(12, 14))

        self._pbar = ProgressBar(c, height=10, bg=C["surface"])
        self._pbar.pack(fill="x")

        step_row = tk.Frame(c, bg=C["surface"])
        step_row.pack(fill="x", pady=(10, 0))
        for lbl in ["Načítanie", "Extrakcia", "AI analýza",
                    "Generovanie", "Validácia", "Export"]:
            col = tk.Frame(step_row, bg=C["surface"])
            col.pack(side="left", expand=True, fill="x")
            tk.Label(col, text="│", font=("Consolas", 7),
                     bg=C["surface"], fg=C["text_dim"]).pack()
            tk.Label(col, text=lbl, font=(FONT, 7),
                     bg=C["surface"], fg=C["text_dim"]).pack()

    # ── Metriky ───────────────────────────────────────────────────────────────

    def _build_metrics(self, parent):
        row = tk.Frame(parent, bg=C["bg"])
        row.pack(fill="x", pady=(0, 12))

        for i, (title, var, fs) in enumerate([
            ("Názov procesu",  self.process_name_var,  14),
            ("Dokumenty",      self.docs_count_var,    10),
            ("Kroky",          self.steps_count_var,   10),
            ("Položky",        self.items_count_var,   10),
        ]):
            outer, c = card(row, bg=C["surface"], pad=16)
            outer.pack(side="left", fill="both",
                       expand=(i == 0),
                       padx=(0, 8) if i < 3 else 0)
            tk.Label(c, text=title, font=(FONT, 8, "bold"),
                     bg=C["surface"], fg=C["text_muted"]).pack(anchor="w")
            tk.Label(c, textvariable=var,
                     font=(FONT, fs, "bold"),
                     bg=C["surface"], fg=C["text"],
                     wraplength=300 if i == 0 else 120,
                     justify="left").pack(anchor="w", pady=(8, 0))

        outer2, c2 = card(parent, bg=C["surface2"], pad=14)
        outer2.pack(fill="x", pady=(0, 12))
        fr = tk.Frame(c2, bg=C["surface2"])
        fr.pack(fill="x")
        tk.Label(fr, text="📄", font=(FONT, 10),
                 bg=C["surface2"], fg=C["text_muted"]).pack(side="left", padx=(0, 8))
        tk.Label(fr, text="Výstupný súbor:", font=(FONT, 9, "bold"),
                 bg=C["surface2"], fg=C["text_muted"]).pack(side="left")
        tk.Label(fr, textvariable=self.output_file_var,
                 font=("Consolas", 9), bg=C["surface2"], fg=C["accent"],
                 wraplength=900, justify="left").pack(side="left", padx=(10, 0))

    # ── Log ───────────────────────────────────────────────────────────────────

    def _build_log(self, parent):
        outer, c = card(parent, bg=C["surface"], pad=16)
        outer.pack(fill="both", expand=True)

        tk.Label(c, text="🖥  Priebeh spracovania",
                 font=(FONT, 10, "bold"), bg=C["surface"],
                 fg=C["text"]).pack(anchor="w", pady=(0, 10))

        border = tk.Frame(c, bg=C["border"], padx=1, pady=1)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg=C["bg"])
        inner.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            inner, wrap="word", height=10,
            font=("Consolas", 10), bg=C["bg"], fg=C["text"],
            relief="flat", borderwidth=0, padx=16, pady=14,
            insertbackground=C["text"],
            selectbackground=C["accent"],
            selectforeground="#ffffff",
            spacing1=3, spacing3=3)
        self.log_text.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(inner, orient="vertical",
                            command=self.log_text.yview, style="Vertical.TScrollbar")
        sb.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=sb.set, state="disabled")

        for tag, fg in [
            ("info",    C["text"]),    ("success", C["success"]),
            ("warning", C["warning"]), ("error",   C["error"]),
            ("accent",  C["accent"]), ("purple",  C["purple"]),
        ]:
            self.log_text.tag_configure(tag, foreground=fg)

    # ── Logika ────────────────────────────────────────────────────────────────

    def _tag(self, msg):
        lo = msg.lower()
        if any(w in lo for w in ("chyba", "error", "failed", "✖")): return "error"
        if any(w in lo for w in ("úspešn", "dokončen", "✔")):        return "success"
        if any(w in lo for w in ("upozornenie", "warning")):          return "warning"
        if any(w in lo for w in ("spúšťam", "⚙", "export")):         return "accent"
        if any(w in lo for w in ("analýz", "extrahu", "generuj")):    return "purple"
        return "info"

    def _update_badge(self):
        phase = self.phase_var.get()
        cfg = {
            "Idle":      (C["text_muted"], C["surface3"]),
            "Running":   (C["accent"],     "#0e2044"),
            "Completed": (C["success"],    C["success_dim"]),
            "Done":      (C["success"],    C["success_dim"]),
            "Error":     (C["error"],      C["error_dim"]),
        }
        fg, bg = cfg.get(phase, (C["text_muted"], C["surface3"]))
        self._phase_badge.config(text=f"  ●  {phase}  ", fg=fg, bg=bg)

    def _update_progress(self, msg):
        lo = msg.lower()
        for kw, pct in PHASES:
            if kw in lo and pct > self._progress_val:
                self._progress_val = pct
                self._pbar.set(pct)
                self.pct_var.set(f"{int(pct)} %")
                self._update_steps(pct)
                break

    def _update_steps(self, pct):
        thresholds = [8, 20, 40, 55, 72, 93]
        for i, (dot, lbl) in enumerate(self._steps_widgets):
            prev = thresholds[i - 1] if i > 0 else 0
            if pct >= thresholds[i]:
                dot.config(text="●", fg=C["success"])
                lbl.config(fg=C["success"])
            elif pct >= prev:
                dot.config(text="◉", fg=C["accent"])
                lbl.config(fg=C["accent"])
            else:
                dot.config(text="○", fg=C["text_dim"])
                lbl.config(fg=C["text_dim"])

    def _reset_steps(self):
        for dot, lbl in self._steps_widgets:
            dot.config(text="○", fg=C["text_dim"])
            lbl.config(fg=C["text_dim"])

    def append_log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n", self._tag(msg))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def set_status(self, msg):
        self.status_var.set(msg)
        self.phase_var.set("Running" if self.is_running else "Done")
        self._update_badge()
        self._update_progress(msg)
        self.append_log(msg)

    def _pick_out_dir(self):
        path = filedialog.askdirectory(title="Vyber výstupný priečinok")
        if path:
            self.out_dir_var.set(path)
            self._history["output_dir"] = path
            save_history(self._history)

    # ── Analýza ───────────────────────────────────────────────────────────────

    def _prepare_input(self):
        """Pripraví vstupný priečinok. Ak sú súbory z rôznych miest, skopíruje ich."""
        parents = {f.parent for f in self._files}
        if len(parents) == 1:
            return str(next(iter(parents)))
        tmp = Path("data/tmp_input")
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        for f in self._files:
            shutil.copy2(f, tmp / f.name)
        return str(tmp)

    def start_analysis(self):
        if self.is_running:
            return
        if not self._files:
            Toast.show(self, "Pretiahni alebo vyber vstupné súbory", "warning")
            return
        out = self.out_dir_var.get().strip()
        if not out:
            Toast.show(self, "Zadaj výstupný priečinok", "warning")
            return

        input_dir = self._prepare_input()

        self.is_running       = True
        self.last_output_file = None
        self._progress_val    = 0.0
        self._pbar.reset()
        self.pct_var.set("0 %")
        self._reset_steps()
        self.open_btn.config(state="disabled", bg=C["surface2"])
        self.run_btn.config(state="disabled", bg=C["accent_dark"])
        self._clear_results()
        self.clear_log()
        self.phase_var.set("Running")
        self._update_badge()
        self.status_var.set("Spúšťam analýzu…")
        self.append_log(f"⚙  Spúšťam analýzu ({len(self._files)} súborov)…")

        threading.Thread(
            target=self._worker, args=(input_dir, out), daemon=True).start()

    def _worker(self, input_dir, output_dir):
        try:
            result = run_fmea_pipeline(
                raw_data_dir=input_dir,
                output_dir=output_dir,
                status_callback=lambda m: self.after(0, self.set_status, m),
            )
            self.after(0, self._on_success, result)
        except Exception as e:
            self.after(0, self._on_error, str(e))

    def _on_success(self, result):
        self.process_name_var.set(result["metadata"]["nazov_procesu"])
        self.docs_count_var.set(str(result["stats"]["documents_count"]))
        self.steps_count_var.set(str(result["stats"]["steps_count"]))
        self.items_count_var.set(str(result["stats"]["items_after_validation"]))
        self.output_file_var.set(result["output_file"])
        self.last_output_file = result["output_file"]
        self.is_running = False
        self.phase_var.set("Completed")
        self._update_badge()
        self.status_var.set("Analýza bola úspešne dokončená.")
        self._pbar.set(100)
        self.pct_var.set("100 %")
        self._update_steps(100)
        self.run_btn.config(state="normal",  bg=C["accent"])
        self.open_btn.config(state="normal", bg=C["surface2"])
        self.append_log("✔  Analýza bola úspešne dokončená.")
        Toast.show(self, "Analýza dokončená! Excel je pripravený.", "success", 5000)

    def _on_error(self, err):
        self.is_running = False
        self.phase_var.set("Error")
        self._update_badge()
        self.status_var.set("Počas spracovania nastala chyba.")
        self.run_btn.config(state="normal",    bg=C["accent"])
        self.open_btn.config(state="disabled", bg=C["surface2"])
        self.append_log(f"✖  Chyba: {err}")
        Toast.show(self, f"Chyba: {err[:80]}", "error", 6000)

    def _clear_results(self):
        for v in (self.process_name_var, self.docs_count_var,
                  self.steps_count_var, self.items_count_var,
                  self.output_file_var):
            v.set("—")

    def open_output(self):
        if not self.last_output_file:
            return
        if not os.path.exists(self.last_output_file):
            Toast.show(self, "Výstupný súbor sa nenašiel.", "warning")
            return
        try:
            os.startfile(self.last_output_file)
        except Exception as e:
            Toast.show(self, f"Súbor sa nepodarilo otvoriť: {e}", "error")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if not _DND:
        print("Tip: pip install tkinterdnd2  →  povolí drag & drop funkciu")
    app = FMEAApp()
    app.mainloop()


if __name__ == "__main__":
    main() 