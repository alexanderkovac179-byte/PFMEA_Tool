"""
owner_assignment.py – priradenie zodpovedného pracovníka pre PFMEA položku.

Logika:
1) Skús nájsť ROLU explicitne spomenutú v doporučenom opatrení alebo v kontexte
   dokumentov (najmä v pracovných inštrukciách, kontrolných plánoch, …).
   Ak je explicitne uvedená, použije sa BEZ hviezdičky.

2) Ak nie je explicitne uvedená, spustí sa vážené skórovanie podľa keywords
   rozdelených do kategórií rolí. Najlepšia rola vyhrá a pripojí sa
   hviezdička – "Skladník*" – čo indikuje, že hodnotu navrhla AI na základe
   kontextu, nie že bola v dokumentoch explicitne uvedená.

Dôležité:
- Hlavný zdroj pre určenie ownera je `doporucene_opatrenia` – to je text, ktorý
  hovorí, ČO sa má urobiť. Ten, kto to urobí, je vlastník opatrenia.
- Príčiny a prevencia sa používajú ako sekundárny signál (nižšia váha).
- Explicitné zmienky typu "Údržba", "QE", "Procesný inžinier" v opatrení
  majú prednosť pred keyword matchingom.
"""

import re
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# 1. Explicitné rolové pattern-y (presne uvedené v texte)
# ─────────────────────────────────────────────────────────────────────────────

ROLE_PATTERNS: list[tuple[str, str]] = [
    # Konkrétne odborné pozície
    (r"\boper[aá]tor(?:ka|i|ov)?\b",              "Operátor"),
    (r"\bved[úu]ci\s+v[ýy]roby\b",                "Vedúci výroby"),
    (r"\bmajster\b",                              "Vedúci výroby"),
    (r"\bprocesn[ýý]\s+in[žz]inier\b",            "Procesný inžinier"),
    (r"\bprocess\s+engineer\b",                   "Procesný inžinier"),
    (r"\bin[žz]inier\s+kvality\b",                "Inžinier kvality"),
    (r"\bquality\s+engineer\b",                   "Inžinier kvality"),
    (r"\btechnik\s+kvality\b",                    "Technik kvality"),
    (r"\bkontrol[óo]r\b",                         "Kontrolór"),
    (r"\bautomatiza[čc]n[ýy]\s+in[žz]inier\b",    "Automatizačný inžinier"),
    (r"\bmes\s+[šs]pecialista\b",                 "IT / Systémový inžinier"),
    (r"\bit\s+[šs]pecialista\b",                  "IT / Systémový inžinier"),
    (r"\bsyst[eé]mov[ýý]\s+in[žz]inier\b",        "IT / Systémový inžinier"),
    (r"\bit\s+in[žz]inier\b",                     "IT / Systémový inžinier"),
    (r"\btechnik\s+[úu]dr[žz]by\b",               "Technik údržby"),
    (r"\b[úu]dr[žz]b(?:a|y|u|e|ou)\b",            "Údržba"),
    (r"\bskladn[ií]k\b",                          "Skladník"),
    (r"\blogistika\b",                            "Logistika"),
    (r"\btechnol[oó]g\b",                         "Technológ"),
    (r"\bpfmea\s+t[ií]m\b",                       "PFMEA tím"),
    (r"\bpfmea\s+team\b",                         "PFMEA tím"),
]

# Text-y, ktoré vyzerajú ako rola ale sú to v skutočnosti názvy procesov/dokumentov
# (typické halucinácie, keď AI píše "podľa pracovnej inštrukcie ..." do owner políčka)
SUSPICIOUS_SUBSTRINGS = [
    "reálnej wi", "pracovnej instrukcie", "pracovná inštrukcia",
    "sériovej montá", "seriovej monta", "používanej v", "podľa wi",
    "vstupných dokumentov", "kontrolného plánu", "sledovateľnosti",
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _find_role(text: str) -> Optional[str]:
    """Vráti názov role, ak je v texte explicitne spomenutá."""
    text = _norm(text)
    for pattern, role in ROLE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return role
    return None


def _is_clean_explicit_owner(text: str) -> bool:
    """
    True iba ak text vyzerá ako legitímna zmienka role
    (nie ako hallucinated popis dokumentu alebo rola ako objekt vety).

    Príklady:
        "Údržba vykoná kalibráciu"         → True  (Údržba je subjekt)
        "preškoliť operátorov"              → False (operátor je objekt)
        "kontrolný plán podľa WI-..."       → False (halucinácia)
        "Technik kvality / 31.12.2024"      → True  (klasický formát owner/dátum)
    """
    if not text:
        return False
    low = _norm(text)
    if any(s in low for s in SUSPICIOUS_SUBSTRINGS):
        return False
    # Dlhé texty s >80 znakmi, ktoré neobsahujú čistú zmienku role, neprijmi
    if len(low) > 80 and _find_role(low) is None:
        return False
    # Ak obsahuje slová dokumentárne povahy (WI, kontrolný plán, …) ale nie rolu
    if re.search(
        r"\b(wi|instrukci|kontroln|kontext|zdroj|oper[aá]ci|mont[aá]ž)\b",
        low,
    ) and _find_role(low) is None:
        return False
    if _find_role(low) is None:
        return False

    # Rola musí byť v akuzatíve/nominatíve ako subjekt, nie objekt slovesa.
    # Odmietneme frázy, kde je rola preceded by slovesom v infinitíve alebo
    # rozkazovacom spôsobe (preškoliť, zaškoliť, informovať, …).
    action_verbs = (
        "preškoli", "preskoli", "zaškoli", "zaskoli", "informova",
        "upozorni", "vyzva", "prizva", "požiada", "poziada",
        "motivova", "trenova", "trénova", "posla", "povola",
    )
    # Ak v texte je „<sloveso> <rola>" – rola je objektom akcie, nie aktérom
    for verb in action_verbs:
        if re.search(rf"\b{verb}\w*\s+\w*(oper[aá]tor|vedúceho|technika|inžiniera)",
                     low):
            return False

    return True


def extract_explicit_owner(*texts: str) -> str:
    """
    Prehľadá texty zhora nadol a vráti prvú legitímnu rolu, ktorú nájde.

    Pozor: "Operátor" sa NIKDY neakceptuje ako explicit owner – operátor je
    vykonávateľ štandardnej práce, nie ten, kto implementuje nápravné opatrenia
    vo FMEA. Ak AI vráti "Operátor", ignoruje sa a spustí sa scoring (ktorý
    vyberie skutočne zodpovednú rolu – napr. Vedúci výroby, Procesný inžinier).
    """
    for text in texts:
        role = _find_role(text)
        if role and role == "Operátor":
            # Operátor nikdy nie je owner FMEA opatrení – preskoč a pokračuj
            continue
        if role and _is_clean_explicit_owner(text):
            return role
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# 2. Vážené skórovanie rolí (keyword matching s váhami)
# ─────────────────────────────────────────────────────────────────────────────

# Každá rola má zoznam keyword-skupín s váhou. Ak sa keyword nájde v texte,
# rola dostane pripočítanú váhu. Na konci rola s najvyšším skóre vyhrá.
#
# Keyword sa hľadá cez `in` – musí byť prefix/substring, nie celé slovo.
# To znamená, že "sken" zasiahne aj "skenovanie" aj "skener".

ROLE_KEYWORD_WEIGHTS: dict[str, list[tuple[list[str], int]]] = {
    # ── Skladník ──────────────────────────────────────────────────────────────
    "Skladník": [
        (["fifo", "skladov", "expira", "exspira", "dátum použit",
          "dátum spotreby", "termín použit", "skladová karta",
          "skladová zásoba", "zásob materiál", "príjem materiálu",
          "výdaj materiálu", "označenie dávky", "skladovanie dielov",
          "balenie na sklade"], 5),
        (["regál", "regal", "obal", "šarža dielov", "sarza dielov"], 3),
    ],

    # ── Logistika ─────────────────────────────────────────────────────────────
    "Logistika": [
        (["logistik", "preprav", "vnútropodnikov", "manipulač", "manipulacn",
          "zaskladnenie", "vyskladnenie", "kanban"], 5),
    ],

    # ── Údržba / Technik údržby ──────────────────────────────────────────────
    "Údržba": [
        (["preventívna údržba", "preventivna udrzba", "plán údržby",
          "servis zariadenia", "výmena nástroja", "výmena dielu stroja",
          "oprava zariaden", "kontrola opotreben", "kalibráci",
          "kalibrác", "servisný interval", "údržb"], 5),
        (["opotrebovaný prípravok", "poškodený prípravok", "oprava prípravku",
          "poškodený nástroj", "opotrebovaný nástroj"], 4),
    ],

    # ── Inžinier kvality / Technik kvality ───────────────────────────────────
    "Inžinier kvality": [
        (["kontrolný plán", "kontrolny plan", "plán kontroly",
          "audit procesu", "výstupná kontrola", "vstupná kontrola",
          "medzioperačná kontrola", "boundary sample", "vzorový diel",
          "etalon", "etalón", "meranie zhody", "rozbor nezhody",
          "analýza reklamáci"], 5),
        (["kontrola kvality", "inšpekci", "inspekci", "ok/nok",
          "kamerový systém", "kamerova kontrola", "optická kontrola",
          "opticka kontrola", "vizuálna kontrola", "vizualna kontrola",
          "meranie rozmeru", "meranie momentu"], 3),
        (["test", "meradl", "meranie"], 1),
    ],

    # ── Procesný inžinier ────────────────────────────────────────────────────
    "Procesný inžinier": [
        (["poka-yoke", "pokayoke", "geometrické vylúčen", "geometricke vylucen",
          "prípravok s", "pripravok s", "upraviť prípravok", "upravit pripravok",
          "úprava prípravku", "uprava pripravku", "design prípravku",
          "nový prípravok", "prepracovať prípravok",
          "process fmea", "revízia procesu", "revizia procesu",
          "zmena technológie", "zmena technologie", "úprava stanice",
          "úprava operácie", "mechanická zábrana", "mechanicka zabrana",
          # Všeobecné procesné zmeny
          "redesign procesu", "optimalizácia procesu", "optimalizacia procesu",
          "úprava receptúry", "zmena receptúry",
          "zmena parametrov procesu", "zmena výrobných parametrov",
          "úprava výrobného postupu"], 5),
        (["prípravok", "pripravok", "technologický postup",
          "technologicky postup", "zmena parametrov", "nastavenie zariadenia",
          "parameter procesu"], 2),
    ],

    # ── IT / Systémový inžinier ──────────────────────────────────────────────
    # Všeobecná rola pre všetko, čo sa týka systémov, databáz, softvéru,
    # interlock-ov, MES/ERP integrácie, IT infraštruktúry.
    # Zahŕňa aj pôvodnú rolu "MES špecialista" (ktorá je typická v automotive,
    # ale pre všeobecnú FMEA je matúca).
    "IT / Systémový inžinier": [
        (["mes blok", "mes systém", "mes system", "systémová blokácia",
          "systemova blokacia", "blokovanie v mes", "mes záznam",
          "mes zaznam", "systémová validácia", "traceability systé",
          "riadiaci systém", "riadiaci system",
          "erp systém", "erp system", "erp",
          "databáza", "databáz", "softvérová validácia",
          "softverova validacia", "it systém pre výrobu",
          "softvérov", "softverov", "software",
          "digitalizáci", "digitalizaci",
          "sharepoint", "dms", "document management",
          "it infraštruktúr", "it infrastruktura"], 5),
        (["interlock", "blokovanie operácie", "blokovanie uvoľnenia",
          "blokovanie pokračovania", "automatické zablokovan",
          "systémové blokovanie", "systemove blokovanie"], 4),
        (["systémové overenie", "systemove overenie", "digitálne párovanie",
          "digitalne parovanie", "elektronický záznam", "elektronicky zaznam"], 3),
    ],

    # ── Automatizačný inžinier ───────────────────────────────────────────────
    "Automatizačný inžinier": [
        (["plc", "automatizáci", "automatizaci", "robotick", "cyklus stroja",
          "program skrutkovača", "program uťahovani", "senzor",
          "optosenzor", "elektrick"], 4),
    ],

    # ── Vedúci výroby ────────────────────────────────────────────────────────
    "Vedúci výroby": [
        (["preškoliť oper", "preskolit oper", "školenie oper", "skolenie oper",
          "zaškoliť oper", "zaskolit oper", "tréning oper", "trening oper",
          "štandardizáci práce", "standardizacia prace",
          "rotácia operátorov", "rotacia operatorov",
          "výmena smeny", "vymena smeny"], 5),
        (["dohľad nad", "dohľad operátor", "dohlad operator",
          "kontrola pracoviska", "pracovný štandard", "pracovny standard",
          "štandardizáci", "standardizaci"], 3),
        (["školen", "skolen"], 1),
    ],

    # ── Technológ (pracovná inštrukcia, WI update) ───────────────────────────
    "Technológ": [
        (["aktualizova pracovn inštrukci", "aktualizovat pracovn instrukci",
          "doplniť pracovn inštrukci", "doplnit pracovn instrukci",
          "zmeniť wi", "zmenit wi", "nová pracovná inštrukc",
          "revízia wi", "revizia wi", "doplnenie postupu", "úprava postupu",
          "doplniť piktogram", "doplnit piktogram",
          "piktogram v pracovn"], 5),
        (["pracovná inštrukcia", "pracovny postup", "technologický postup",
          "technologicky postup"], 2),
    ],

    # POZOR: "Operátor" sa v PFMEA NEPRIRAĎUJE ako owner opatrenia.
    # Operátor pasívne vykonáva nové postupy, ale vlastníkom opatrenia je vždy
    # niekto zo supervízornej/inžinierskej vrstvy (Vedúci výroby, Procesný
    # inžinier, QE, Technik údržby, Technológ …). Preto Operátor nie je
    # v ROLE_KEYWORD_WEIGHTS.
}


def _role_score(text: str) -> dict[str, int]:
    """Spočíta skóre každej role podľa výskytu keywords v texte."""
    scores: dict[str, int] = {}
    for role, groups in ROLE_KEYWORD_WEIGHTS.items():
        score = 0
        for keywords, weight in groups:
            for kw in keywords:
                if kw in text:
                    score += weight
                    break   # v rámci jednej skupiny počítame len raz
        if score > 0:
            scores[role] = score
    return scores


def suggest_owner(
    item: dict,
    krok_procesu: str = "",
    funkcia_kroku: str = "",
    context: str = "",
) -> str:
    """
    Navrhne ownera s hviezdičkou (AI návrh).

    Primárnym zdrojom pre určenie ownera je `doporucene_opatrenia` – ten,
    kto bude opatrenie vykonávať, je owner. Sekundárne sa berie do úvahy
    aj príčina, prevencia, chyba a kontext kroku.
    """
    opatrenia = _norm(item.get("doporucene_opatrenia", ""))
    pricina   = _norm(item.get("mozna_pricina_mechanizmus_chyby", ""))
    prevencia = _norm(item.get("pouzivane_metody_prevencie", ""))
    odhalenie = _norm(item.get("pouzivane_metody_odhalenia", ""))
    chyba     = _norm(item.get("mozna_chyba", ""))
    krok      = _norm(f"{krok_procesu} {funkcia_kroku}")

    # Primárne skóre z opatrení (váha ×3, pretože opatrenia určujú, kto to bude robiť)
    total: dict[str, int] = {}
    for role, score in _role_score(opatrenia).items():
        total[role] = total.get(role, 0) + score * 3

    # Sekundárne skóre z prevencie (×1)
    for role, score in _role_score(prevencia).items():
        total[role] = total.get(role, 0) + score

    # Sekundárne skóre z odhalenia (×1)
    for role, score in _role_score(odhalenie).items():
        total[role] = total.get(role, 0) + score

    # Kontext z príčiny a chyby (×1) – ľudská chyba / nepozornosť → Vedúci výroby
    for role, score in _role_score(pricina).items():
        total[role] = total.get(role, 0) + score

    for role, score in _role_score(chyba).items():
        total[role] = total.get(role, 0) + score

    # Heuristika na "ľudský faktor" v príčine → bonus pre Vedúci výroby
    if any(k in pricina for k in [
        "ľudská chyba", "ludska chyba", "nepozornos", "nedodržan",
        "nedodrzan", "vynechal", "zabudol", "neškolený", "neskoleny",
        "nezaškolený", "nezaskoleny",
    ]):
        total["Vedúci výroby"] = total.get("Vedúci výroby", 0) + 3

    # Špecifiká: "dátum exspirácie", "FIFO" → Skladník bonus
    if any(k in chyba + " " + pricina for k in [
        "exspirác", "expirác", "dátum použit", "fifo",
    ]):
        total["Skladník"] = total.get("Skladník", 0) + 5

    # Deformácia / poškodenie dielu pri vstupe → vstupná kontrola = QE
    if any(k in chyba for k in ["deformác", "poškoden", "korozi", "koróz"]):
        if any(k in pricina + prevencia for k in ["vstupn", "dodávateľ", "dodavatel"]):
            total["Inžinier kvality"] = total.get("Inžinier kvality", 0) + 3

    # Vyber najlepšiu rolu
    if not total:
        # Žiadny match – použij default podľa kontextu kroku
        if any(k in krok for k in ["kontrola", "vyhodnoten", "meran"]):
            return "Inžinier kvality*"
        if any(k in krok for k in ["príprav", "pripav", "nastav"]):
            return "Procesný inžinier*"
        return "Procesný inžinier*"

    best_role = max(total.items(), key=lambda kv: kv[1])[0]
    return f"{best_role}*"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Public API
# ─────────────────────────────────────────────────────────────────────────────

def assign_owner(
    item: dict,
    krok_procesu: str = "",
    funkcia_kroku: str = "",
    context: str = "",
) -> str:
    """
    Hlavný vstupný bod. Vráti jedno z dvoch:
      "Údržba"   – rola bola explicitne uvedená vo vstupných dokumentoch
      ""         – rola nie je známa, pole sa nechá prázdne

    AI vráti hodnotu v poli "zodp_pracovnik_datum_ukoncenia" LEN ak je v
    zdrojových dokumentoch explicitne spomenutá (napr. "Zodpovedný: Technik
    kvality / 31.12.2026" v kontrolnom pláne alebo NCR zázname). Ak nie je,
    pole ostáva prázdne – nerobíme žiadne domnelé návrhy.

    Operátor sa nikdy neakceptuje ako owner (vo FMEA nie je vlastníkom
    nápravných opatrení).

    Kontext (krok_procesu, funkcia_kroku) je zachovaný pre spätnú kompatibilitu
    so starším API, ale pre výpočet ownera sa už nepoužíva.
    """
    # 1. Priamo v poli od AI (extrahované z dokumentu)
    ai_value = item.get("zodp_pracovnik_datum_ukoncenia", "")
    explicit = extract_explicit_owner(ai_value)
    if explicit:
        return explicit

    # 2. V texte opatrenia alebo všeobecnom kontexte (citovanie role zo zdroja)
    explicit = extract_explicit_owner(
        item.get("doporucene_opatrenia", ""),
        context,
    )
    if explicit:
        return explicit

    # 3. Nevieme – vrátime prázdne pole
    return "" 