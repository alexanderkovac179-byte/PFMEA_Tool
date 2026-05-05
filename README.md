# PFMEA Tool

**Desktopová aplikácia pre AI-asistované generovanie procesnej FMEA (Failure Mode and Effects Analysis) z technických dokumentov.**

Aplikácia automaticky analyzuje vstupné dokumenty (PDF, DOCX, XLSX, TXT, MD) a pomocou modelu Claude Opus 4.7 vygeneruje návrh procesnej FMEA podľa metodiky **AIAG/VDA 2019** a normy **IEC 60812:2018**. Výstupom je formátovaný Excel súbor s hodnotami S, O, D, RPN a klasifikáciou špeciálnych charakteristík (CC, OS, SC, HI).

> **Poznámka:** PFMEA Tool je AI-asistovaný nástroj na podporu tvorby FMEA dokumentácie. Výstup nie je finálnym auditovateľným záznamom a nenahrádza odbornú expertízu inžinierov kvality.

Diplomová práca, 2026.

---

## Hlavné vlastnosti

- **AI generuje len text** (chyby, príčiny, opatrenia), zatiaľ čo S/O/D/RPN sa počítajú deterministickými pravidlami v Pythone, čo zaručuje **reprodukovateľnosť** podľa IEC 60812:2018
- Podpora vstupných formátov: **PDF, DOCX, XLSX, TXT, MD**
- **Paralelné spracovanie** krokov procesu cez ThreadPoolExecutor
- **Confidence skóre** pre každú FMEA položku s farebným vyznačením v Exceli
- **Klasifikácia špeciálnych charakteristík** CC / OS / SC / HI podľa AIAG/VDA 2019
- **Indikátor kvality vstupných dokumentov** (skóre 0–100 s odporúčaniami)
- **Cenový odhad** pred spustením analýzy (USD aj EUR)
- **Voliteľné generovanie 5 listov legiend** v Exceli s odkazmi na IEC 60812:2018
- Tmavý režim UI cez **CustomTkinter**
- História predchádzajúcich behov, manuálne ukladanie nastavení

---

## Architektúra

```
┌─────────────┐    ┌──────────────┐
│   ui.py     │    │   main.py    │
│ (GUI)       │    │ (CLI)        │
└──────┬──────┘    └──────┬───────┘
       │                  │
       └────────┬─────────┘
                ▼
       ┌────────────────┐
       │ preflight_     │  ← cena + kvalita + voľba legiend
       │ dialog.py      │
       └────────┬───────┘
                ▼
       ┌────────────────┐
       │  pipeline.py   │  ← orchestrácia
       └────────┬───────┘
                ▼
  loaders → generator → validator → scoring → exporter
                │
                ▼
        Claude Opus 4.7 API
```

### Moduly

| Modul                 | Účel                                                                   |
| --------------------- | ---------------------------------------------------------------------- |
| `ui.py`               | Hlavné GUI v CustomTkinter                                             |
| `preflight_dialog.py` | Modálny dialóg pred spustením (cena, kvalita, voľba legiend)           |
| `pipeline.py`         | Orchestrácia celého toku spracovania                                   |
| `loaders.py`          | Načítavanie vstupných dokumentov (PDF, DOCX, XLSX, TXT)                |
| `generator.py`        | Anthropic API volania (názov procesu, kroky, FMEA položky)             |
| `validator.py`        | Validácia a deduplikácia AI výstupu                                    |
| `scoring.py`          | Deterministický výpočet S, O, D, RPN a klasifikácie                    |
| `exporter.py`         | Export do formátovaného Excelu s 5 legendami                           |
| `cost_estimator.py`   | Odhad ceny a analýza kvality vstupných dokumentov                      |
| `legends.py`          | Definície legiend pre Excel (Význam, Výskyt, Odhalenie, Klasifikácia)  |
| `models.py`           | Pydantic modely pre typovú validáciu                                   |
| `config.py`           | Centralizovaná konfigurácia                                            |
| `logging_utils.py`    | Markdown audit logy každého behu                                       |

---

## Inštalácia

### Požiadavky

- Python 3.10+
- API kľúč Anthropic (https://console.anthropic.com)
- Operačný systém: Windows / macOS / Linux

### Postup

1. **Naklonuj repozitár:**

   ```bash
   git clone https://github.com/<tvoj-username>/pfmea-tool.git
   cd pfmea-tool
   ```

2. **Vytvor virtuálne prostredie:**

   ```bash
   python -m venv venv
   ```

   Aktivuj ho:
   - **Windows:** `venv\Scripts\activate`
   - **macOS/Linux:** `source venv/bin/activate`

3. **Nainštaluj knižnice:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Vytvor `.env` súbor v root priečinku** podľa vzoru `.env.example`:

   ```env
   ANTHROPIC_API_KEY=sk-ant-api03-...
   CLAUDE_MODEL=claude-opus-4-7
   ```

5. **Spusti aplikáciu:**

   ```bash
   python -m app.ui
   ```

   alebo cez CLI:

   ```bash
   python -m app.main
   ```

---

## Použitie

1. **Pridaj vstupné dokumenty** (drag-and-drop alebo kliknutím na "Pridať súbory")
2. **Klikni na "Spustiť analýzu"** – otvorí sa preflight dialog
3. **V preflight dialógu** skontroluj:
   - Skóre kvality vstupných dokumentov (0–100)
   - Odhad ceny analýzy v USD a EUR
   - Voľbu generovania legiend v Exceli
4. **Klikni na "Spustiť analýzu"** v dialógu – pipeline beží paralelne
5. **Po dokončení** sa otvorí možnosť otvoriť vygenerovaný Excel

### Vhodné vstupné dokumenty

- Pracovné postupy a inštrukcie (Work Instructions)
- Kontrolné plány (Control Plans)
- Procesné toky (Process Flow Charts)
- Záznamy o nezhodách (NCR, 8D)
- Existujúce FMEA z podobných procesov
- Plány údržby a kalibrácie

---

## Technológie

- **Python 3.10+** – jadro aplikácie
- **Anthropic SDK** – komunikácia s Claude API
- **CustomTkinter** – moderné GUI s tmavým režimom
- **openpyxl + pandas** – generovanie a formátovanie Excelu
- **pypdf, python-docx** – načítavanie dokumentov
- **Pydantic** – typová validácia AI výstupu

---

## Súlad s normami

- **IEC 60812:2018** – Failure modes and effects analysis (FMEA and FMECA)
- **AIAG/VDA 2019** – metodika klasifikácie špeciálnych charakteristík (CC, OS, SC, HI)

Hodnoty S, O, D vychádzajú z príkladovej stupnice 1–10 uvedenej v informatívnej prílohe normy IEC 60812:2018, prispôsobenej pre procesnú FMEA v automotive odvetví podľa metodiky AIAG/VDA.

---

## Licencia

Tento projekt je vytvorený v rámci diplomovej práce. Všetky práva vyhradené.

## Autor

**Alexander [Priezvisko]** – diplomová práca, [Univerzita / Fakulta], 2026
