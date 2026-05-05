"""
scoring.py – deterministický výpočet S / O / D a RPN.

Keyword-katalógy sú koncipované všeobecne (naprieč odvetviami: strojárstvo,
elektronika, potravinárstvo, farmácia, chémia, služby). Sektorovo špecifické
termíny (automotive, aerospace, medical) sú tolerované – zachytávajú sa cez
generické rodičovské pojmy:
    "zlyhani bezpečnostnej funkcie"    → automotive "zlyhanie brzdy"
    "vážne ohrozenie používateľa"      → medical "pacient riziko"
    "kontaminácia produktu"             → food/pharma
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

    # S=10: bezpečnosť bez varovania / KONKRÉTNE kritické ohrozenie ľudí
    # POZN: Generické formulácie ("ohrozenie bezpečnosti", "strata bezpečnostnej
    # funkcie") sú zámerne odstránené – AI ich nadpoužíva v reťazcoch následkov
    # aj pri chybách, ktoré primárne nie sú bezpečnostné. Vyžadujeme buď
    # konkrétny typ úrazu, konkrétny zlyhaný bezpečnostný systém, alebo
    # explicitnú kombináciu so smrteľným/havarijným kontextom.
    if _has(combined,
            # Generické bezpečnostné signály – LEN ak sú silné
            "ohrozenie života", "smrteľné riziko", "smrteľný úraz", "fatálne",
            "kritické zlyhanie bez varovania", "nebezpečný stav bez varovania",
            # Úraz – konkrétny pracovný úraz operátora/pracovníka/používateľa
            "úraz pracovník", "úraz operátor", "úraz používateľ",
            "úraz zákazník", "úraz spotrebiteľ",
            "vážny úraz", "vazny uraz", "pracovný úraz", "pracovny uraz",
            # Poranenie s chronickým dopadom
            "chronické poškodenie zdravia", "chronicke poskodenie zdravia",
            "trvalé poškodenie zdravia", "invalidita",
            "poranenie chrbtice", "poranenie hlavy",
            # Privretie končatín / amputácia
            "privretie končatiny", "privretie koncatiny",
            "privretie ruky", "privretie prsto",
            "amputáci", "amputaci",
            # Výbušné / požiarne situácie
            "požiar", "výbuch", "zadretie motora",
            # Zlyhanie KONKRÉTNEHO bezpečnostného systému
            # (musí byť uvedený konkrétny systém – brzda/airbag/sterilita/dávka)
            "zlyhanie brzd", "zlyhani brzd", "strata brzd",
            "zlyhanie airbag", "zlyhanie ochranného krytu",
            "zlyhanie núdzového zastavenia", "zlyhanie poistného ventilu",
            "strata sterility", "kontaminácia patogén",
            "nesprávne dávkovanie liečiva", "predávkovanie pacient",
            # Dopad – iba ak je explicitne vážny
            "vážne ohrozenie používateľa", "vážne ohrozenie pacienta",
            "vážne ohrozenie osôb", "vážne ohrozenie operátora"):
        return 10

    # S=9: vážne bezpečnostné riziko s varovaním / produkt recall
    if _has(combined,
            "bezpečnostné riziko", "kritické zlyhanie", "kritická porucha",
            "bezpečnostná chyba",
            # Generický "bezpečnostný dopad" (nešpecifikovaný, ale vážny)
            "bezpečnostný dopad", "bezpečnostným dopadom",
            "bezpečnostnym dopadom",
            "potenciálnym bezpečnostným", "potencialnym bezpecnostnym",
            "potenciálny bezpečnostný",
            # Strata bezpečnostnej funkcie – generická formulácia tu, nie v S=10,
            # pretože AI ju nadpoužíva ako defaultné dotiahnutie reťazca.
            # Konkrétne zlyhanie brzd/airbagu/ochranného krytu zostáva v S=10.
            "strata bezpečnostnej funkcie", "zlyhani bezpečnostnej funkcie",
            "zlyhani ochrannej funkcie", "strata ochrany",
            "ohrozenie bezpečnosti", "ohrozenie zdravia",
            "ohrozenie používateľa", "ohrozenie osôb",
            "strata kontroly zariaden", "strata kontroly stroja",
            "havária",
            # Zdravotné / hygienické (food, pharma, medical)
            "zdravotné riziko", "kontaminácia produktu", "toxický",
            "alergén", "patogén", "nežiaduci účinok",
            # Recall / stiahnutie trhu
            "stiahnutie z trhu", "stiahnutia produktov", "recall",
            "masívna reklamácia"):
        return 9

    # S=8: strata základnej funkcie produktu / nefunkčný výrobok
    if _has(nasledok,
            # Nefunkčnosť – všeobecne
            "nefunkčný výrobok", "nefunkčný produkt", "nefunkčná zostava",
            "strata základnej funkcie", "strata hlavnej funkcie",
            "strata funkcie", "zmontovan nefunkčn",
            "nefunkčnosť zostavy", "nefunkčnosť", "spôsobiť nefunkčn",
            "stratí funkčnú spoľahlivosť",
            "zostava nebude spĺňať",
            # Zákazník dostane NOK produkt
            "dodanie nefunkčného", "dodanie chybného",
            # Nekompatibilné / falošne vyhovujúce
            "nekompatibilné diely", "nekompatibil",
            "falošne vyhovujúci spoj", "falošne vyhovujúci výstup",
            # Kritické parametre mimo toleranciu
            "predpätie", "nie je možné dosiahnuť predpísané",
            "uvoľnenie a strata funkcie",
            # Vystúpenie dielu z uloženia v prevádzke
            "uvoľnenie čapu počas prevádzky", "uvolnenie capu pocas prevadzky",
            "vypadnutie dielu", "vypadnutie komponent"):
        return 8

    # S=7: závažná funkčná / montážna chyba s priamym dopadom na produkt
    if _has(nasledok,
            # Funkčné zlyhania (generické)
            "funkčné zlyhanie", "funkčné problémy", "funkčná spoľahlivosť",
            "čiastočná strata funkcie", "obmedzená funkčnosť",
            "výrazne znížená výkonnosť", "zníženie spoľahlivosti",
            # Mechanika / montáž (strojárstvo)
            "uvoľnenie zostavy", "zostava sa môže uvoľniť", "uvoľnenie dielu",
            # Uvoľnenie počas prevádzky – mechanické zlyhanie, nie automaticky
            # bezpečnostné. Ak by malo bezpečnostný dopad (brzda, riadenie,
            # ochranný kryt), AI to vyjadrí konkrétnym systémom a S=10 sa
            # spustí cez tie keywordy.
            "uvoľnenie počas prevádzky", "uvoľnenie pocas prevadzky",
            "zlyhani počas prevádzky", "zlyhani pocas prevadzky",
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
            "mimo požadovaný moment", "mimo predpísaný moment",
            "mimo požadovaný rozsah", "nekompatibi",
            "poškodenie skrutkového spoja", "poškodeniu skrutkového",
            "poškodenie závitu", "poškodeniu závitu",
            "zníženie životnosti spoja", "zníženiu životnosti", "prítlačná sila",
            "nesprávnu funkciu zostavy", "nedosadne správne na hriadeľ",
            "nesprávnu polohu pri", "chybné polohovaní",
            # Elektronika / elektrotechnika
            "elektrické zlyhanie", "skrat", "prerušenie obvodu",
            "stratený signál", "nesprávny výstupný signál",
            "degradácia signálu", "rušenie signálu",
            # Software / data
            "nesprávny výsledok", "nesprávna hodnota na výstupe",
            "chybný výpočet", "strata dát", "korupcia dát",
            # Chemické / procesné
            "mimo tolerancie receptúry", "chybná koncentrácia",
            "nesprávne pomerovanie", "nesprávna dávka",
            # Food / pharma
            "zmena organoleptických vlastností", "prekročenie špecifikácie"):
        return 7

    # S=6: znížená kvalita / reklamácia / nutnosť prepracovania
    if _has(nasledok,
            "reklamácia zákazníka", "reklamácia",
            "nezhoda produktu", "nezhoda výrobku", "nezhoda u zákazníka",
            "nezhodný produkt", "zadržanie produkcie",
            "únik nezhodného", "uvoľnenie nezhodného výrobku",
            "chybná poloha", "riziko nezhodného produktu",
            "nutnosť opravy", "nutnosť prepracovania",
            "kvalitatívnej nezhody", "riziko kvalitatívn", "riziko nezhody",
            "obsahovať neoverený", "neoverený materiál",
            "znížená kvalita", "znížená výkonnosť"):
        return 6

    # S=5: viditeľná alebo detegovateľná chyba s obmedzeným dopadom
    if _has(nasledok,
            "viditeľná vada", "povrchová vada", "estetická chyba",
            "preukázaná zhoda spoja", "zhoda spoja",
            "sledovateľnosť výrobku",
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

# Sila opatrenia – podľa hierarchie efektivity opatrení:
#   1 (najsilnejšie) = eliminácia / zmena konštrukcie
#   2 = automatické zabránenie (poka-yoke, mistake-proofing, interlock)
#   3 = automatické odhalenie (100 % senzor, kamera)
#   4 = zvýšená manuálna kontrola
#   5 (najslabšie) = školenie, inštrukcie, vizuálne označenia
#
# Silnejšie opatrenia vedú k DRAMATICKÉMU zníženiu O a D, nie len -1 -2.

def _classify_action(opatrenia: str) -> dict:
    t = str(opatrenia).lower()
    return {
        # Úroveň 1: eliminácia / zmena návrhu (znižuje S)
        "sev_elimination": _has(t,
            "eliminovať následok", "odstrániť bezpečnostné riziko",
            "zmeniť konštrukciu", "upraviť konštrukciu", "zmeniť návrh",
            "nahradiť materiál", "zmeniť materiál"),

        # Úroveň 2: silná PREVENCIA – fyzicky / systémovo znemožní chybu
        #   → O klesne takmer na 1 (poka-yoke, interlock, automatizácia)
        "prev_strong": _has(t,
            "poka-yoke", "pokayoke", "mistake proofing", "mistake-proofing",
            "automatizovať proces", "plne automatizovať",
            "jednoznačné polohovanie", "geometrické vylúčen",
            "mes blok", "mes interlock", "systémový interlock", "interlock",
            "blokovanie operácie", "blokovanie pokračovania",
            "zablokovať operáciu", "zablokovať pokračovanie",
            "znemožni", "znemozni",
            "fyzické oddelenie", "fyzicke oddelenie",
            "plne automatické"),

        # Úroveň 2 mierna: systémové blokovanie, ale nie úplné
        "prev_medium_strong": _has(t,
            "implementovať automatick", "automatické potvrdenie",
            "automatické zablokovan", "systémové overenie",
            "digitálne párovanie", "fyzicky oddelené pozície"),

        # Úroveň 4-5: mäkké opatrenia – O klesne iba o 1-2
        "prev_medium": _has(t,
            "zaviesť", "nastaviť", "štandardizovať", "preškoliť",
            "školenie", "kalibr", "údržb", "vizuálne označenie",
            "pracovnú inštrukciu", "spresniť postup", "checklist",
            "doplniť povinný", "označiť", "prepoj"),

        # Úroveň 3: silné ODHALENIE – 100% automatická kontrola
        #   → D klesne takmer na 1-2
        "det_very_strong": _has(t,
            "100 % automatick", "100% automatick",
            "100 % kontrola s blokovan", "100% kontrola s blokovan",
            "automatické meranie so zastaven", "automaticke meranie so zastaven",
            "kamerová kontrola s blokov", "kamera s blokov",
            "senzor s blokovan"),

        "det_strong": _has(t,
            "automatická kontrola", "automatické meranie",
            "automatick",    # pokrýva aj "automatickú kamerovú kontrolu" atď.
            "100 % kontrola", "100% kontrola",
            "senzor", "kamerov", "kamera",    # kamerovú, kamerová, ...
            "kontrolný prípravok", "stop pri chybe",
            "blokovanie uvoľnenia", "blokácia", "zablokuj",
            "automatické vyhodnot"),

        "det_medium": _has(t,
            "dodatočná kontrola", "dvojitá kontrola", "vizuálna kontrola",
            "overenie", "kontrola", "potvrdenie", "checklist",
            "doplniť checklist", "povinné bodové potvrdenie",
            "audit"),
    }


def estimate_post_action_values(item: dict) -> dict:
    """
    Odhaduje nové S / O / D po implementácii opatrení.

    Silné opatrenia (poka-yoke, MES interlock, 100 % automatická kontrola)
    dramaticky znižujú O a D na cieľové hodnoty 1-3. Mierne opatrenia
    (školenie, checklist) znižujú len mierne.
    """
    vyznam    = int(item["vyznam"])
    vyskyt    = int(item["vyskyt"])
    odhalenie = int(item["odhalenie"])
    flags     = _classify_action(item.get("doporucene_opatrenia", ""))

    # ── Severity ────────────────────────────────────────────────────────────
    # S sa znižuje iba ak opatrenie priamo eliminuje následok
    # (v praxi zriedkavé – vyžaduje zmenu návrhu produktu).
    if flags["sev_elimination"]:
        novy_vyznam = max(1, vyznam - 2)
    else:
        novy_vyznam = vyznam

    # ── Occurrence ──────────────────────────────────────────────────────────
    # Silné preventívne opatrenie → O klesne na absolútnu cieľovú hodnotu
    # (poka-yoke / interlock = 1-2, systémová blokácia = 2-3, školenie = -1).
    if flags["prev_strong"]:
        novy_vyskyt = min(vyskyt, 2)             # cieľová hodnota ~2
    elif flags["prev_medium_strong"]:
        novy_vyskyt = min(vyskyt, 3)             # cieľová hodnota ~3
    elif flags["prev_medium"]:
        novy_vyskyt = max(1, vyskyt - 1)         # mierne zníženie
    else:
        novy_vyskyt = vyskyt

    # ── Detection ───────────────────────────────────────────────────────────
    # Silné odhalenie → D klesne na cieľovú hodnotu (100 % auto = 1-2).
    if flags["det_very_strong"]:
        nove_odhalenie = min(odhalenie, 2)
    elif flags["det_strong"]:
        nove_odhalenie = min(odhalenie, 3)
    elif flags["det_medium"]:
        nove_odhalenie = max(1, odhalenie - 2)
    else:
        nove_odhalenie = odhalenie

    # Ak je definované opatrenie ale nič sa nezmenilo (slabá formulácia),
    # aspoň symbolické zníženie O o 1.
    opatrenia = str(item.get("doporucene_opatrenia", "")).strip()
    if opatrenia and novy_vyskyt == vyskyt and nove_odhalenie == odhalenie \
       and novy_vyznam == vyznam:
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
    item["klasifikacia"] = assign_classification(item["vyznam"], item["vyskyt"], item)
    return estimate_post_action_values(item)


def calculate_rpn_for_all(items: list[dict]) -> list[dict]:
    return [calculate_rpn(item) for item in items]


def _is_operator_safety(item: dict) -> bool:
    """
    True ak následok / chyba ohrozuje primárne bezpečnosť operátora alebo
    pracovníka v prevádzke (nie produkt).

    Klasické OS situácie:
    - úraz / poranenie pracovníka
    - riziko pri manipulácii (pohyblivé časti, ostré hrany, teplo)
    - chemická expozícia, požiar
    - ergonomické riziko (opakované zdvíhanie, zlá poloha)
    - BOZP / OSHA violácie
    """
    text = (
        str(item.get("mozny_nasledok_chyby", "")) + " " +
        str(item.get("mozna_chyba", "")) + " " +
        str(item.get("mozna_pricina_mechanizmus_chyby", ""))
    ).lower()

    operator_safety_signals = [
        # Úraz / poranenie
        "úraz operátor", "úraz pracovník", "poranenie operátor",
        "poranenie pracovník", "zranenie", "ohrozenie operátor",
        "ohrozenie pracovník", "ohrozenie zdravia pracovník",
        "bezpečnosť operátor", "bezpečnosť pracovník",
        # BOZP / normy
        "bozp", "osha", "porušenie predpisov bozp",
        "bezpečnosť práce", "ergonomick",
        # Expozícia
        "chemická expozícia", "chemicka expozicia",
        "vdychovanie", "popálenie", "opálenie",
        # Manipulácia
        "privretie prsta", "porezanie",
        "zasiahnut pracovník", "zasiahnut operátor",
        "vystrelenie dielu", "odlet dielu",
        "zachytenie končatiny", "zachytenie ruky",
        # Ochrana
        "ochranné pomôcky", "ochranne pomocky", "ochrana pred",
    ]
    return any(k in text for k in operator_safety_signals)


def _is_high_impact_process(item: dict) -> bool:
    """
    True ak následok zaťažuje primárne VÝROBNÝ PROCES (prestoje, prepracovanie,
    znížená efektivita) a nie priamo zákazníka či produkt.

    HI je opak SC: SC je "dôležité pre zákazníka", HI je "dôležité pre proces".
    """
    text = (
        str(item.get("mozny_nasledok_chyby", "")) + " " +
        str(item.get("mozna_pricina_mechanizmus_chyby", ""))
    ).lower()

    process_impact_signals = [
        "prestoj", "zastaven", "zastavenie linky", "zastavenie stroja",
        "prerušenie procesu", "prerušenie výroby",
        "prepracovanie v rámci procesu", "interné prepracovanie",
        "dodatočné operácie", "nutnosť preverenia",
        "zníženie efektivity", "znížená efektivita",
        "zvýšené náklady procesu",
        "predĺžený taktový čas", "predĺženie taktu",
        "zvýšený zmätk", "zvýšený odpad",
        "prepracovani mimo", "blokovanie dávky",
        "zdržanie na operácii", "zdrzanie na operacii",
    ]
    customer_impact_signals = [
        "zákazník", "zakaznik", "u zákazníka", "reklamáci",
        "dodanie", "expedíci", "expedici",
        "v prevádzke", "nasadení u zák",
    ]

    has_process = any(k in text for k in process_impact_signals)
    has_customer = any(k in text for k in customer_impact_signals)

    # Len ak ide PRIMÁRNE o proces a nie o zákazníka
    return has_process and not has_customer


def assign_classification(s: int, o: int, item: dict = None) -> str:
    """
    Klasifikácia špeciálnej charakteristiky podľa štandardnej FMEA metodiky.

    Rozhodovanie:
    - S = 9 alebo 10  →  CC (produkt / používateľ) alebo OS (operátor)
    - S = 5 – 8       →  SC (zákazník) alebo HI (proces)
                         (O neovplyvňuje klasifikáciu, iba prioritu opatrení;
                          chyby so S=5-8 sú vždy "significant")
    - S = 4, O ≥ 4    →  SC (sledovateľnosť / kvalita)
    - S ≤ 3           →  bez klasifikácie (bežná charakteristika)

    Rozlíšenie CC vs OS a SC vs HI sa robí cez keyword analýzu následku/chyby.
    Ak item nie je dodané (backward-compat s pôvodným API), použije sa len
    S/O rozhodnutie a vráti sa CC / SC (default-y).
    """
    # Vysoká závažnosť → CC alebo OS (nezávisle od O)
    if s >= 9:
        if item is not None and _is_operator_safety(item):
            return "OS"
        return "CC"

    # Stredná závažnosť → SC alebo HI (nezávisle od O)
    if 5 <= s <= 8:
        if item is not None and _is_high_impact_process(item):
            return "HI"
        return "SC"

    # S = 4, O ≥ 4 – sledovateľnosť / kvalita ako SC
    if s == 4 and o >= 4:
        return "SC"

    return "" 