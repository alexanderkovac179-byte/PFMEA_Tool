# FMEA Studio – AI-assisted procesná FMEA

> Diplomová práca | Automatizovaná tvorba procesnej FMEA pomocou umelej inteligencie

FMEA Studio je desktopová aplikácia, ktorá automaticky generuje návrh **procesnej FMEA** (Failure Mode and Effects Analysis) z PDF a DOCX dokumentov. Výstupom je formátovaný Excel súbor podľa štandardu AIAG/VDA.

---

## Ukážka

![FMEA Studio UI](docs/screenshot.png)

---

## Ako to funguje

```
Vstupné dokumenty (PDF/DOCX)
        ↓
  Extrakcia textu
        ↓
  AI – identifikácia krokov procesu
        ↓
  AI – generovanie FMEA položiek pre každý krok
        ↓
  Deterministický výpočet S / O / D / RPN
        ↓
  Klasifikácia CC / SC (AIAG/VDA)
        ↓
  Validácia a deduplikácia
        ↓
  Export do Excelu (.xlsx)
```

---

## Požiadavky

- Python 3.10+
- OpenAI API kľúč (model `gpt-5.4`)
- Windows (UI využíva `os.startfile`)

---

## Inštalácia

```bash
# 1. Klonovanie repozitára
git clone https://github.com/TVOJE_MENO/fmea-studio.git
cd fmea-studio

# 2. Vytvorenie virtuálneho prostredia
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/macOS

# 3. Inštalácia závislostí
pip install -r requirements.txt

# 4. Drag & drop podpora (voliteľné)
pip install tkinterdnd2

# 5. Nastavenie API kľúča
cp .env.example .env
# Otvor .env a doplň svoj OPENAI_API_KEY
```

---

## Spustenie

```bash
# Grafické rozhranie
python -m app.ui

# Príkazový riadok
python -m app.main
```

---

## Štruktúra projektu

```
fmea-studio/
├── app/
│   ├── config.py          # Konfigurácia (model, limity, metadáta)
│   ├── ui.py              # Grafické rozhranie (Tkinter + drag & drop)
│   ├── pipeline.py        # Orchestrácia celého procesu
│   ├── generator.py       # AI volania – extrakcia krokov a FMEA
│   ├── scoring.py         # Deterministický výpočet S/O/D/RPN + klasifikácia CC/SC
│   ├── validator.py       # Validácia a deduplikácia položiek
│   ├── exporter.py        # Export do formátovaného Excelu
│   ├── loaders.py         # Načítanie PDF, DOCX, TXT
│   ├── legends.py         # Legenda hodnôt S/O/D (AIAG/VDA)
│   ├── logging_utils.py   # Logovanie behov do Markdown súboru
│   └── main.py            # CLI vstupný bod
├── data/
│   ├── raw/               # Sem vlož vstupné dokumenty
│   ├── output/            # Sem sa uloží vygenerovaný Excel
│   └── logs/              # Logy jednotlivých behov
├── .env.example           # Šablóna pre API kľúč
├── requirements.txt
└── README.md
```

---

## Konfigurácia

Hlavné nastavenia sú v `app/config.py`:

| Premenná | Popis | Predvolená hodnota |
|---|---|---|
| `OPENAI_MODEL` | Model OpenAI | `gpt-5.4` |
| `OPENAI_TEMPERATURE` | Teplota generovania | `0.2` |
| `MAX_FMEA_ITEMS_PER_STEP` | Max FMEA riadkov na krok | `3` |
| `STEP_EXTRACTION_MAX_CHARS` | Max znakov pre extrakciu krokov | `16 000` |

---

## Výstup – Excel

Vygenerovaný Excel obsahuje:
- **Hlavičku** s metadátami procesu (názov, dátum, revízia)
- **FMEA tabuľku** s hodnotami S/O/D, RPN a klasifikáciou CC/SC
- **Podmienené formátovanie** RPN (červená ≥ 200, žltá ≥ 100, zelená < 100)
- **3 listy legiend** pre S, O, D hodnoty podľa AIAG/VDA

---

## Odporúčané vstupné dokumenty

Pre najlepšie výsledky použite:
- Pracovné postupy / Work Instructions
- Kontrolné plány
- Procesné toky / Flow Charts
- Záznamy o nezhodách

---

## Technológie

| Vrstva | Technológia |
|---|---|
| AI generovanie | OpenAI Responses API (`gpt-5.4`) |
| UI | Python Tkinter + tkinterdnd2 |
| Spracovanie PDF | pypdf |
| Spracovanie DOCX | python-docx |
| Excel export | openpyxl + pandas |
| Štandard | AIAG/VDA FMEA (2019) |

---

## Autor

**Alexander** – Diplomová práca  
Rok: 2026

---

## Licencia

Tento projekt je určený pre akademické účely v rámci diplomovej práce.
