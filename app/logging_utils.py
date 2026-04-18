from pathlib import Path
from datetime import datetime
import re
import unicodedata


def slugify(text: str) -> str:
    text = str(text or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "proces"


def build_log_path(logs_dir: str, process_name: str) -> Path:
    Path(logs_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"log_{timestamp}_{slugify(process_name)}.md"
    return Path(logs_dir) / filename


def _shorten(text: str, max_len: int = 3000) -> str:
    text = str(text or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "\n\n...[skrátené]"


def write_run_log(
    log_path,
    docs: list[dict],
    process_name: str,
    steps: list[dict],
    step_contexts: list[dict],
    items_before_cleaning: int,
    items_after_cleaning: int,
    output_file: str,
):
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    lines = []
    lines.append("# Log spracovania AI-assisted procesnej FMEA")
    lines.append("")
    lines.append(f"**Dátum a čas spustenia:** {now}")
    lines.append(f"**Odvodený názov procesu:** {process_name}")
    lines.append(f"**Počet načítaných dokumentov:** {len(docs)}")
    lines.append(f"**Počet identifikovaných krokov:** {len(steps)}")
    lines.append(f"**Počet FMEA položiek pred čistením:** {items_before_cleaning}")
    lines.append(f"**Počet FMEA položiek po čistení:** {items_after_cleaning}")
    lines.append(f"**Výstupný Excel:** `{output_file}`")
    lines.append("")

    lines.append("## Načítané dokumenty")
    lines.append("")
    if docs:
        for doc in docs:
            source = doc.get("source", "Neznámy zdroj")
            text = doc.get("text", "")
            lines.append(f"- **{source}** — {len(text)} znakov")
    else:
        lines.append("- Neboli načítané žiadne dokumenty.")
    lines.append("")

    lines.append("## Identifikované kroky procesu")
    lines.append("")
    if steps:
        for i, step in enumerate(steps, start=1):
            krok = step.get("krok_procesu", "")
            funkcia = step.get("funkcia_kroku", "")
            lines.append(f"{i}. **{krok}** — {funkcia}")
    else:
        lines.append("Neboli identifikované žiadne kroky procesu.")
    lines.append("")

    lines.append("## Kontext a generovanie podľa krokov")
    lines.append("")

    if step_contexts:
        for idx, record in enumerate(step_contexts, start=1):
            krok = record.get("krok_procesu", "")
            funkcia = record.get("funkcia_kroku", "")
            context = record.get("context", "")
            item_count = record.get("item_count", 0)

            lines.append(f"### Krok {idx}: {krok}")
            lines.append("")
            lines.append(f"**Funkcia kroku:** {funkcia}")
            lines.append("")
            lines.append(f"**Počet prijatých FMEA položiek pre krok:** {item_count}")
            lines.append("")
            lines.append("**Vybraný relevantný kontext:**")
            lines.append("")
            lines.append("```text")
            lines.append(_shorten(context, 5000))
            lines.append("```")
            lines.append("")
    else:
        lines.append("Nie sú dostupné záznamy o kontexte krokov.")
        lines.append("")

    Path(log_path).write_text("\n".join(lines), encoding="utf-8")