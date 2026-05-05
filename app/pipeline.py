"""
pipeline.py – orchestrácia celého FMEA procesu.

Kľúčové zmeny oproti pôvodnej verzii:
- Kroky sa generujú PARALELNE cez ThreadPoolExecutor (MAX_PARALLEL_STEPS).
- Každý krok má vlastný try/except – jedno zlyhanie nerozbije celú pipeline.
- Zachované pôvodné poradie krokov vo výsledkoch (MES-kompatibilný log).
- Priebežné status hlásenia (XX%) aj pri paralelnom spracovaní.
"""

from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from app.config import (
    RAW_DATA_DIR,
    OUTPUT_DIR,
    LOGS_DIR,
    FMEA_METADATA_DEFAULTS,
    MAX_PARALLEL_STEPS,
)
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


# ── Spracovanie jedného kroku v samostatnom vlákne ─────────────────────────────

def _process_single_step(
    step_index: int,
    step: dict,
    docs: list[dict],
) -> dict:
    """
    Izolovaná jednotka práce pre ThreadPoolExecutor. Vráti vždy dict
    (nikdy nehodí) – caller následne pozerá na pole `error`.
    """
    krok    = step.get("krok_procesu", "")
    funkcia = step.get("funkcia_kroku", "")

    try:
        context = select_relevant_context(docs, krok, funkcia)
        items   = generate_fmea_for_step(context, krok, funkcia)
        return {
            "index":         step_index,
            "krok_procesu":  krok,
            "funkcia_kroku": funkcia,
            "context":       context,
            "items":         items,
            "error":         None,
        }
    except Exception as e:
        return {
            "index":         step_index,
            "krok_procesu":  krok,
            "funkcia_kroku": funkcia,
            "context":       "",
            "items":         [],
            "error":         f"{type(e).__name__}: {e}",
        }


# ── Hlavná pipeline ────────────────────────────────────────────────────────────

def run_fmea_pipeline(
    raw_data_dir:         str  = RAW_DATA_DIR,
    output_dir:           str  = OUTPUT_DIR,
    status_callback            = None,
    model_override:       str  = None,
    parallel_steps:       int  = None,
    include_legends:      bool = True,
) -> dict:
    """
    Spustí kompletnú FMEA pipeline.

    model_override:  prepíše CLAUDE_MODEL pre toto volanie (session-level).
                     Realizované cez os.environ, aby sa prejavilo aj v generator.py.
    parallel_steps:  prepíše MAX_PARALLEL_STEPS pre toto volanie.
    """
    # Session-level override modelu pre toto volanie. generator.client je
    # singleton, ale samotné messages.create() používa model= z parametra,
    # ktorý berieme z CLAUDE_MODEL cez reimport. Najspoľahlivejšie je nastaviť
    # env + reload config vo volajúcich moduloch.
    if model_override:
        import os as _os
        _os.environ["CLAUDE_MODEL"] = model_override
        import importlib, app.config, app.generator
        importlib.reload(app.config)
        importlib.reload(app.generator)
        # Re-import lokálnych referencií, aby odtiaľto používali reloadnuté moduly
        global extract_process_steps, generate_fmea_for_step
        global select_relevant_context, infer_process_name_from_ai
        from app.generator import (
            extract_process_steps,
            generate_fmea_for_step,
            select_relevant_context,
            infer_process_name_from_ai,
        )

    # Efektívny počet paralelných workerov
    effective_parallel = parallel_steps if parallel_steps else MAX_PARALLEL_STEPS

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

    # 4 – Generovanie FMEA pre každý krok PARALELNE
    total = len(steps)
    workers = max(1, min(effective_parallel, total))
    _emit(
        status_callback,
        f"Generujem FMEA paralelne ({workers} krokov súčasne)...",
    )

    results_by_index: dict[int, dict] = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_process_single_step, idx, step, docs): idx
            for idx, step in enumerate(steps)
        }
        completed = 0
        for future in as_completed(futures):
            result = future.result()
            results_by_index[result["index"]] = result
            completed += 1

            pct = int(40 + (completed / total) * 40)   # 40–80 %
            krok_short = result["krok_procesu"][:60]
            if result["error"]:
                _emit(
                    status_callback,
                    f"[{pct}%] ⚠ Krok {completed}/{total} zlyhal "
                    f"({krok_short}): {result['error']}",
                )
            else:
                _emit(
                    status_callback,
                    f"[{pct}%] Hotové {completed}/{total}: {krok_short} "
                    f"({len(result['items'])} položiek)",
                )

    # 5 – Zachovať pôvodné poradie krokov v outputoch
    ordered_results = [results_by_index[i] for i in range(total)]

    all_items: list[dict] = []
    step_contexts: list[dict] = []
    failed_steps: list[dict] = []

    for r in ordered_results:
        all_items.extend(r["items"])
        step_contexts.append({
            "krok_procesu":  r["krok_procesu"],
            "funkcia_kroku": r["funkcia_kroku"],
            "context":       r["context"],
            "item_count":    len(r["items"]),
            "error":         r["error"],
        })
        if r["error"]:
            failed_steps.append({
                "krok_procesu": r["krok_procesu"],
                "error":        r["error"],
            })

    if failed_steps:
        _emit(
            status_callback,
            f"Upozornenie: {len(failed_steps)} z {total} krokov zlyhalo "
            "– pokračujem s ostatnými.",
        )

    items_before_validation = len(all_items)
    if items_before_validation == 0:
        raise ValueError(
            "Žiadny krok nevrátil použiteľnú FMEA položku. "
            "Skontroluj logy a vstupné dokumenty."
        )

    # 6 – Validácia
    _emit(status_callback, "[82%] Validujem a filtrujem položky...")
    all_items, validation_stats = validate_and_filter_items(all_items)
    items_after_validation = len(all_items)
    _emit(
        status_callback,
        f"Položiek po validácii: {items_after_validation} "
        f"(zamietnutých: {validation_stats['rejected_count']})",
    )

    # 7 – Scoring S/O/D + RPN
    _emit(status_callback, "[88%] Počítam S / O / D a RPN...")
    scored_items = calculate_rpn_for_all(all_items)

    # 8 – Export Excel
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_filename = build_output_filename(process_name)
    output_file     = Path(output_dir) / output_filename

    # Ak je cieľový súbor otvorený (napr. v Exceli) alebo zamknutý, skúsime
    # alternatívne meno s poradovým číslom namiesto toho, aby pipeline spadla.
    if output_file.exists():
        try:
            # Otestuj, či sa dá súbor otvoriť na zápis (uvoľnený)
            with open(output_file, "a"):
                pass
        except (PermissionError, OSError):
            stem = output_file.stem
            suffix = output_file.suffix
            for i in range(2, 20):
                alt = output_file.with_name(f"{stem}_{i}{suffix}")
                if not alt.exists():
                    output_file = alt
                    _emit(
                        status_callback,
                        f"Pôvodný Excel je zamknutý – ukladám ako {alt.name}",
                    )
                    break

    if include_legends:
        _emit(status_callback, "[93%] Exportujem Excel s legendami...")
    else:
        _emit(status_callback, "[93%] Exportujem Excel (bez legiend)...")
    export_to_excel(scored_items, str(output_file), metadata=metadata, include_legends=include_legends)

    # 9 – Log
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
        "docs":         docs,
        "steps":        steps,
        "metadata":     metadata,
        "items":        scored_items,
        "output_file":  str(output_file),
        "failed_steps": failed_steps,
        "stats": {
            "documents_count":         len(docs),
            "steps_count":             total,
            "steps_failed":            len(failed_steps),
            "items_before_validation": items_before_validation,
            "items_after_validation":  items_after_validation,
            "validation":              validation_stats,
            "per_step": [
                {"krok": sc["krok_procesu"], "count": sc["item_count"], "error": sc["error"]}
                for sc in step_contexts
            ],
        },
    } 