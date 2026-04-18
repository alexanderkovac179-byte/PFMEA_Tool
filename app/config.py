# ── Model ──────────────────────────────────────────────────────────────────────
OPENAI_MODEL = "gpt-5.4"          # gpt-5.4 / gpt-5.4-mini / gpt-5.4-nano
OPENAI_TEMPERATURE = 0.2           # nízka teplota = konzistentnejší výstup
OPENAI_MAX_RETRIES = 3             # počet opakovaní pri zlyhaní API

# ── Adresáre ───────────────────────────────────────────────────────────────────
RAW_DATA_DIR = "data/raw"
OUTPUT_DIR   = "data/output"
LOGS_DIR     = "data/logs"

# ── Extrakcia krokov ───────────────────────────────────────────────────────────
STEP_EXTRACTION_MAX_CHARS = 16000

# ── Kontext pre krok ───────────────────────────────────────────────────────────
CONTEXT_CHUNK_SIZE          = 1200
CONTEXT_CHUNK_OVERLAP       = 180
MAX_CONTEXT_CHUNKS_PER_STEP = 4
MAX_CONTEXT_CHARS_PER_STEP  = 5000

# ── Počet FMEA riadkov na krok ─────────────────────────────────────────────────
MIN_FMEA_ITEMS_PER_STEP = 1
MAX_FMEA_ITEMS_PER_STEP = 3

# ── Predvolené metadáta ────────────────────────────────────────────────────────
FMEA_METADATA_DEFAULTS = {
    "nazov_procesu":  "Proces načítaný zo vstupných dokumentov",
    "cislo_fmea":     "PFMEA-001",
    "typ_fmea":       "Procesná FMEA",
    "revizia":        "0",
    "vypracoval":     "AI prototyp / používateľ",
    "poznamka":       "Automaticky generovaný návrh FMEA z dokumentov",
    "nazov_hlavicky": "Procesná FMEA",
}

# ── Validačné pravidlá ─────────────────────────────────────────────────────────
VALIDATION_RULES = {
    "min_text_len":                        8,
    "max_items_per_step_after_validation": 3,
    "reject_generic_errors":               True,
}

# ── Excel – šírky stĺpcov ──────────────────────────────────────────────────────
EXCEL_COLUMN_WIDTHS = {
    "A": 34, "B": 30, "C": 36, "D": 10, "E": 18,
    "F": 36, "G": 10, "H": 34, "I": 34, "J": 10,
    "K": 10, "L": 38, "M": 24, "N": 12, "O": 12,
    "P": 14, "Q": 12,
}