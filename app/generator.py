"""
generator.py – volanie Claude API pre extrakciu krokov procesu a generovanie
FMEA položiek.

Kľúčové optimalizácie:
- Prompt caching na FMEA systémovej inštrukcii (90% zľava na opakovaných volaniach).
- Retry/timeout cez anthropic SDK (max_retries, timeout).
- Oddelenie statickej systémovej inštrukcie od dynamickej user správy.
- Pydantic (FmeaItem) normalizácia namiesto ručného _is_valid_item.
- Pole `klasifikacia` odstránené z AI schémy – priradí sa deterministicky
  v scoring.assign_classification (úspora tokenov + eliminácia halucinácií).
"""

import json
import os
import re
from anthropic import Anthropic
from dotenv import load_dotenv

from app.config import (
    CLAUDE_MODEL,
    STEP_EXTRACTION_MAX_CHARS,
    CONTEXT_CHUNK_SIZE,
    CONTEXT_CHUNK_OVERLAP,
    MAX_CONTEXT_CHUNKS_PER_STEP,
    MAX_CONTEXT_CHARS_PER_STEP,
    MIN_FMEA_ITEMS_PER_STEP,
    MAX_FMEA_ITEMS_PER_STEP,
    API_MAX_RETRIES,
    API_TIMEOUT_SEC,
    API_MAX_TOKENS_FMEA,
)
from app.models import FmeaItem
from app.owner_assignment import assign_owner

load_dotenv()

# SDK má vstavanú exponential-backoff retry logiku pre 408, 409, 429, 5xx
# a sieťové chyby. max_retries zdvojujeme oproti defaultu (2 → 4).
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_retries=API_MAX_RETRIES,
    timeout=API_TIMEOUT_SEC,
)


STOPWORDS = {
    "a", "aj", "ale", "ani", "aby", "asi", "bez", "bol", "bola", "bolo", "boli",
    "by", "byť", "cez", "čo", "do", "ho", "ich", "inak", "je", "jej", "jeho",
    "ju", "k", "každý", "kde", "ktorá", "ktoré", "ktorý", "ma", "má", "medzi",
    "mi", "na", "nad", "najmä", "ne", "nebo", "než", "nie", "od", "po", "pod",
    "podľa", "pre", "pri", "sa", "si", "sme", "sú", "tak", "tie", "to", "tou",
    "tu", "tú", "v", "vo", "z", "za", "že",
    "krok", "proces", "procesu", "funkcia", "kroku", "operácia", "operacie",
    "vykonať", "vykonáva", "zabezpečiť", "zabezpečuje"
}


# ── Systémové prompty (CACHEABLE) ─────────────────────────────────────────────
# Čím dlhší statický systémový prompt, tým väčší benefit z prompt cachingu.
# Cache je ephemeral (5 min TTL) – pri pipeline, ktorá má 5-15 krokov spustených
# paralelne, sa všetky okrem prvého platia 10 % ceny vstupných tokenov.

FMEA_SYSTEM_PROMPT = f"""Si odborný asistent pre procesnú FMEA (Failure Mode and Effects Analysis)
podľa metodiky AIAG & VDA (vydanie 2019).

=== VÝSTUPNÝ FORMÁT ===
Vraciaš VÝLUČNE JSON zoznam. Žiadny text mimo JSON. Žiadne markdown
code fences. Žiadne vysvetlenia, komentáre ani úvodné/záverečné vety.

Presná štruktúra každej položky:
[
  {{
    "funkcia_procesu_pozadavky": "...",
    "mozna_chyba": "...",
    "mozny_nasledok_chyby": "...",
    "mozna_pricina_mechanizmus_chyby": "...",
    "pouzivane_metody_prevencie": "...",
    "pouzivane_metody_odhalenia": "...",
    "doporucene_opatrenia": "...",
    "zodp_pracovnik_datum_ukoncenia": "",
    "confidence": 0.85
  }}
]

=== PRAVIDLÁ OBSAHU ===
- Vytvor {MIN_FMEA_ITEMS_PER_STEP} až {MAX_FMEA_ITEMS_PER_STEP} riadkov pre zadaný krok procesu.
- Používaj VÝLUČNE informácie, ktoré sú odôvodniteľné z poskytnutého kontextu.
- Vytváraj iba reálne chyby procesu alebo produktu viazané na tento krok.
- NEVYTVÁRAJ všeobecné chyby typu "porucha procesu", "chyba operácie",
  "problém vo výrobe", "chyba". Tieto automaticky zahodím.
- NEVYTVÁRAJ údržbové činnosti ako samotnú chybu (údržba, kalibrácia,
  servis, oprava zariadenia).
- NEVYTVÁRAJ duplicitné riadky (rovnaká chyba + rovnaká príčina).

=== SYSTEMATICKÁ IDENTIFIKÁCIA CHÝB (POVINNÝ POSTUP) ===
Pre zabezpečenie konzistentných výsledkov naprieč behmi použi NASLEDOVNÝ
kontrolný zoznam kategórií rizík. Pre každý krok procesu postupne zváž
KAŽDÚ kategóriu a ak je tam reálne riziko, vytvor riadok:

  1. MATERIÁL / VSTUP – nesprávny diel, zámena materiálu, kontaminácia,
     exspirácia, poškodenie obalu, dodávateľské riziko
  2. METÓDA / POSTUP – vynechaný krok, nesprávne poradie, nesprávne
     parametre (teplota, tlak, moment, čas, koncentrácia)
  3. STROJ / ZARIADENIE – porucha, opotrebenie, nesprávna kalibrácia,
     výpadok, strata funkcie
  4. MERANIE / KONTROLA – zlyhanie senzora, nepresná detekcia,
     prehliadnutie chyby, falošne OK výsledok
  5. PROSTREDIE – teplota, vlhkosť, prach, kontaminácia prostredia,
     elektromagnetické rušenie, aseptika
  6. ĽUDSKÝ FAKTOR – chyba operátora v postupe, zámena, obídenie kontroly,
     nepozornosť (ale OWNER nesmie byť "Operátor")
  7. BOZP / ERGONÓMIA – úraz, popálenie, privretie, ručná manipulácia nad
     limit, chemická expozícia, ostré hrany – aspoň 1 riadok ak krok má
     manuálnu prácu
  8. SYSTÉMOVÉ / IT – chyba v MES/ERP/databáze, chybná konfigurácia,
     obídenie interlock-u, únik dát
  9. TRACEABILITY / ZÁZNAM – chýbajúci záznam, nečitateľný identifikátor,
     nesprávne šaržovanie, porušená sledovateľnosť

Nie každý krok má riziká v každej kategórii – ak ich nemá, vynechaj.
Ale PREJDI CELÝ ZOZNAM, nevynechávaj kategórie systematicky.

=== POŽIADAVKY NA JEDNOTLIVÉ POLIA ===
• mozna_chyba – stručná a konkrétna, jedna veta.
• mozny_nasledok_chyby – realistický a PRIMERANÝ danej chybe. MUSÍ byť
  odlišný od mozna_chyba.

  NAPÍŠ PRIMÁRNY A NAJPRAVDEPODOBNEJŠÍ DOPAD – NIE NAJHORŠÍ MOŽNÝ SCENÁR.
  Reťazec dôsledkov má mať MAX. 2–3 úrovne (chyba → priamy dôsledok →
  dopad na zákazníka/proces). Nedotiahni reťazec k bezpečnostnému alebo
  havárijnému dopadu, ak chyba primárne nie je bezpečnostná.

  POUŽI SPRÁVNU ÚROVEŇ ZÁVAŽNOSTI:
  • Bezpečnostné formulácie ("strata bezpečnostnej funkcie", "havária",
    "úraz", "ohrozenie používateľa/pacienta", "požiar", "recall") POUŽI
    LEN ak chyba PRIAMO ohrozuje bezpečnosť – napr. zlyhanie brzdy,
    chybné dávkovanie liečiva, zlyhanie ochranného krytu, kontaminácia
    potraviny patogénom, nezaistená manipulácia s ťažkým bremenom.
  • Pri kvalitárskych chybách (vibrácie, tolerancie, vzhľad, životnosť,
    estetika, čiastočne znížená funkcia) opíš KVALITÁRSKE následky –
    "reklamácia", "zníženie životnosti", "zvýšené opotrebenie",
    "nesprávna funkcia bez bezpečnostného dopadu", "obmedzená
    funkčnosť pri zachovaní základnej funkcie".
  • Pri ergonomických / procesných chybách opíš dopad na proces –
    "zastavenie linky", "prepracovanie", "vyradenie kusa", bez eskalácie
    k bezpečnosti.

  PRÍKLADY SPRÁVNEHO POSÚDENIA:
  ZLE (zveličené):
    "Nedotiahnutie skrutiek momentom → uvoľnenie počas prevádzky vozidla
    → strata bezpečnostnej funkcie → riziko havárie a recall"
  DOBRE (primerané):
    "Nedotiahnutie skrutiek na predpísaný moment → znížená pevnosť spoja
    → predčasné opotrebenie a riziko reklamácie zákazníka"

  ZLE (zveličené):
    "Vibrácie pri rozbehu → opotrebenie uloženia → strata bezpečnostnej
    funkcie pohonu"
  DOBRE (primerané):
    "Vibrácie pri rozbehu → predčasné opotrebenie ložiska → reklamácia
    zákazníka v rámci záruky"

  Bezpečnostnú formuláciu použi LEN keď je obhájiteľná – nie ako
  defaultné dotiahnutie reťazca.

• mozna_pricina_mechanizmus_chyby – vysvetľuje VZNIK chyby (mechanizmus),
  NIE jej následok. MUSÍ byť odlišné od následku.
• pouzivane_metody_prevencie – ako sa ZABRÁNI vzniku chyby. Samostatne
  od metód odhalenia.
• pouzivane_metody_odhalenia – ako sa ZISTÍ, že chyba nastala.
• doporucene_opatrenia – konkrétne, vykonateľné, MIN. 2 slová, ZAČÍNAJÚ
  slovesom (zaviesť, implementovať, doplniť, nastaviť, preškoliť, ...).
• zodp_pracovnik_datum_ukoncenia – vyplň IBA ak je vo vstupných dokumentoch
  (napr. v kontrolnom pláne, NCR zázname alebo pracovnom postupe) explicitne
  uvedená zodpovedná rola pre daný typ chyby/kontroly/opatrenia. Ak dokument
  hovorí "Zodp: Technik kvality", "Vlastník: Procesný inžinier",
  "Eskalovať na vedúceho údržby", vráť túto rolu (ideálne aj s dátumom
  ak je uvedený). Ak žiadna konkrétna rola pre túto chybu v dokumentoch
  NIE JE uvedená, VRÁŤ PRÁZDNY REŤAZEC "". NEODHADUJ, NEVYMÝŠĽAJ, NEGENERALIZUJ.
  Zvlášť NIKDY NEVRACIAJ hodnotu "Operátor" – operátor vo FMEA nie je
  vlastníkom nápravných opatrení.
• confidence – float 0.0–1.0, istota položky na základe kontextu:
    1.0 = chyba explicitne doložená v kontexte (záznam o nezhodách, kontrolný plán)
    0.7–0.9 = chyba odvoditeľná z kontextu (pracovný postup, procesný tok)
    0.4–0.6 = typická chyba pre daný typ operácie, kontext ju priamo nespomína
    0.0–0.3 = generická chyba, kontext je slabý alebo chýba

=== ČO NEUVÁDZAŠ ===
- Klasifikáciu CC/OS/SC/HI (priradí sa automaticky podľa S/O po generovaní).
- Číselné hodnotenia severity (Význam), occurrence (Výskyt), detection (Odhalenie).
- Polia novy_vyznam, novy_vyskyt, nove_odhalenie, novy_rpn.

=== JAZYK ===
- Odborná slovenčina (technická / odvetvová terminológia).
- Stručne a vecne, bez zbytočných prídavných mien a vaty.
- Prispôsob terminológiu odvetviu: strojárstvo (moment, vôľa, os), potravinárstvo
  (CCP, HACCP, kontaminácia, alergén), farmácia (koncentrácia, validácia šarže),
  elektronika (signál, skrat, prerušenie obvodu), služby (SLA, GDPR, úplnosť
  údajov), administratíva (doklad, záznam, archivácia)."""


STEP_EXTRACTION_SYSTEM_PROMPT = """Si odborný asistent pre analýzu procesov.

Z poskytnutého textu identifikuj hlavné, vecne odlišné kroky výrobného
alebo technologického procesu a vráť ich ako JSON zoznam.

Výstupný formát (presná štruktúra):
[
  {"krok_procesu": "...", "funkcia_kroku": "..."}
]

Pravidlá:
- Identifikuj len hlavné, vecne odlišné kroky procesu.
- Nevracaj chyby, príčiny ani následky.
- funkcia_kroku má stručne vysvetliť, ČO má krok zabezpečiť.
- Zachovaj logické poradie procesu.
- Administratívne a systémové kroky (skenovanie kódu, zápis do MES) ponechaj.
- Vráť VÝLUČNE JSON, žiadny text mimo neho."""


NAME_INFERENCE_SYSTEM_PROMPT = (
    "Si odborný technológ. Odpovedaj stručne, výlučne požadovanú informáciu."
)


# ── Nízkoúrovňové volanie Claude API ───────────────────────────────────────────

def _call_model(
    user_prompt: str,
    system_prompt: str | None = None,
    max_tokens: int = API_MAX_TOKENS_FMEA,
    use_cache: bool = False,
) -> str:
    """
    Volá Anthropic Messages API a vráti zlúčený text z odpovede.

    Konzistentnosť výstupov medzi behmi sa rieši výhradne cez systematický
    checklist v prompte (9 kategórií rizík, explicitné pravidlá). Parameter
    `temperature` sa NEPOUŽÍVA – novšie Claude modely ho neakceptujú
    (invalid_request_error).

    Parametre:
    - use_cache=True označí systémový prompt ako ephemeral cache breakpoint.
      Opakované volania s rovnakým system_prompt v ~5 min okne platia 10 %
      ceny vstupných tokenov.
    """
    kwargs: dict = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    if system_prompt:
        if use_cache:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)

    # Odpoveď je zoznam blokov – zaujímajú nás len textové.
    parts = [
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    ]
    return "".join(parts).strip()


# ── Pomocné parsery a normalizátory ────────────────────────────────────────────

def _extract_json_part(raw_output: str) -> str:
    start = raw_output.find("[")
    end = raw_output.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return raw_output
    return raw_output[start:end + 1]


def _flatten_items(data):
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


_DIACRITIC_FIXES = {
    "dotaženie": "dotiahnutie",
    "dotažená": "dotiahnutá",
    "dotažený": "dotiahnutý",
    "čož": "čo",
    "zámienka": "zámena",
    "bezúhľa": "bezchybnosť",
    "výmenna": "výmena",
    "kontrolovat": "kontrolovať",
    "identifikacia": "identifikácia",
    "zaznam": "záznam",
    "nespravne": "nesprávne",
    "spravne": "správne",
    "vyrobku": "výrobku",
    "vyroby": "výroby",
    "pripravok": "prípravok",
    "automaticke": "automatické",
    "operator": "operátor",
    "vizualna": "vizuálna",
    "manualna": "manuálna",
}


def _clean_text(value):
    """Odstráni AI-typické preklepy, zduplikované medzery, ošetrí prvé písmeno."""
    if value is None:
        return ""
    text = str(value).strip()
    for old, new in _DIACRITIC_FIXES.items():
        text = text.replace(old, new)
    text = " ".join(text.split())
    if text:
        text = text[0].upper() + text[1:]
    return text


def _normalize_raw_item(raw: dict) -> dict:
    """Očistí textové polia a pridá prázdne technické polia s defaultmi."""
    return {
        "funkcia_procesu_pozadavky": _clean_text(raw.get("funkcia_procesu_pozadavky", "")),
        "mozna_chyba": _clean_text(raw.get("mozna_chyba", "")),
        "mozny_nasledok_chyby": _clean_text(raw.get("mozny_nasledok_chyby", "")),
        "mozna_pricina_mechanizmus_chyby": _clean_text(raw.get("mozna_pricina_mechanizmus_chyby", "")),
        "pouzivane_metody_prevencie": _clean_text(raw.get("pouzivane_metody_prevencie", "")),
        "pouzivane_metody_odhalenia": _clean_text(raw.get("pouzivane_metody_odhalenia", "")),
        "doporucene_opatrenia": _clean_text(raw.get("doporucene_opatrenia", "")),
        "zodp_pracovnik_datum_ukoncenia": _clean_text(raw.get("zodp_pracovnik_datum_ukoncenia", "")),
        "confidence": raw.get("confidence", 0.5),
        # technické polia s defaultmi – doplní scoring
        "klasifikacia": "",
        "vyznam": 0, "vyskyt": 0, "odhalenie": 0, "rpn": 0,
        "novy_vyznam": 0, "novy_vyskyt": 0, "nove_odhalenie": 0, "novy_rpn": 0,
        "vysledky_opatreni": "",
    }


# ── Výber relevantného kontextu ────────────────────────────────────────────────

def _normalize_for_match(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"[^a-záäčďéíĺľňóôŕšťúýž0-9\s]", " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _tokenize(text: str) -> list[str]:
    text = _normalize_for_match(text)
    return [t for t in text.split() if len(t) >= 3 and t not in STOPWORDS]


def _split_text_into_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()

        if end < text_len:
            newline_pos = chunk.rfind("\n")
            period_pos = chunk.rfind(". ")
            best_pos = max(newline_pos, period_pos)
            if best_pos > int(chunk_size * 0.55):
                chunk = chunk[:best_pos + 1].strip()
                end = start + len(chunk)

        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = max(end - overlap, start + 1)

    return chunks


def _score_chunk(chunk: str, query_tokens: list[str]) -> int:
    if not chunk or not query_tokens:
        return 0
    chunk_norm = _normalize_for_match(chunk)
    score = 0
    for token in query_tokens:
        if token in chunk_norm:
            score += 3
    score += sum(chunk_norm.count(token) for token in query_tokens)
    if any(w in chunk_norm for w in ["kontrola", "montáž", "operátor", "meranie", "záznam", "prípravok"]):
        score += 1
    return score


def select_relevant_context(docs: list[dict], krok_procesu: str, funkcia_kroku: str) -> str:
    query_tokens = _tokenize(f"{krok_procesu} {funkcia_kroku}")
    ranked_chunks = []

    for doc in docs:
        source = doc.get("source", "")
        text = doc.get("text", "")
        if not text.strip():
            continue

        chunks = _split_text_into_chunks(
            text=text,
            chunk_size=CONTEXT_CHUNK_SIZE,
            overlap=CONTEXT_CHUNK_OVERLAP,
        )
        for chunk in chunks:
            score = _score_chunk(chunk, query_tokens)
            if score > 0:
                ranked_chunks.append({"source": source, "score": score, "chunk": chunk})

    ranked_chunks.sort(key=lambda x: x["score"], reverse=True)
    ranked_chunks = ranked_chunks[:MAX_CONTEXT_CHUNKS_PER_STEP]

    # Fallback: nič sa netrafilo – vezmi začiatky dokumentov.
    if not ranked_chunks:
        fallback_parts = []
        current_len = 0
        for doc in docs:
            part = f"ZDROJ: {doc['source']}\n{doc['text'][:1500].strip()}"
            if current_len + len(part) > MAX_CONTEXT_CHARS_PER_STEP:
                break
            fallback_parts.append(part)
            current_len += len(part) + 2
        return "\n\n".join(fallback_parts)

    selected_parts = []
    current_len = 0
    for item in ranked_chunks:
        part = f"ZDROJ: {item['source']}\n{item['chunk']}"
        if current_len + len(part) > MAX_CONTEXT_CHARS_PER_STEP:
            break
        selected_parts.append(part)
        current_len += len(part) + 2

    return "\n\n".join(selected_parts)


# ── Verejné funkcie volané z pipeline ──────────────────────────────────────────

def infer_process_name_from_ai(combined_text: str) -> str:
    """AI odvodí stručný slovenský názov procesu zo vstupných dokumentov."""
    truncated = combined_text[:6000]
    prompt = f"""Na základe nasledujúceho textu zo vstupných dokumentov urči
stručný slovenský názov výrobného alebo technologického procesu.

Pravidlá:
- vráť IBA samotný názov procesu, bez úvodzoviek, bez vysvetlenia
- názov má byť stručný (2–6 slov), vecný a technický
- používaj slovenčinu
- ak nie je možné určiť presný názov, vráť "Výrobný proces"

Text:
{truncated}"""
    try:
        result = _call_model(
            prompt,
            system_prompt=NAME_INFERENCE_SYSTEM_PROMPT,
            max_tokens=200,
        )
        result = result.strip().strip(' "`').strip()
        if result and len(result) < 120:
            return result
    except Exception as e:
        print(f"AI inferencia názvu procesu zlyhala: {e}")
    return "Výrobný proces"


def extract_process_steps(document_text: str) -> list[dict]:
    """AI identifikuje kroky procesu zo vstupného textu."""
    truncated_text = document_text[:STEP_EXTRACTION_MAX_CHARS]
    user_prompt = f"Text vstupných dokumentov:\n\n{truncated_text}"

    raw_output = _call_model(
        user_prompt,
        system_prompt=STEP_EXTRACTION_SYSTEM_PROMPT,
        max_tokens=4096,
    )
    json_part = _extract_json_part(raw_output)

    try:
        parsed = json.loads(json_part)
    except json.JSONDecodeError:
        print("Model nevrátil validný JSON pre kroky procesu.")
        print(raw_output)
        return []

    steps = _flatten_items(parsed)
    cleaned = []
    for step in steps:
        krok = _clean_text(step.get("krok_procesu", ""))
        funkcia = _clean_text(step.get("funkcia_kroku", ""))
        if len(krok) >= 4 and len(funkcia) >= 6:
            cleaned.append({"krok_procesu": krok, "funkcia_kroku": funkcia})
    return cleaned


def generate_fmea_for_step(
    step_context: str,
    krok_procesu: str,
    funkcia_kroku: str,
) -> list[dict]:
    """
    Vygeneruje FMEA položky pre jeden krok procesu.

    Systémový prompt je cache-ovaný – volania pre jednotlivé kroky zdieľajú
    rovnaký kontext inštrukcií a platia len 10 % ich vstupných tokenov
    (okrem prvého volania v 5-minútovom okne).
    """
    user_prompt = f"""Krok procesu: {krok_procesu}
Funkcia kroku: {funkcia_kroku}

Kontext zo vstupných dokumentov:
{step_context}"""

    raw_output = _call_model(
        user_prompt,
        system_prompt=FMEA_SYSTEM_PROMPT,
        use_cache=True,
        max_tokens=API_MAX_TOKENS_FMEA,
    )
    json_part = _extract_json_part(raw_output)

    try:
        parsed = json.loads(json_part)
    except json.JSONDecodeError:
        print(f"Model nevrátil validný JSON pre krok: {krok_procesu}")
        print(raw_output)
        return []

    raw_items = _flatten_items(parsed)

    # Normalizácia + Pydantic validácia. Štruktúrne zlé položky (napr. chýbajúca
    # mozna_chyba) sa zahodia bez pádu. Business-level validácia (chyba vs.
    # následok, generické frázy, …) ide cez validator.py v pipeline.py.
    result: list[dict] = []
    for raw in raw_items:
        normalized = _normalize_raw_item(raw)
        normalized["zodp_pracovnik_datum_ukoncenia"] = assign_owner(
            normalized,
            krok_procesu=krok_procesu,
            funkcia_kroku=funkcia_kroku,
            context=step_context,
        )
        item = FmeaItem.from_ai_output(normalized)
        if item is not None:
            result.append(item.to_dict())
    return result 