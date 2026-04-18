"""
scoring.py – deterministický výpočet S / O / D a RPN.

Hlavná oprava: score_vyznam má oveľa širšiu detekciu
slovenskej automotive terminológie – predchádza uniformnému S=5.
"""


def _clamp(value: int, lo: int = 1, hi: int = 10) -> int:
    return max(lo, min(hi, int(value)))


def _has(text: str, *keywords) -> bool:
    t = str(text).lower()
    return any(kw in t for kw in keywords)


def _score_text(*texts: str) -> str:
    return " ".join(str(t).lower() for t in texts)


# ── Význam (Severity) ──────────────────────────────────────────────────────────

def score_vyznam(item: dict) -> int:
    chyba    = str(item.get("mozna_chyba", "")).lower()
    nasledok = str(item.get("mozny_nasledok_chyby", "")).lower()
    combined = chyba + " " + nasledok

    # S=10: bezpečnosť bez varovania
    if _has(combined,
            "ohrozenie bezpečnosti", "ohrozenie zdravia", "havária",
            "kritické zlyhanie bez varovania", "nebezpečný stav",
            "zadretie", "úraz pracovníka", "požiar", "výbuch"):
        return 10

    # S=9: bezpečnosť s varovaním / kritické riziko
    if _has(combined,
            "bezpečnostné riziko", "kritické zlyhanie", "kritická porucha",
            "ohrozenie zdravia", "bezpečnostná chyba"):
        return 9

    # S=8: strata základnej funkcie produktu / nefunkčná zostava
    if _has(nasledok,
            "nefunkčnosť rozvodu", "nefunkčný rozvod",
            "zostava nebude spĺňať", "nefunkčná zostava", "nefunkčný výrobok",
            "strata základnej funkcie", "strata funkcie motora",
            "nekompatibilné diely", "zostava z nekompatibilných",
            "prenos pohybu", "prenosu pohybu",
            "falošne vyhovujúci spoj",
            "predpätie", "nie je možné dosiahnuť predpísané",
            "uvoľnenie a strata funkcie", "stratí funkčnú spoľahlivosť",
            "bezpečnostne a funkčne dôležitého spoja",
            "nie je preukázaná zhoda bezpečnostne",
            "nevyhovujúce predpätie spoja"):
        return 8

    # S=7: závažná funkčná / montážna chyba s priamym dopadom na produkt
    if _has(nasledok,
            "funkčné zlyhanie", "funkčné problémy", "funkčná spoľahlivosť",
            "uvoľnenie zostavy", "zostava sa môže uvoľniť", "uvoľnenie dielu",
            "poškodenie zostavy", "nesprávna poloha zostavy",
            "nesprávne polohovanie", "nesprávna axiálna", "axiálna vôľa",
            "nepresný prenos", "zlyhanie prenosu momentu",
            "nedotiahnutý spoj", "pretiahnutý spoj", "nezhodná zostava",
            "uvoľnenie nezhodnej", "chybná montáž",
            "nesprávne usadenie", "nesprávna orientácia zostavy",
            "nepresné polohovanie dielov", "problémy rozvodu",
            "montážne problémy", "ohrozenie funkcie zostavy",
            "axiálne vedenie", "axiálnej vôle", "axiálnu vôľu", "axiálnej vôli",
            "nesprávnu polohu zostavy", "nesprávne polohovaný",
            "nesprávny moment", "nesprávny uhol dotiahnutia",
            "poškodenie skrutkového spoja", "poškodeniu skrutkového", "poškodenie závitu", "poškodeniu závitu",
            "zníženie životnosti spoja", "zníženiu životnosti", "prítlačná sila",
            "nesprávnu funkciu zostavy", "nedosadne správne na hriadeľ",
            "nesprávnu polohu pri", "chybné polohovaní"):
        return 7

    # S=6: znížená kvalita / reklamácia / nutnosť prepracovania
    if _has(nasledok,
            "reklamácia zákazníka", "reklamácia",
            "nezhoda produktu", "nezhoda výrobku", "nezhoda u zákazníka",
            "nezhodný produkt", "zadržanie produkcie",
            "únik nezhodného", "uvoľnenie nezhodného výrobku",
            "chybná poloha", "riziko nezhodného produktu",
            "nutnosť opravy", "nutnosť prepracovania",
            "znížená kvalita", "znížená výkonnosť"):
        return 6

    # S=5: viditeľná alebo detegovateľná chyba s obmedzeným dopadom
    if _has(nasledok,
            "viditeľná vada", "povrchová vada", "estetická chyba",
            "zákazník si všimne", "nedostatok kvality",
            "interné prepracovanie", "triedenie"):
        return 5

    # S=4: sledovateľnosť / traceability / administratívny dopad
    if _has(nasledok,
            "sledovateľnosť", "traceability", "sledovateľnosti",
            "nie je možné identifikovať", "nie je možné spätne dohľadať",
            "chybný záznam", "neplatný záznam", "neplatná sledovateľnosť",
            "zablokovať dotknuté", "identifikovať dotknuté diely",
            "preukázať zhodu zákazníkovi", "neúplná evidencia",
            "administratívny nesúlad",
            "nie je možné jednoznačne priradiť",
            "montážne a kontrolné dáta", "priradiť montážne"):
        return 4

    # S=3: minimálny dopad / ľahko opraviteľné
    if _has(nasledok,
            "drobná odchýlka", "minimálny dopad", "ľahko opraviteľné",
            "lokálna úprava", "zanedbateľný dopad"):
        return 3

    # default: stredná závažnosť – neznámy typ dopadu
    return 5


# ── Výskyt (Occurrence) ────────────────────────────────────────────────────────

def score_vyskyt(item: dict) -> int:
    chyba    = str(item.get("mozna_chyba", "")).lower()
    pricina  = str(item.get("mozna_pricina_mechanizmus_chyby", "")).lower()
    prevencia = str(item.get("pouzivane_metody_prevencie", "")).lower()

    base = 5

    # zvyšujúce – príčina je riziková
    if _has(pricina,
            "ľudská chyba", "nepozornosť", "nezaškolený operátor",
            "zámena dielu", "nesprávne nastavenie", "opotrebovaný prípravok",
            "nekalibrované meradlo", "chýba štandard", "nie je definovaný postup",
            "nejednoznačné pracovné inštrukcie"):
        base += 2

    if _has(pricina, "opakovaný problém", "častý výskyt", "chronický"):
        base += 3

    # zvyšujúce – typ chyby je bežný
    if _has(chyba,
            "zámena dielu", "nedotiahnutie", "nesprávne usadenie",
            "nesprávna orientácia", "chýbajúci záznam",
            "vynechal", "zabudol"):
        base += 1

    # znižujúce – príčina je vzácna
    if _has(pricina, "sporadický", "náhodný", "občasný", "ojedinelý", "vzácny",
            "výpadok komunikácie", "výpadok systému"):
        base -= 1

    # znižujúce – silná prevencia (poka-yoke, automatika, MES blokovanie)
    if _has(prevencia,
            "poka-yoke", "automatické blokovanie", "systémové overenie",
            "digitálne párovanie", "jednoznačné polohovanie",
            "prípravok so zámkom", "skener", "skenovanie kódu",
            "mistake proofing", "blokovanie operácie", "blokovanie pokračovania",
            "blokovanie uvoľnenia", "mes blok"):
        base -= 3

    # znižujúce – stredná prevencia
    elif _has(prevencia,
              "pracovná inštrukcia", "školenie operátora", "preventívna údržba",
              "kalibrácia", "vizuálne označenie", "kontrola pripravenosti",
              "štandardizovaný postup", "checklist", "pracovný štandard",
              "pracovný postup"):
        base -= 1

    return _clamp(base)


# ── Odhalenie (Detection) ──────────────────────────────────────────────────────

def score_odhalenie(item: dict) -> int:
    detection = str(item.get("pouzivane_metody_odhalenia", "")).lower()
    prevencia = str(item.get("pouzivane_metody_prevencie", "")).lower()

    # D=1: poka-yoke – chyba nemôže vzniknúť
    if _has(prevencia,
            "poka-yoke", "mistake proofing", "blokovanie operácie",
            "automatické zamedzenie chyby"):
        return 1

    # D=2: automatická kontrola so zastavením procesu
    if _has(detection,
            "automatická kontrola", "automatické meranie", "kamerová kontrola",
            "senzor", "stop pri chybe", "elektronické overenie",
            "okamžitý nok signál", "blokovanie uvoľnenia dielu pri"):
        return 2

    # D=3: 100 % kontrola prípravkom / funkčným testom / momentom
    if _has(detection,
            "100 % kontrola", "100% kontrola", "kontrolný prípravok",
            "funkčný test", "momentová kontrola", "meranie momentu",
            "online monitorovanie momentu", "online monitorovanie"):
        return 3

    # D=4: kontrola na nasledujúcom kroku / prvý kus / dvojitá kontrola
    if _has(detection,
            "kontrola prvého kusu", "nasledujúci krok", "medzioperačná kontrola",
            "dvojitá kontrola", "vrstvený procesný audit",
            "kontrola v mes", "blokovanie pokračovania v mes",
            "kontrola prítomnosti a platnosti záznamu"):
        return 4

    # D=5: meranie / SPC / overenie záznamu v systéme / 100% vizuálna
    if _has(detection,
            "meranie", "spc", "štatistická kontrola",
            "overenie záznamu", "kontrola povinných polí",
            "spätná väzba o chýbajúcom zázname",
            "100 % vizuálna", "100% vizuálna",
            "kontrola zhody identifikátora"):
        return 5

    # D=6: audit / sledovanie v systéme / dokumentácia
    if _has(detection,
            "audit", "procesný audit", "spätná kontrola",
            "kontrola traceability", "overenie záznamu pri audite"):
        return 6

    # D=7: vizuálna kontrola operátorom (bežná)
    if _has(detection,
            "vizuálna kontrola", "vizualne overenie", "vizuálne overenie",
            "vizuálne potvrdenie", "manuálna kontrola"):
        return 7

    # existuje nejaká kontrola, ale nie je bližšie popísaná
    if detection.strip():
        return 6

    # žiadna kontrola
    return 9


# ── Odhad hodnôt po opatreniach ────────────────────────────────────────────────

def _classify_action(opatrenia: str) -> dict:
    t = str(opatrenia).lower()
    return {
        "prev_strong": _has(t,
            "poka-yoke", "zablokovať", "blokovanie", "automatizovať",
            "jednoznačné polohovanie", "upraviť prípravok", "digitálne párovanie",
            "skener", "senzor", "systémové overenie", "blokovanie operácie",
            "zablokuj", "implementovať automatick", "automatické potvrdenie"),
        "prev_medium": _has(t,
            "zaviesť", "nastaviť", "štandardizovať", "preškoliť",
            "školenie", "kalibr", "údržb", "vizuálne označenie",
            "pracovnú inštrukciu", "spresniť postup", "checklist",
            "doplniť povinný", "označiť", "prepoj"),
        "det_strong": _has(t,
            "automatická kontrola", "automatické meranie", "100 % kontrola",
            "100% kontrola", "senzor", "test", "skener",
            "kontrolný prípravok", "stop pri chybe", "kamerová kontrola",
            "blokovanie uvoľnenia", "blokácia", "zablokuj"),
        "det_medium": _has(t,
            "dodatočná kontrola", "dvojitá kontrola", "vizuálna kontrola",
            "overenie", "kontrola", "potvrdenie", "checklist",
            "doplniť checklist", "povinné bodové potvrdenie"),
        "sev_reduction": _has(t,
            "zmeniť konštrukciu", "upraviť konštrukciu", "zmeniť návrh",
            "eliminovať následok", "odstrániť bezpečnostné riziko"),
    }


def estimate_post_action_values(item: dict) -> dict:
    vyznam    = int(item["vyznam"])
    vyskyt    = int(item["vyskyt"])
    odhalenie = int(item["odhalenie"])
    flags     = _classify_action(item.get("doporucene_opatrenia", ""))

    novy_vyznam    = max(1, vyznam - 1)    if flags["sev_reduction"] else vyznam
    novy_vyskyt    = max(1, vyskyt - 3)   if flags["prev_strong"]   else \
                     max(1, vyskyt - 1)   if flags["prev_medium"]   else vyskyt
    nove_odhalenie = max(1, odhalenie - 4) if flags["det_strong"]   else \
                     max(1, odhalenie - 2) if flags["det_medium"]   else odhalenie

    # ak žiadne zlepšenie ale opatrenie existuje → aspoň -1 výskyt
    opatrenia = str(item.get("doporucene_opatrenia", "")).strip()
    if opatrenia and novy_vyskyt == vyskyt and nove_odhalenie == odhalenie:
        novy_vyskyt = max(1, vyskyt - 1)

    item["novy_vyznam"]    = novy_vyznam
    item["novy_vyskyt"]    = novy_vyskyt
    item["nove_odhalenie"] = nove_odhalenie
    item["novy_rpn"]       = novy_vyznam * novy_vyskyt * nove_odhalenie
    return item


def calculate_rpn(item: dict) -> dict:
    item["vyznam"]       = score_vyznam(item)
    item["vyskyt"]       = score_vyskyt(item)
    item["odhalenie"]    = score_odhalenie(item)
    item["rpn"]          = item["vyznam"] * item["vyskyt"] * item["odhalenie"]
    item["klasifikacia"] = assign_classification(item["vyznam"], item["vyskyt"])
    return estimate_post_action_values(item)


def calculate_rpn_for_all(items: list[dict]) -> list[dict]:
    return [calculate_rpn(item) for item in items]


def assign_classification(s: int, o: int) -> str:
    """
    Klasifikácia špeciálnej charakteristiky podľa AIAG/VDA PFMEA:
      CC – Critical Characteristic : S ≥ 9  (bezpečnosť / legislatíva)
      SC – Significant Characteristic : S 5–8 A ZÁROVEŇ O ≥ 4
      (prázdne) – bežná charakteristika
    """
    if s >= 9:
        return "CC"
    if 5 <= s <= 8 and o >= 4:
        return "SC"
    return "" 