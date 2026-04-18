"""
pipeline.py – orchestrácia celého FMEA procesu.

Zmeny:
- infer_process_name nahradený AI-based verziou z generator.py
- odstránené hardcoded názvy procesov
- integrované write_run_log (logging_utils.py)
- lepšie status správy s percentuálnym postupom
- výstupný súbor obsahuje rok aj mesiac
"""

from pathlib import Path
from datetime import datetime
import re

from app.config import RAW_DATA_DIR, OUTPUT_DIR, LOGS_DIR, FMEA_METADATA_DEFAULTS
from app.loaders import load_documents
from app.generator import (
    extract_process_steps,
    generate_fmea_for_step,
    select_relevant_context,
    infer_process_name_from_ai,
)
from app.scoring import calculate_rpn_for_all
from app.exporter import export_to_excel
from app.validator import validate_and_filter_items
from app.logging_utils import build_log_path, write_run_log


# ── Pomocné funkcie ────────────────────────────────────────────────────────────

def slugify_filename(text: str) -> str:
    text = str(text or "").strip().lower()
    replacements = {
        "á": "a", "ä": "a", "č": "c", "ď": "d", "é": "e",
        "í": "i", "ĺ": "l", "ľ": "l", "ň": "n", "ó": "o",
        "ô": "o", "ŕ": "r", "š": "s", "ť": "t", "ú": "u",
        "ý": "y", "ž": "z",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "proces"


def build_output_filename(process_name: str) -> str:
    stamp = datetime.now().strftime("%Y-%m")
    slug  = slugify_filename(process_name)
    return f"pfmea_{slug}_{stamp}.xlsx"


def build_fmea_metadata(process_name: str) -> dict:
    metadata = dict(FMEA_METADATA_DEFAULTS)
    metadata["nazov_procesu"] = process_name
    return metadata


def _emit(cb, message: str):
    if cb:
        cb(message)


# ── Hlavná pipeline ────────────────────────────────────────────────────────────

def run_fmea_pipeline(
    raw_data_dir: str = RAW_DATA_DIR,
    output_dir:   str = OUTPUT_DIR,
    status_callback=None,
) -> dict:

    # 1 – Načítanie dokumentov
    _emit(status_callback, "Načítavam vstupné dokumenty...")
    docs = load_documents(raw_data_dir)
    if not docs:
        raise ValueError("Neboli nájdené žiadne vstupné dokumenty (PDF, DOCX, TXT).")

    combined_text = "\n\n".join(
        f"ZDROJ: {d['source']}\n{d['text']}" for d in docs
    )
    _emit(status_callback, f"Načítaných dokumentov: {len(docs)}")

    # 2 – AI inferencia názvu procesu
    _emit(status_callback, "Identifikujem názov procesu...")
    process_name = infer_process_name_from_ai(combined_text)
    metadata     = build_fmea_metadata(process_name)
    _emit(status_callback, f"Názov procesu: {process_name}")

    # 3 – Extrakcia krokov
    _emit(status_callback, "Extrahujem kroky procesu...")
    steps = extract_process_steps(combined_text)
    if not steps:
        raise ValueError("Nepodarilo sa identifikovať kroky procesu.")
    _emit(status_callback, f"Identifikovaných krokov: {len(steps)}")

    # 4 – Generovanie FMEA pre každý krok
    all_items    = []
    step_contexts = []

    for idx, step in enumerate(steps, start=1):
        krok    = step["krok_procesu"]
        funkcia = step["funkcia_kroku"]
        pct     = int(40 + (idx / len(steps)) * 40)   # 40–80 %
        _emit(status_callback, f"[{pct}%] Generujem FMEA – krok {idx}/{len(steps)}: {krok}")

        context    = select_relevant_context(docs, krok, funkcia)
        step_items = generate_fmea_for_step(context, krok, funkcia)

        step_contexts.append({
            "krok_procesu": krok,
            "funkcia_kroku": funkcia,
            "context": context,
            "item_count": len(step_items),
        })
        all_items.extend(step_items)

    items_before_validation = len(all_items)

    # 5 – Validácia
    _emit(status_callback, "[82%] Validujem a filtrujem položky...")
    all_items, validation_stats = validate_and_filter_items(all_items)
    items_after_validation = len(all_items)
    _emit(status_callback, f"Položiek po validácii: {items_after_validation} (zamietnutých: {validation_stats['rejected_count']})")

    # 6 – Scoring S/O/D + RPN
    _emit(status_callback, "[88%] Počítam S / O / D a RPN...")
    scored_items = calculate_rpn_for_all(all_items)

    # 7 – Export Excel
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_filename = build_output_filename(process_name)
    output_file     = Path(output_dir) / output_filename

    _emit(status_callback, "[93%] Exportujem Excel...")
    export_to_excel(scored_items, str(output_file), metadata=metadata)

    # 8 – Log
    try:
        log_path = build_log_path(LOGS_DIR, process_name)
        write_run_log(
            log_path=log_path,
            docs=docs,
            process_name=process_name,
            steps=steps,
            step_contexts=step_contexts,
            items_before_cleaning=items_before_validation,
            items_after_cleaning=items_after_validation,
            output_file=str(output_file),
        )
        _emit(status_callback, f"Log uložený: {log_path}")
    except Exception as e:
        _emit(status_callback, f"Varovanie: log sa nepodarilo uložiť ({e})")

    _emit(status_callback, "[100%] Analýza dokončená.")

    return {
        "docs":        docs,
        "steps":       steps,
        "metadata":    metadata,
        "items":       scored_items,
        "output_file": str(output_file),
        "stats": {
            "documents_count":       len(docs),
            "steps_count":           len(steps),
            "items_before_validation": items_before_validation,
            "items_after_validation":  items_after_validation,
            "validation":            validation_stats,
            "per_step":              [
                {"krok": sc["krok_procesu"], "count": sc["item_count"]}
                for sc in step_contexts
            ],
        },
    }