"""
preflight_dialog.py – modálny dialóg pred spustením FMEA analýzy.

Zobrazuje:
  1. Kvalitný indikátor vstupných dokumentov  (skóre 0–100, odporúčania)
  2. Cenový odhad za beh                       (USD + EUR + počet tokenov)
  3. Voľbu "Generovať legendy v Exceli"        (áno / nie)
  4. Tlačidlá "Spustiť" / "Zrušiť"

Používa rovnaký design system ako zvyšok aplikácie (CTk, design tokens).
"""

from pathlib import Path
import threading
import customtkinter as ctk

from app.cost_estimator import (
    estimate_cost,
    analyze_quality,
    CostEstimate,
    QualityIndicator,
)


# ── Design tokens (musia byť synchronizované s ui.py) ──────────────────────────
BG_APP          = ("#f7f7f9", "#1a1b1e")
BG_CARD         = ("#ffffff", "#27282c")
BG_SUBTLE       = ("#f3f4f6", "#212225")
BG_SUBTLE_HI    = ("#e7e8ec", "#2b2c30")
BORDER_SOFT     = ("#e4e4e7", "#35363b")
TEXT_PRIMARY    = ("#18181b", "#f4f4f5")
TEXT_SECONDARY  = ("#52525b", "#a1a1aa")
TEXT_MUTED      = ("#71717a", "#71717a")
COLOR_IDLE      = "#3b82f6"
COLOR_IDLE_HOVER = "#2563eb"
COLOR_SUCCESS   = "#22c55e"
COLOR_WARN      = "#f59e0b"
COLOR_ERROR     = "#ef4444"
RADIUS_MD       = 10
RADIUS_LG       = 14
FONT_FAMILY     = "Segoe UI"


# ── Tooltip helper ─────────────────────────────────────────────────────────────

class Tooltip:
    """
    Jednoduchý tooltip – zobrazí krátky vysvetľujúci text pri hovere
    nad widget. Používa CTkToplevel pre konzistentný vzhľad.
    """

    _ACTIVE_TOOLTIP = None    # globálne sledovanie aktívneho tooltipu

    def __init__(self, widget, text: str, delay_ms: int = 400, max_width: int = 320):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.max_width = max_width
        self._tip_window = None
        self._after_id = None

        widget.bind("<Enter>", self._schedule_show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule_show(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip_window or not self.text:
            return

        # Schovaj iný aktívny tooltip
        if Tooltip._ACTIVE_TOOLTIP is not None:
            try:
                Tooltip._ACTIVE_TOOLTIP._hide()
            except Exception:
                pass

        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return

        self._tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.configure(fg_color=BG_CARD)

        frame = ctk.CTkFrame(
            tw, fg_color=BG_CARD,
            corner_radius=RADIUS_MD,
            border_width=1, border_color=BORDER_SOFT,
        )
        frame.pack(padx=2, pady=2)

        label = ctk.CTkLabel(
            frame, text=self.text,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=TEXT_PRIMARY,
            wraplength=self.max_width,
            justify="left",
        )
        label.pack(padx=12, pady=(8, 9))

        tw.update_idletasks()
        # Ak by tooltip vyšiel mimo obrazovku – posuň doľava
        screen_w = tw.winfo_screenwidth()
        if x + tw.winfo_width() > screen_w:
            x = screen_w - tw.winfo_width() - 12
        tw.geometry(f"+{x - tw.winfo_width()//2}+{y}")

        Tooltip._ACTIVE_TOOLTIP = self

    def _hide(self, _event=None):
        self._cancel()
        if self._tip_window:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None
        if Tooltip._ACTIVE_TOOLTIP is self:
            Tooltip._ACTIVE_TOOLTIP = None


def add_tooltip(widget, text: str):
    """Pohodlná funkcia: pripojí tooltip k widgetu."""
    Tooltip(widget, text)


# ── Quality bar widget ─────────────────────────────────────────────────────────

class QualityScoreBar(ctk.CTkFrame):
    """Horizontálny pruh skóre 0–100 s farebným odlíšením."""

    def __init__(self, parent, score: int, color: str):
        super().__init__(parent, fg_color="transparent", height=10)
        self._score = score
        self._color = color

        self._track = ctk.CTkFrame(
            self, fg_color=BG_SUBTLE_HI,
            corner_radius=5, height=8,
        )
        self._track.place(relx=0, rely=0.5, relwidth=1, anchor="w")

        self._fill = ctk.CTkFrame(
            self, fg_color=color,
            corner_radius=5, height=8,
        )
        # Šírka pruhu = score / 100 z plochy
        fill_ratio = max(0.02, min(1.0, score / 100))
        self._fill.place(relx=0, rely=0.5, relwidth=fill_ratio, anchor="w")


# ── Hlavný dialóg ──────────────────────────────────────────────────────────────

class PreflightDialog(ctk.CTkToplevel):
    """
    Modálny dialóg pred spustením FMEA analýzy.

    Použitie:
        dialog = PreflightDialog(parent, file_paths, model="claude-opus-4-7")
        result = dialog.show_modal()
        if result is not None:
            # result = {"include_legends": True/False, "estimate": CostEstimate, ...}
            run_analysis(result)
    """

    def __init__(self, parent, file_paths: list, model: str = "claude-opus-4-7"):
        super().__init__(parent)
        self.parent = parent
        self.file_paths = [Path(p) for p in file_paths]
        self.model = model

        # Výsledok dialógu (None = zrušené, dict = potvrdené)
        self._result = None

        # Cena – výpočet je rýchly (len súbory.stat()), pustíme synchrónne
        self.cost: CostEstimate = estimate_cost(self.file_paths, model)

        # Kvalita – pre veľké PDF/DOCX môže trvať niekoľko sekúnd.
        # Najprv okamžite zostavíme placeholder a hneď otvoríme dialóg,
        # samotnú analýzu spustíme v samostatnom threade.
        self.quality: QualityIndicator | None = None
        self._quality_loading = True

        self._configure_window()
        self._build_ui()
        self._setup_modal()

        # Spusti analýzu kvality na pozadí
        threading.Thread(
            target=self._analyze_quality_async,
            daemon=True,
        ).start()

    def _analyze_quality_async(self):
        """Spustí analýzu kvality v samostatnom threade a UI updatne cez .after()."""
        try:
            quality = analyze_quality(self.file_paths)
        except Exception as e:
            quality = None
            print(f"Chyba pri analýze kvality: {e}")

        # Update UI v main threade
        try:
            self.after(0, self._on_quality_ready, quality)
        except Exception:
            pass

    def _on_quality_ready(self, quality):
        """Callback po dokončení analýzy kvality – aktualizuje UI."""
        if quality is None:
            return
        if not self.winfo_exists():
            return

        self.quality = quality
        self._quality_loading = False
        self._update_quality_card()

    # ── Window setup ───────────────────────────────────────────────────────────
    def _configure_window(self):
        self.title("Spustenie analýzy FMEA")
        self.geometry("680x780")
        self.minsize(620, 720)
        self.configure(fg_color=BG_APP)
        self.resizable(True, True)

        # Centruj relatívne k rodičovi
        self.update_idletasks()
        try:
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            x = px + (pw - 680) // 2
            y = py + (ph - 780) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _setup_modal(self):
        """Modálne správanie – blokuje rodičovské okno."""
        self.transient(self.parent)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        # Grab až po vykreslení (inak Tkinter vyhodí výnimku)
        self.after(100, self._safe_grab)

    def _safe_grab(self):
        try:
            self.grab_set()
            self.focus_set()
        except Exception:
            pass

    # ── UI construction ────────────────────────────────────────────────────────
    def _build_ui(self):
        # Scrollable container – pre prípad menších obrazoviek
        outer = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=BORDER_SOFT,
            scrollbar_button_hover_color=BG_SUBTLE_HI,
        )
        outer.pack(fill="both", expand=True, padx=20, pady=(20, 0))

        # ── Header ────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", pady=(0, 18))

        ctk.CTkLabel(
            header, text="Pred spustením analýzy",
            font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text=f"Skontrolujte kvalitu vstupných dát a odhad ceny pre {self.cost.files_count} dokumentov",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        # ── Karta 1: Indikátor kvality ────────────────────────────────────────
        self._build_quality_card(outer)

        # ── Karta 2: Cenový odhad ─────────────────────────────────────────────
        self._build_cost_card(outer)

        # ── Karta 3: Voľba legiend ────────────────────────────────────────────
        self._build_legend_card(outer)

        # ── Tlačidlá ───────────────────────────────────────────────────────────
        self._build_buttons()

    # ── Karta kvality vstupov ──────────────────────────────────────────────────
    def _build_quality_card(self, parent):
        card = self._make_card(parent)
        # Uložíme referenciu, aby sme ju mohli neskôr prebudovať pri loadovaní dát
        self._quality_card = card

        # Hlavička s tooltipom
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(20, 12))

        title = ctk.CTkLabel(
            head, text="📊  Kvalita vstupných dokumentov",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title.pack(side="left")

        info = ctk.CTkLabel(
            head, text="ⓘ", text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            cursor="hand2",
        )
        info.pack(side="left", padx=(8, 0))
        add_tooltip(info, (
            "Skóre 0–100 vyjadruje, ako dobre vstupné dokumenty pokrývajú kľúčové oblasti "
            "FMEA: pracovné postupy, kontrolné plány a záznamy o nezhodách. "
            "Vyššie skóre = kvalitnejší výstup AI analýzy."
        ))

        # Container pre dynamický obsah (skóre / loader)
        self._quality_content = ctk.CTkFrame(card, fg_color="transparent")
        self._quality_content.pack(fill="x", expand=True)

        # Pri inicializácii zobrazíme loading stav
        if self._quality_loading:
            self._render_quality_loading()
        else:
            self._render_quality_content()

    # ── Render kvality – stav loading vs hotové ───────────────────────────────
    def _render_quality_loading(self):
        """Zobrazí spinner/loader pred dokončením analýzy."""
        for w in self._quality_content.winfo_children():
            w.destroy()

        loader = ctk.CTkFrame(self._quality_content, fg_color="transparent")
        loader.pack(fill="x", padx=22, pady=(0, 24))

        ctk.CTkLabel(
            loader, text="Analyzujem obsah dokumentov…",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            text_color=TEXT_PRIMARY, anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            loader,
            text="Čítam vzorky textu z PDF, DOCX a XLSX súborov.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=TEXT_MUTED, anchor="w",
        ).pack(anchor="w", pady=(4, 12))

        # Indeterminate progress bar
        self._loader_pb = ctk.CTkProgressBar(
            loader, mode="indeterminate", height=6,
            fg_color=BG_SUBTLE_HI,
            progress_color=COLOR_IDLE,
        )
        self._loader_pb.pack(fill="x")
        self._loader_pb.start()

    def _render_quality_content(self):
        """Zobrazí reálne dáta z analýzy kvality."""
        for w in self._quality_content.winfo_children():
            w.destroy()

        if self.quality is None:
            return

        # Veľké skóre + label
        score_row = ctk.CTkFrame(self._quality_content, fg_color="transparent")
        score_row.pack(fill="x", padx=22, pady=(0, 8))

        ctk.CTkLabel(
            score_row, text=f"{self.quality.score}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=42, weight="bold"),
            text_color=self.quality.score_color,
        ).pack(side="left")

        ctk.CTkLabel(
            score_row, text=f"/ 100",
            font=ctk.CTkFont(family=FONT_FAMILY, size=18),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(4, 14), pady=(14, 0))

        ctk.CTkLabel(
            score_row, text=self.quality.score_label,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=self.quality.score_color,
        ).pack(side="left", padx=(0, 0), pady=(16, 0))

        # Progress bar
        bar = QualityScoreBar(self._quality_content, self.quality.score, self.quality.score_color)
        bar.pack(fill="x", padx=22, pady=(8, 16))

        # Detekované sekcie (mriežka 2 stĺpce)
        sections_frame = ctk.CTkFrame(self._quality_content, fg_color="transparent")
        sections_frame.pack(fill="x", padx=22, pady=(0, 14))

        section_labels = {
            "pracovny_postup":     ("Pracovný postup", "Identifikácia krokov procesu"),
            "kontrolny_plan":      ("Kontrolný plán",   "Hodnotenie metód odhalenia (D)"),
            "zaznamy_nezhod":      ("Záznamy o nezhodách", "Hodnotenie pravdepodobnosti výskytu (O)"),
            "udrzba_kalibrácia":   ("Údržba a kalibrácia", "Doplňujúci kontext"),
        }

        for i, (key, (label, desc)) in enumerate(section_labels.items()):
            detected = self.quality.detected_sections.get(key, False)
            row = i // 2
            col = i % 2

            cell = ctk.CTkFrame(
                sections_frame,
                fg_color=BG_SUBTLE,
                corner_radius=RADIUS_MD,
                border_width=1, border_color=BORDER_SOFT,
            )
            cell.grid(row=row, column=col, padx=(0, 6) if col == 0 else (6, 0),
                      pady=(0, 6) if row == 0 else (6, 0), sticky="nsew")

            inner = ctk.CTkFrame(cell, fg_color="transparent")
            inner.pack(padx=12, pady=10, fill="x")

            icon_color = COLOR_SUCCESS if detected else COLOR_ERROR
            icon_char  = "✓" if detected else "✕"

            top = ctk.CTkFrame(inner, fg_color="transparent")
            top.pack(fill="x")
            ctk.CTkLabel(
                top, text=icon_char, text_color=icon_color,
                font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            ).pack(side="left")
            ctk.CTkLabel(
                top, text=label,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                text_color=TEXT_PRIMARY,
            ).pack(side="left", padx=(8, 0))

            ctk.CTkLabel(
                inner, text=desc,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                text_color=TEXT_MUTED, anchor="w", justify="left", wraplength=240,
            ).pack(anchor="w", pady=(2, 0))

        sections_frame.grid_columnconfigure(0, weight=1)
        sections_frame.grid_columnconfigure(1, weight=1)

        # Odporúčania
        recs_frame = ctk.CTkFrame(
            self._quality_content, fg_color=BG_SUBTLE,
            corner_radius=RADIUS_MD,
            border_width=1, border_color=BORDER_SOFT,
        )
        recs_frame.pack(fill="x", padx=22, pady=(4, 20))

        ctk.CTkLabel(
            recs_frame, text="Odporúčania",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", padx=14, pady=(10, 4))

        for rec in self.quality.recommendations[:4]:
            row = ctk.CTkFrame(recs_frame, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(0, 4))
            ctk.CTkLabel(
                row, text="•", text_color=TEXT_MUTED,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            ).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                row, text=rec,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                text_color=TEXT_SECONDARY,
                anchor="w", justify="left", wraplength=520,
            ).pack(side="left", anchor="w", fill="x", expand=True)

        ctk.CTkLabel(recs_frame, text="").pack(pady=(0, 4))

    def _update_quality_card(self):
        """Aktualizuje kartu kvality po dokončení analýzy v threade."""
        try:
            if hasattr(self, "_loader_pb"):
                try:
                    self._loader_pb.stop()
                except Exception:
                    pass
            self._render_quality_content()
        except Exception as e:
            print(f"Chyba pri obnove karty kvality: {e}")

# ── Karta cenového odhadu ──────────────────────────────────────────────────
    def _build_cost_card(self, parent):
        card = self._make_card(parent)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(20, 12))

        ctk.CTkLabel(
            head, text="💰  Odhad ceny analýzy",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        info = ctk.CTkLabel(
            head, text="ⓘ", text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            cursor="hand2",
        )
        info.pack(side="left", padx=(8, 0))
        add_tooltip(info, (
            "Odhad nákladov za jeden beh PFMEA Tool. Vychádza z veľkosti vstupných "
            "dokumentov, počtu identifikovaných krokov a aktuálnych cien Anthropic API. "
            "Skutočná cena sa môže líšiť ±20 % v závislosti od obsahu."
        ))

        # Hlavná suma
        price_row = ctk.CTkFrame(card, fg_color="transparent")
        price_row.pack(fill="x", padx=22, pady=(0, 8))

        ctk.CTkLabel(
            price_row, text=f"${self.cost.cost_total_usd:.2f}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=36, weight="bold"),
            text_color=COLOR_IDLE,
        ).pack(side="left")

        ctk.CTkLabel(
            price_row, text=f"≈ {self.cost.cost_total_eur:.2f} €",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(12, 0), pady=(14, 0))

        # Detaily v 4 stĺpcoch
        details = ctk.CTkFrame(card, fg_color=BG_SUBTLE, corner_radius=RADIUS_MD,
                               border_width=1, border_color=BORDER_SOFT)
        details.pack(fill="x", padx=22, pady=(8, 20))

        for c in range(4):
            details.grid_columnconfigure(c, weight=1)

        rows = [
            ("Vstupné tokeny",   f"{self.cost.total_input_tokens:,}".replace(",", " "),
             "Tokeny posielané do AI modelu (text vstupných dokumentov + system prompt)."),
            ("Výstupné tokeny",  f"{self.cost.output_tokens:,}".replace(",", " "),
             "Tokeny vygenerované AI modelom (FMEA položky)."),
            ("Odhad krokov",     str(self.cost.estimated_steps),
             "Predpokladaný počet krokov procesu, ktoré AI identifikuje."),
            ("Odhad položiek",   str(self.cost.estimated_items),
             "Predpokladaný počet vygenerovaných FMEA riadkov."),
        ]

        for i, (label, value, tip) in enumerate(rows):
            cell = ctk.CTkFrame(details, fg_color="transparent")
            cell.grid(row=0, column=i, padx=10, pady=14, sticky="ew")

            label_row = ctk.CTkFrame(cell, fg_color="transparent")
            label_row.pack(anchor="w")

            lbl = ctk.CTkLabel(
                label_row, text=label,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                text_color=TEXT_MUTED,
            )
            lbl.pack(side="left")
            info_dot = ctk.CTkLabel(
                label_row, text="ⓘ",
                font=ctk.CTkFont(family=FONT_FAMILY, size=10),
                text_color=TEXT_MUTED,
                cursor="hand2",
            )
            info_dot.pack(side="left", padx=(4, 0))
            add_tooltip(info_dot, tip)

            ctk.CTkLabel(
                cell, text=value,
                font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
                text_color=TEXT_PRIMARY,
            ).pack(anchor="w", pady=(2, 0))

        # Model info
        model_row = ctk.CTkFrame(card, fg_color="transparent")
        model_row.pack(fill="x", padx=22, pady=(0, 18))

        ctk.CTkLabel(
            model_row, text=f"Model:  {self.cost.model}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=TEXT_MUTED,
        ).pack(side="left")

    # ── Karta voľby legiend ────────────────────────────────────────────────────
    def _build_legend_card(self, parent):
        card = self._make_card(parent)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(20, 8))

        ctk.CTkLabel(
            head, text="📖  Vygenerovať legendy v Exceli",
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        info = ctk.CTkLabel(
            head, text="ⓘ", text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            cursor="hand2",
        )
        info.pack(side="left", padx=(8, 0))
        add_tooltip(info, (
            "Pri zapnutí: Excel obsahuje 5 listov legiend (Význam, Výskyt, Odhalenie, "
            "Klasifikácia, Istota AI) podľa metodiky AIAG/VDA a normy IEC 60812:2018.\n\n"
            "Pri vypnutí: Excel obsahuje len samotnú FMEA tabuľku — vhodné pre "
            "už zabehnuté tímy s vlastnými legendami alebo pre integráciu do interných šablón."
        ))

        ctk.CTkLabel(
            card,
            text=(
                "Excel obsahuje 5 listov s legendami pre hodnotenia S, O, D, "
                "klasifikáciu CC/SC/HI/OS a istotu AI."
            ),
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=TEXT_SECONDARY,
            anchor="w", justify="left", wraplength=560,
        ).pack(anchor="w", padx=22, pady=(0, 12))

        # Switch s vlastným popisom
        switch_row = ctk.CTkFrame(card, fg_color="transparent")
        switch_row.pack(fill="x", padx=22, pady=(0, 20))

        self._include_legends_var = ctk.BooleanVar(value=True)

        self._switch = ctk.CTkSwitch(
            switch_row,
            text="Zahrnúť legendy v Excel výstupe",
            variable=self._include_legends_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
            progress_color=COLOR_SUCCESS,
            command=self._on_switch_change,
        )
        self._switch.pack(side="left")

        self._switch_status = ctk.CTkLabel(
            switch_row, text="✓  Zapnuté",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_SUCCESS,
        )
        self._switch_status.pack(side="right")

    def _on_switch_change(self):
        if self._include_legends_var.get():
            self._switch_status.configure(text="✓  Zapnuté", text_color=COLOR_SUCCESS)
        else:
            self._switch_status.configure(text="✕  Vypnuté", text_color=TEXT_MUTED)

    # ── Tlačidlá ───────────────────────────────────────────────────────────────
    def _build_buttons(self):
        bar = ctk.CTkFrame(self, fg_color=BG_APP, height=72)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        # Separator nad tlačidlami
        sep = ctk.CTkFrame(bar, fg_color=BORDER_SOFT, height=1)
        sep.pack(fill="x", side="top")

        btn_row = ctk.CTkFrame(bar, fg_color="transparent")
        btn_row.pack(side="right", padx=20, pady=14)

        cancel_btn = ctk.CTkButton(
            btn_row, text="Zrušiť", width=120, height=40,
            corner_radius=RADIUS_MD,
            fg_color=BG_SUBTLE, hover_color=BG_SUBTLE_HI,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            command=self._on_cancel,
        )
        cancel_btn.pack(side="left", padx=(0, 10))

        confirm_btn = ctk.CTkButton(
            btn_row, text="▶  Spustiť analýzu", width=180, height=40,
            corner_radius=RADIUS_MD,
            fg_color=COLOR_IDLE, hover_color=COLOR_IDLE_HOVER,
            text_color="#ffffff",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            command=self._on_confirm,
        )
        confirm_btn.pack(side="left")

        # Klávesové skratky
        self.bind("<Return>", lambda _e: self._on_confirm())
        self.bind("<Escape>", lambda _e: self._on_cancel())

    # ── Helper na vytvorenie karty ─────────────────────────────────────────────
    def _make_card(self, parent):
        card = ctk.CTkFrame(
            parent, fg_color=BG_CARD,
            corner_radius=RADIUS_LG,
            border_width=1, border_color=BORDER_SOFT,
        )
        card.pack(fill="x", pady=(0, 14))
        return card

    # ── Akcie ─────────────────────────────────────────────────────────────────
    def _on_confirm(self):
        self._result = {
            "include_legends": self._include_legends_var.get(),
            "estimate":        self.cost,
            "quality":         self.quality,
        }
        self._close()

    def _on_cancel(self):
        self._result = None
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    # ── Verejné API ───────────────────────────────────────────────────────────
    def show_modal(self) -> dict | None:
        """
        Zobrazí dialóg modálne. Blokuje volajúci kód kým používateľ
        neklikne Spustiť alebo Zrušiť.

        Vráti dict s nastaveniami alebo None pri zrušení.
        """
        self.wait_window(self)
        return self._result 