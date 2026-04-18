"""
generator.py – AI generovanie krokov procesu a FMEA položiek.

Zmeny oproti pôvodnému:
- system prompt pre konzistentnejší výstup
- temperature=0.2 pre reprodukovateľnosť
- retry logika pri zlyhaní API
- AI-based inferencia názvu procesu (bez hardcoded reťazcov)
- lepšie prompty s explicitnými pravidlami
"""

import json
import os
import re
import time

from openai import OpenAI, APIError, RateLimitError
from dotenv import load_dotenv

from app.config import (
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_RETRIES,
    STEP_EXTRACTION_MAX_CHARS,
    CONTEXT_CHUNK_SIZE,
    CONTEXT_CHUNK_OVERLAP,
    MAX_CONTEXT_CHUNKS_PER_STEP,
    MAX_CONTEXT_CHARS_PER_STEP,
    MIN_FMEA_ITEMS_PER_STEP,
    MAX_FMEA_ITEMS_PER_STEP,
)

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT_FMEA = (
    "Si odborný inžinier kvality so skúsenosťami s procesnou FMEA podľa AIAG/VDA metodiky. "
    "Tvoje odpovede sú vždy presné, stručné a technicky správne. "
    "Nikdy nevypisuj nič mimo požadovaného formátu JSON."
)

STOPWORDS = {
    "a", "aj", "ale", "ani", "aby", "asi", "bez", "bol", "bola", "bolo", "boli",
    "by", "byť", "cez", "čo", "do", "ho", "ich", "inak", "je", "jej", "jeho",
    "ju", "k", "každý", "kde", "ktorá", "ktoré", "ktorý", "ma", "má", "medzi",
    "mi", "na", "nad", "najmä", "ne", "nebo", "než", "nie", "od", "po", "pod",
    "podľa", "pre", "pri", "sa", "si", "sme", "sú", "tak", "tie", "to", "tou",
    "tu", "tú", "v", "vo", "z", "za", "že",
    "krok", "proces", "procesu", "funkcia", "kroku", "operácia", "operacie",
    "vykonať", "vykonáva", "zabezpečiť", "zabezpečuje",
}


# ── API helper ─────────────────────────────────────────────────────────────────

def _call_model(user_prompt: str, system_prompt: str = SYSTEM_PROMPT_FMEA) -> str:
    """Zavolá OpenAI Responses API s retry logikou."""
    last_error = None

    for attempt in range(1, OPENAI_MAX_RETRIES + 1):
        try:
            response = client.responses.create(
                model=OPENAI_MODEL,
                instructions=system_prompt,
                input=user_prompt,
                temperature=OPENAI_TEMPERATURE,
            )
            return response.output_text.strip()

        except RateLimitError as e:
            wait = 2 ** attempt
            print(f"Rate limit (pokus {attempt}), čakám {wait}s...")
            time.sleep(wait)
            last_error = e

        except APIError as e:
            print(f"API chyba (pokus {attempt}): {e}")
            time.sleep(1)
            last_error = e

    raise RuntimeError(f"API zlyhalo po {OPENAI_MAX_RETRIES} pokusoch: {last_error}")


# ── JSON parsing helpers ───────────────────────────────────────────────────────

def _extract_json_part(raw: str) -> str:
    # odstráň markdown bloky
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    start = raw.find("[")
    end   = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return raw
    return raw[start:end + 1]


def _flatten_items(data) -> list:
    flat = []
    if isinstance(data, dict):
        flat.append(data)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                flat.append(item)
            elif isinstance(item, list):
                flat.extend(_flatten_items(item))
    return flat


# ── Text cleaning ──────────────────────────────────────────────────────────────

_REPLACEMENTS = {
    "dotaženie": "dotiahnutie",
    "dotažená":  "dotiahnutá",
    "dotažený":  "dotiahnutý",
    "čož":       "čo",
    "kontrolovat":     "kontrolovať",
    "identifikacia":   "identifikácia",
    "zaznam":          "záznam",
    "nespravne":       "nesprávne",
    "spravne":         "správne",
    "vyrobku":         "výrobku",
    "vyroby":          "výroby",
    "pripravok":       "prípravok",
    "automaticke":     "automatické",
    "operator":        "operátor",
    "vizualna":        "vizuálna",
    "manualna":        "manuálna",
}


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    text = " ".join(text.split())
    return (text[0].upper() + text[1:]) if text else text


def _is_meaningful(text: str, min_len: int = 8) -> bool:
    return bool(text) and len(text.strip()) >= min_len


# ── Item normalization & validation ────────────────────────────────────────────

def _normalize_item(item: dict) -> dict:
    return {
        "funkcia_procesu_pozadavky":        _clean_text(item.get("funkcia_procesu_pozadavky", "")),
        "mozna_chyba":                      _clean_text(item.get("mozna_chyba", "")),
        "mozny_nasledok_chyby":             _clean_text(item.get("mozny_nasledok_chyby", "")),
        "klasifikacia":                     _clean_text(item.get("klasifikacia", "")),
        "mozna_pricina_mechanizmus_chyby":  _clean_text(item.get("mozna_pricina_mechanizmus_chyby", "")),
        "pouzivane_metody_prevencie":       _clean_text(item.get("pouzivane_metody_prevencie", "")),
        "pouzivane_metody_odhalenia":       _clean_text(item.get("pouzivane_metody_odhalenia", "")),
        "doporucene_opatrenia":             _clean_text(item.get("doporucene_opatrenia", "")),
        "zodp_pracovnik_datum_ukoncenia":   _clean_text(item.get("zodp_pracovnik_datum_ukoncenia", "")),
        "vysledky_opatreni": "",
        "vyznam": "", "vyskyt": "", "odhalenie": "", "rpn": "",
        "novy_vyznam": "", "novy_vyskyt": "", "nove_odhalenie": "", "novy_rpn": "",
    }


_BAD_CHYBA = {
    "chyba procesu", "problém vo výrobe", "porucha procesu",
    "chyba operácie", "vykonať kontrolu", "zlepšiť proces",
    "dbať na kvalitu", "vykonať opatrenie", "kontrola", "problém",
}
_BAD_CHYBA_KEYWORDS = ["údržba", "kalibrácia", "výmena batérie", "servis", "oprava zariadenia"]


def _is_valid_item(item: dict) -> bool:
    required = [
        "funkcia_procesu_pozadavky", "mozna_chyba",
        "mozny_nasledok_chyby", "mozna_pricina_mechanizmus_chyby", "doporucene_opatrenia",
    ]
    for f in required:
        if not _is_meaningful(item.get(f, "")):
            return False

    chyba    = item["mozna_chyba"].strip().lower()
    nasledok = item["mozny_nasledok_chyby"].strip().lower()
    pricina  = item["mozna_pricina_mechanizmus_chyby"].strip().lower()
    opatrenie = item["doporucene_opatrenia"].strip().lower()

    if chyba == nasledok or chyba == pricina or nasledok == pricina:
        return False
    if chyba in _BAD_CHYBA or opatrenie in _BAD_CHYBA:
        return False
    if any(w in chyba for w in _BAD_CHYBA_KEYWORDS):
        return False
    if len(opatrenie.split()) < 2:
        return False

    return True


# ── Context selection ──────────────────────────────────────────────────────────

def _normalize_for_match(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"[^a-záäčďéíĺľňóôŕšťúýž0-9\s]", " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _tokenize(text: str) -> list[str]:
    return [
        t for t in _normalize_for_match(text).split()
        if len(t) >= 3 and t not in STOPWORDS
    ]


def _split_text_into_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks, start = [], 0
    while start < len(text):
        end   = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if end < len(text):
            best = max(chunk.rfind("\n"), chunk.rfind(". "))
            if best > int(chunk_size * 0.55):
                chunk = chunk[:best + 1].strip()
                end   = start + len(chunk)
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _score_chunk(chunk: str, query_tokens: list[str]) -> int:
    if not chunk or not query_tokens:
        return 0
    norm  = _normalize_for_match(chunk)
    score = sum(norm.count(t) * 3 for t in query_tokens if t in norm)
    score += sum(1 for w in ["kontrola", "montáž", "operátor", "meranie", "záznam", "prípravok"]
                 if w in norm)
    return score


def select_relevant_context(docs: list[dict], krok_procesu: str, funkcia_kroku: str) -> str:
    query_tokens  = _tokenize(f"{krok_procesu} {funkcia_kroku}")
    ranked_chunks = []

    for doc in docs:
        for chunk in _split_text_into_chunks(doc.get("text", ""), CONTEXT_CHUNK_SIZE, CONTEXT_CHUNK_OVERLAP):
            score = _score_chunk(chunk, query_tokens)
            if score > 0:
                ranked_chunks.append({"source": doc.get("source", ""), "score": score, "chunk": chunk})

    ranked_chunks.sort(key=lambda x: x["score"], reverse=True)
    ranked_chunks = ranked_chunks[:MAX_CONTEXT_CHUNKS_PER_STEP]

    if not ranked_chunks:
        # fallback: prvých N znakov z každého dokumentu
        parts, total = [], 0
        for doc in docs:
            part = f"ZDROJ: {doc['source']}\n{doc['text'][:1500].strip()}"
            if total + len(part) > MAX_CONTEXT_CHARS_PER_STEP:
                break
            parts.append(part)
            total += len(part) + 2
        return "\n\n".join(parts)

    parts, total = [], 0
    for item in ranked_chunks:
        part = f"ZDROJ: {item['source']}\n{item['chunk']}"
        if total + len(part) > MAX_CONTEXT_CHARS_PER_STEP:
            break
        parts.append(part)
        total += len(part) + 2
    return "\n\n".join(parts)


# ── Public API ─────────────────────────────────────────────────────────────────

def infer_process_name_from_ai(combined_text: str) -> str:
    """
    Použije AI na odvodenie stručného názvu procesu zo vstupných dokumentov.
    Nahrádza pôvodné hardcoded riešenie v pipeline.py.
    """
    truncated = combined_text[:6000]
    prompt = f"""
Na základe nasledujúceho textu zo vstupných dokumentov urči stručný slovenský názov výrobného alebo technologického procesu.

Pravidlá:
- vráť iba samotný názov procesu, bez úvodzoviek, bez vysvetlenia
- názov má byť stručný (2–6 slov), vecný a technický
- používaj slovenčinu
- ak nie je možné určiť presný názov, vráť "Výrobný proces"

Text:
{truncated}
"""
    try:
        result = _call_model(prompt, system_prompt="Si odborný technológ. Odpovedaj stručne, len požadovanú informáciu.")
        # vyčisti prípadné úvodzovky alebo markdown
        result = result.strip().strip('"\'`').strip()
        if result and len(result) < 120:
            return result
    except Exception as e:
        print(f"AI inferencia názvu procesu zlyhala: {e}")
    return "Výrobný proces"


def extract_process_steps(document_text: str) -> list[dict]:
    truncated = document_text[:STEP_EXTRACTION_MAX_CHARS]

    prompt = f"""
Z nasledujúceho textu identifikuj hlavné kroky výrobného alebo technologického procesu.

Vráť VÝLUČNE JSON zoznam v tomto formáte:
[
  {{
    "krok_procesu": "Stručný názov kroku (3–8 slov)",
    "funkcia_kroku": "Čo má krok zabezpečiť (1–2 vety)"
  }}
]

Pravidlá:
- identifikuj len hlavné, vecne odlišné kroky (nie chyby, príčiny ani opatrenia)
- funkcia_kroku vysvetľuje účel kroku, nie spôsob vykonania
- zachovaj logické poradie procesu
- nevypisuj nič mimo JSON

Text:
{truncated}
"""
    raw   = _call_model(prompt)
    jpart = _extract_json_part(raw)

    try:
        parsed  = json.loads(jpart)
        steps   = _flatten_items(parsed)
        cleaned = []
        for s in steps:
            krok    = _clean_text(s.get("krok_procesu", ""))
            funkcia = _clean_text(s.get("funkcia_kroku", ""))
            if _is_meaningful(krok, 4) and _is_meaningful(funkcia, 6):
                cleaned.append({"krok_procesu": krok, "funkcia_kroku": funkcia})
        return cleaned
    except json.JSONDecodeError:
        print("Neplatný JSON pre kroky procesu:")
        print(raw)
        return []


def generate_fmea_for_step(step_context: str, krok_procesu: str, funkcia_kroku: str) -> list[dict]:
    prompt = f"""
Vytvor FMEA riadky PRE TENTO KONKRÉTNY KROK procesu na základe poskytnutého kontextu.

Krok procesu : {krok_procesu}
Funkcia kroku: {funkcia_kroku}

Vráť VÝLUČNE JSON zoznam ({MIN_FMEA_ITEMS_PER_STEP}–{MAX_FMEA_ITEMS_PER_STEP} položiek):
[
  {{
    "funkcia_procesu_pozadavky": "Čo musí krok splniť – požiadavka na výstup",
    "mozna_chyba": "Konkrétna a stručná chyba (nie všeobecná)",
    "mozny_nasledok_chyby": "Realistický dopad chyby na produkt alebo zákazníka",
    "klasifikacia": "",
    "mozna_pricina_mechanizmus_chyby": "Mechanizmus vzniku chyby – nie jej následok",
    "pouzivane_metody_prevencie": "Existujúce preventívne opatrenia",
    "pouzivane_metody_odhalenia": "Existujúce metódy detekcie chyby",
    "doporucene_opatrenia": "Konkrétne opatrenie začínajúce slovesom",
    "zodp_pracovnik_datum_ukoncenia": ""
  }}
]

Povinné pravidlá:
- mozna_chyba musí byť KONKRÉTNA a viazaná na tento krok (nie "porucha procesu", "chyba operácie")
- mozna_pricina NESMIE byť totožná s mozna_chyba ani mozny_nasledok
- pouzivane_metody_prevencie a pouzivane_metody_odhalenia musia byť ODLIŠNÉ
- doporucene_opatrenia musia začínať SLOVESOM a byť vykonateľné
- NEuvádzaj číselné hodnotenia S/O/D ani RPN
- NEpíš nič mimo JSON

Kontext z dokumentov:
{step_context}
"""
    raw   = _call_model(prompt)
    jpart = _extract_json_part(raw)

    try:
        parsed     = json.loads(jpart)
        items      = _flatten_items(parsed)
        normalized = [_normalize_item(i) for i in items]
        return [i for i in normalized if _is_valid_item(i)]
    except json.JSONDecodeError:
        print(f"Neplatný JSON pre krok: {krok_procesu}")
        print(raw)
        return [] 