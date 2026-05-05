# ── Model ──────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
import os

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")

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

# ── Paralelizácia a odolnosť API volaní ────────────────────────────────────────
# Počet krokov procesu spracovaných súčasne. Typické tier-1 rate limity
# (50 RPM) bezpečne zvládnu 4-6 paralelných volaní.
MAX_PARALLEL_STEPS  = 4
# Počet automatických pokusov pri sieťovej alebo rate-limit chybe (robí SDK).
API_MAX_RETRIES     = 4
# Timeout jedného API volania v sekundách.
API_TIMEOUT_SEC     = 60.0
# Maximálny počet output tokenov pre FMEA generovanie.
API_MAX_TOKENS_FMEA = 8192

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
    "min_opatrenie_words":                 2,
}

# ── Excel – šírky stĺpcov ──────────────────────────────────────────────────────
EXCEL_COLUMN_WIDTHS = {
    "A": 34, "B": 30, "C": 36, "D": 10, "E": 18,
    "F": 36, "G": 10, "H": 34, "I": 34, "J": 10,
    "K": 10, "L": 38, "M": 24, "N": 12, "O": 12,
    "P": 14, "Q": 12, "R": 14,
}

# ── Excel – výšky riadkov ──────────────────────────────────────────────────────
EXCEL_ROW_HEIGHT_MIN = 48    # minimálna výška dátového riadku
EXCEL_ROW_HEIGHT_MAX = 240   # strop aby sa nevytváral Excel s 1000px riadkami

# ── Confidence skóre ───────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD_LOW  = 0.50   # pod touto hodnotou = červená vlajka
CONFIDENCE_THRESHOLD_MID  = 0.75   # pod touto hodnotou = žltá vlajka 