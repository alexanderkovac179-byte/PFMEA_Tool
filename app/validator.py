"""
validator.py – jediný zdroj pravdy pre business-level validáciu FMEA položiek.

Predtým boli pravidlá duplikované: jedna sada v generator._is_valid_item (hneď po
AI výstupe), druhá v tomto súbore (pred exportom). Teraz generator robí iba
štruktúrnu Pydantic kontrolu a obsahové pravidlá sú všetky tu.
"""

import re
from app.config import VALIDATION_RULES


GENERIC_ERRORS = {
    "chyba procesu",
    "porucha procesu",
    "problem vo vyrobe",
    "problém vo výrobe",
    "chyba operacie",
    "chyba operácie",
    "problem",
    "problém",
    "nespravny proces",
    "nesprávny proces",
    "chyba",
    "porucha",
}

GENERIC_ACTIONS = {
    "vykonat kontrolu",
    "vykonať kontrolu",
    "zlepsit proces",
    "zlepšiť proces",
    "vykonat opatrenie",
    "vykonať opatrenie",
    "dbat na kvalitu",
    "dbať na kvalitu",
    "kontrola",
    "opatrenie",
}

# Kľúčové slová, ktoré signalizujú, že model vytvoril údržbovú činnosť
# ako "chybu". Tieto patria do FMEA systému, nie do riadku mozna_chyba.
MAINTENANCE_KEYWORDS = [
    "údržba",
    "kalibrácia",
    "servis",
    "oprava zariadenia",
    "výmena batérie",
    "plánovaná údržba",
]


def _norm(text: str) -> str:
    """Lowercase + single-space + strip – pre porovnanie obsahov."""
    text = str(text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _looks_meaningful(text: str) -> bool:
    return len(_norm(text)) >= VALIDATION_RULES["min_text_len"]


def validate_item(item: dict) -> tuple[bool, list[str]]:
    """
    Posúdi, či má FMEA položka dostatočnú kvalitu na export.

    Vracia (is_valid, [reasons_for_rejection]). Keď je reasons prázdne, položku
    možno akceptovať.
    """
    reasons: list[str] = []

    chyba     = _norm(item.get("mozna_chyba", ""))
    nasledok  = _norm(item.get("mozny_nasledok_chyby", ""))
    pricina   = _norm(item.get("mozna_pricina_mechanizmus_chyby", ""))
    opatrenie = _norm(item.get("doporucene_opatrenia", ""))
    funkcia   = _norm(item.get("funkcia_procesu_pozadavky", ""))

    # ── Minimálna dĺžka kľúčových polí ─────────────────────────────────────────
    if not _looks_meaningful(funkcia):
        reasons.append("slaba_funkcia")
    if not _looks_meaningful(chyba):
        reasons.append("slaba_chyba")
    if not _looks_meaningful(nasledok):
        reasons.append("slaby_nasledok")
    if not _looks_meaningful(pricina):
        reasons.append("slaba_pricina")
    if not _looks_meaningful(opatrenie):
        reasons.append("slabe_opatrenie")

    # ── Chyba / následok / príčina nesmú byť rovnaké ───────────────────────────
    if chyba and chyba == nasledok:
        reasons.append("chyba_rovnaka_ako_nasledok")
    if chyba and chyba == pricina:
        reasons.append("chyba_rovnaka_ako_pricina")
    if nasledok and nasledok == pricina:
        reasons.append("nasledok_rovnaky_ako_pricina")

    # ── Generické frázy ────────────────────────────────────────────────────────
    if VALIDATION_RULES["reject_generic_errors"]:
        if chyba in GENERIC_ERRORS:
            reasons.append("prilis_vseobecna_chyba")
        if opatrenie in GENERIC_ACTIONS:
            reasons.append("prilis_vseobecne_opatrenie")

    # ── Údržbová činnosť ako "chyba" ──────────────────────────────────────────
    if any(word in chyba for word in MAINTENANCE_KEYWORDS):
        reasons.append("neziaduca_chyba_typu_udrzba")

    # ── Opatrenie musí mať aspoň N slov ────────────────────────────────────────
    min_words = VALIDATION_RULES.get("min_opatrenie_words", 2)
    if opatrenie and len(opatrenie.split()) < min_words:
        reasons.append("prilis_kratke_opatrenie")

    return len(reasons) == 0, reasons


def deduplicate_items(items: list[dict]) -> list[dict]:
    """Odstráni presné duplikáty (rovnaká funkcia + chyba + príčina)."""
    seen = set()
    unique = []

    for item in items:
        key = (
            _norm(item.get("funkcia_procesu_pozadavky", "")),
            _norm(item.get("mozna_chyba", "")),
            _norm(item.get("mozna_pricina_mechanizmus_chyby", "")),
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def filter_similar_items(items: list[dict]) -> list[dict]:
    """
    Odstráni položky, ktoré sú príliš podobné už prijatým (substring match
    na chybe + zhoda príčiny, alebo zhoda chyby + zhoda následku).
    """
    result: list[dict] = []

    for item in items:
        chyba    = _norm(item.get("mozna_chyba", ""))
        pricina  = _norm(item.get("mozna_pricina_mechanizmus_chyby", ""))
        nasledok = _norm(item.get("mozny_nasledok_chyby", ""))

        too_similar = False
        for existing in result:
            ex_chyba    = _norm(existing.get("mozna_chyba", ""))
            ex_pricina  = _norm(existing.get("mozna_pricina_mechanizmus_chyby", ""))
            ex_nasledok = _norm(existing.get("mozny_nasledok_chyby", ""))

            if chyba == ex_chyba and pricina == ex_pricina:
                too_similar = True
                break
            if chyba == ex_chyba and nasledok == ex_nasledok:
                too_similar = True
                break
            if (chyba in ex_chyba or ex_chyba in chyba) and pricina == ex_pricina:
                too_similar = True
                break

        if not too_similar:
            result.append(item)

    return result


def validate_and_filter_items(items: list[dict]) -> tuple[list[dict], dict]:
    """
    Hlavná entry point – aplikuje pravidlá + deduplikáciu + podobnostný filter.
    Vracia (accepted_items, stats_dict).
    """
    validation_stats: dict = {
        "input_count": len(items),
        "rejected_count": 0,
        "accepted_count": 0,
        "reasons": {},
    }

    accepted: list[dict] = []
    for item in items:
        ok, reasons = validate_item(item)
        if ok:
            accepted.append(item)
            validation_stats["accepted_count"] += 1
        else:
            validation_stats["rejected_count"] += 1
            for reason in reasons:
                validation_stats["reasons"][reason] = (
                    validation_stats["reasons"].get(reason, 0) + 1
                )

    accepted = deduplicate_items(accepted)
    accepted = filter_similar_items(accepted)

    validation_stats["final_count"] = len(accepted)
    return accepted, validation_stats 