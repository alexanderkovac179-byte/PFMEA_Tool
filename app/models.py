"""
models.py – typované modely pre FMEA dáta.

Nahrádza neštruktúrované dict-y, ktoré sa predtým prehadzovali medzi
generator → validator → scoring → exporter. Pydantic validuje hodnoty
okamžite po AI výstupe (min dĺžka, rozsahy S/O/D, tvar confidence), takže
chyba sa nedostane až do Excelu ako prázdna bunka.
"""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# Povolené hodnoty klasifikácie (dopĺňa sa deterministicky v scoring.py).
# Prázdny string znamená "bežná charakteristika" – nie je Special Char.
Klasifikacia = Literal["CC", "OS", "SC", "HI", ""]


class FmeaItem(BaseModel):
    """
    Jeden riadok FMEA tabuľky.

    Model je deliberate tolerantný voči neznámym kľúčom vo vstupe (extra="ignore"),
    lebo AI občas vráti navyše pole. String polia sa automaticky trim-ujú.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="ignore",
        validate_assignment=True,
    )

    # ── Polia dodávané AI ──────────────────────────────────────────────────────
    funkcia_procesu_pozadavky: str = Field(min_length=8)
    mozna_chyba: str = Field(min_length=8)
    mozny_nasledok_chyby: str = Field(min_length=8)
    mozna_pricina_mechanizmus_chyby: str = Field(min_length=8)
    pouzivane_metody_prevencie: str = ""
    pouzivane_metody_odhalenia: str = ""
    doporucene_opatrenia: str = Field(min_length=8)
    zodp_pracovnik_datum_ukoncenia: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)

    # ── Polia dopočítavané deterministicky v scoring.py ───────────────────────
    # (0 = ešte neohodnotené; po prechode cez scoring.calculate_rpn_for_all
    # budú v rozsahu 1–10)
    klasifikacia: Klasifikacia = ""
    vyznam: int = Field(ge=0, le=10, default=0)
    vyskyt: int = Field(ge=0, le=10, default=0)
    odhalenie: int = Field(ge=0, le=10, default=0)
    rpn: int = 0

    novy_vyznam: int = Field(ge=0, le=10, default=0)
    novy_vyskyt: int = Field(ge=0, le=10, default=0)
    nove_odhalenie: int = Field(ge=0, le=10, default=0)
    novy_rpn: int = 0

    vysledky_opatreni: str = ""

    # ── Validátory ─────────────────────────────────────────────────────────────
    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        """AI niekedy vráti '85 %' alebo '0,85' namiesto float."""
        if v in (None, ""):
            return 0.5
        if isinstance(v, str):
            v = v.replace(",", ".").replace("%", "").strip()
            try:
                v = float(v)
            except ValueError:
                return 0.5
            if v > 1.0:          # AI vrátila percentá (napr. 85)
                v = v / 100.0
        return max(0.0, min(1.0, float(v)))

    # ── Factory a serializácia ────────────────────────────────────────────────
    @classmethod
    def from_ai_output(cls, raw: dict) -> Optional["FmeaItem"]:
        """
        Skonštruuje FmeaItem z raw AI dictu; pri štruktúrnej chybe vráti None,
        namiesto výnimky. Volajúci má tak možnosť pokračovať pri jednej zlej
        položke (napr. chýbajúca `mozna_chyba`) a neshodiť celý krok.
        """
        try:
            return cls(**raw)
        except Exception:
            return None

    def to_dict(self) -> dict:
        """Serializácia späť na dict pre existujúci exporter / validator."""
        return self.model_dump() 