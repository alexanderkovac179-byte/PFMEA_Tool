VYZNAM_LEGENDA = [
    [
        "Následok",
        "Kritériá pre určenie významnosti z hľadiska následku pre zákazníka / používateľa",
        "Kritériá pre určenie významnosti z hľadiska následku pre proces / organizáciu",
        "Hodnota indexu",
    ],
    [
        "Nebezpečný - bez varovania",
        "Veľmi vysoké hodnotenie významnosti, keď možná chyba výrazne ovplyvní bezpečnosť, zdravie, súlad s požiadavkami alebo spôsobí kritické zlyhanie bez predchádzajúceho varovania.",
        "Môže ohroziť pracovníka, zariadenie, prevádzku alebo viesť ku kritickému prerušeniu procesu bez varovania.",
        10,
    ],
    [
        "Nebezpečný - s varovaním",
        "Veľmi vysoké hodnotenie významnosti, keď možná chyba výrazne ovplyvní bezpečnosť, zdravie, súlad s požiadavkami alebo spôsobí kritické zlyhanie s predchádzajúcim varovaním.",
        "Môže ohroziť pracovníka, zariadenie alebo prevádzku, avšak s predchádzajúcim varovaním.",
        9,
    ],
    [
        "Veľmi vážny",
        "Produkt, služba alebo výstup procesu je nefunkčný alebo dochádza k strate základnej funkcie.",
        "100 % výstupov môže byť vyradených, proces sa zastaví alebo je potrebný zásah iného útvaru s významnou časovou stratou.",
        8,
    ],
    [
        "Vážny",
        "Produkt, služba alebo výstup procesu zostáva funkčný, ale s výrazne zníženou úrovňou výkonnosti. Používateľ je veľmi nespokojný.",
        "Časť výstupov musí byť vyradená alebo prepracovaná, prípadne je potrebný zásah iného útvaru so strednou časovou stratou.",
        7,
    ],
    [
        "Mierny",
        "Funkčnosť zostáva zachovaná, ale niektoré vlastnosti, komfort alebo použiteľnosť sú obmedzené. Používateľ je nespokojný.",
        "Časť výstupov musí byť vyradená alebo prepracovaná s menším dopadom na priebeh procesu.",
        6,
    ],
    [
        "Malý",
        "Výstup je funkčný, ale so zníženou účinnosťou alebo nižšou kvalitou bez zásadného dopadu na základnú funkciu.",
        "Výstupy musia byť prepracované mimo hlavného miesta vykonania operácie, ale bez zásadného narušenia procesu.",
        5,
    ],
    [
        "Veľmi malý",
        "Používateľ si všimne menší nedostatok kvality, vzhľadu, presnosti alebo komfortu. Vadu si všimne väčšina používateľov.",
        "Výstupy musia byť pretriedené alebo čiastočne prepracované bez zásadného dopadu na chod procesu.",
        4,
    ],
    [
        "Nevýznamný",
        "Používateľ si všimne drobný nedostatok len v časti prípadov.",
        "Menšia časť výstupov si vyžaduje lokálnu úpravu alebo opravu bez výrazného dopadu na proces.",
        3,
    ],
    [
        "Úplne nevýznamný",
        "Nedostatok je sotva rozpoznateľný a ovplyvňuje len malú časť používateľov alebo situácií.",
        "Dopad na proces je zanedbateľný a ľahko odstrániteľný na mieste.",
        2,
    ],
    [
        "Žiadny",
        "Bez rozpoznateľného následku pre zákazníka alebo používateľa.",
        "Bez rozpoznateľného následku pre proces, organizáciu alebo pracovníka.",
        1,
    ],
    [
        "Poznámka o norme",
        "Hodnoty a kritériá Významu (Severity) v tejto legende vychádzajú z medzinárodnej normy "
        "IEC 60812:2018 – Failure modes and effects analysis (FMEA and FMECA), príloha A. "
        "Norma definuje rámec hodnotenia; presné kritériá sú prispôsobené pre procesnú FMEA "
        "v automotive odvetví podľa metodiky AIAG & VDA (vydanie 2019).",
        "—",
        "—",
    ],
]


VYSKYT_LEGENDA = [
    [
        "Pravdepodobnosť výskytu",
        "Kritérium hodnotenia",
        "Hodnota indexu",
    ],
    [
        "Veľmi vysoká",
        "Veľmi vysoká pravdepodobnosť výskytu potenciálnej poruchy. "
        "Chyba sa vyskytuje opakovane, často alebo permanentne. "
        "Táto úroveň vyžaduje okamžité opatrenia v procese.",
        "9 – 10",
    ],
    [
        "Vysoká",
        "Vysoká pravdepodobnosť výskytu potenciálnej poruchy. "
        "Chyba sa prejavuje pravidelne a v procese je reálnym rizikom. "
        "Vyžaduje zváženie preventívnych opatrení.",
        "7 – 8",
    ],
    [
        "Stredná",
        "Stredná pravdepodobnosť výskytu potenciálnej poruchy. "
        "Chyba sa môže vyskytnúť príležitostne, proces ju však do značnej miery zvláda.",
        "5 – 6",
    ],
    [
        "Nízka",
        "Nízka pravdepodobnosť výskytu potenciálnej poruchy. "
        "Chyba sa objavuje zriedka a proces je pomerne stabilný.",
        "3 – 4",
    ],
    [
        "Malá",
        "Malá pravdepodobnosť výskytu potenciálnej poruchy. "
        "Chyba je nepravdepodobná, proces je dobre riadený a stabilný.",
        "1 – 2",
    ],
    [
        "Poznámka",
        "Táto časť je v postupe FMEA kľúčová – každá kategória s hodnotením "
        "'veľmi vysoká' alebo 'vysoká' by sa mala zvážiť a riešiť prioritne. "
        "Hodnotenia je možné definovať aj inak podľa metodiky firmy.",
        "—",
    ],
    [
        "Poznámka o norme",
        "Hodnoty a kritériá Výskytu (Occurrence) v tejto legende vychádzajú z medzinárodnej "
        "normy IEC 60812:2018 – Failure modes and effects analysis (FMEA and FMECA), príloha A. "
        "Pri dostupnosti historických dát o nezhodách sa odporúča hodnoty výskytu kalibrovať "
        "podľa skutočnej štatistiky procesu.",
        "—",
    ],
]


ODHALENIE_LEGENDA = [
    [
        "Odhalenie",
        "Kritérium",
        "Typ kontroly A",
        "Typ kontroly B",
        "Typ kontroly C",
        "Predpokladaný rozsah kontroly",
        "Hodnota indexu",
    ],
    [
        "Prakticky nemožné",
        "Prakticky istota, že sa chyba neodhalí",
        "",
        "",
        "X",
        "Chybu nie je možné odhaliť alebo nie je zavedená vhodná kontrola.",
        10,
    ],
    [
        "Veľmi nepatrná možnosť",
        "Pravdepodobne neodhalí",
        "",
        "",
        "X",
        "Nepriama, náhodná alebo neúplná kontrola.",
        9,
    ],
    [
        "Nepatrná možnosť",
        "Malá šanca odhaliť",
        "",
        "",
        "X",
        "Iba jednoduchý vizuálny spôsob kontroly.",
        8,
    ],
    [
        "Veľmi malá možnosť",
        "Malá šanca odhaliť",
        "",
        "",
        "X",
        "Opakovaná vizuálna alebo manuálna kontrola s obmedzenou spoľahlivosťou.",
        7,
    ],
    [
        "Malá možnosť",
        "Môže odhaliť",
        "",
        "X",
        "X",
        "Grafický záznam, trendovanie alebo štatistické sledovanie procesu.",
        6,
    ],
    [
        "Priemerná možnosť",
        "Môže odhaliť",
        "",
        "X",
        "",
        "Kontrola meraním parametra alebo 100 % kontrola výstupu po vykonaní operácie.",
        5,
    ],
    [
        "Nadpriemerná možnosť",
        "Dobrá šanca odhaliť",
        "X",
        "X",
        "",
        "Kontrola na nasledujúcom kroku procesu alebo kontrola po nastavení a prvom kuse.",
        4,
    ],
    [
        "Veľká možnosť",
        "Dobrá šanca odhaliť",
        "X",
        "X",
        "",
        "Kontrola na pracovnom mieste alebo na nasledujúcom kroku s viacnásobným overením. Chybný výstup sa s vysokou pravdepodobnosťou neprepustí ďalej.",
        3,
    ],
    [
        "Veľmi veľká možnosť",
        "Väčšinou istota, že odhalí",
        "X",
        "X",
        "",
        "Automatické meranie alebo automatická kontrola so zastavením procesu pri výskyte chyby.",
        2,
    ],
    [
        "Takmer istá detekcia",
        "Chybe je zabránené konštrukciou",
        "X",
        "",
        "",
        "Chyba prakticky nemôže vzniknúť, pretože jej bráni konštrukcia riešenia, technické zabezpečenie alebo princíp poka-yoke.",
        1,
    ],
    [
        "Poznámka o norme",
        "Hodnoty a kritériá Odhalenia (Detection) v tejto legende vychádzajú z medzinárodnej "
        "normy IEC 60812:2018 – Failure modes and effects analysis (FMEA and FMECA), príloha A. "
        "Norma uvádza odhalenie ako voliteľný parameter; v procesnej FMEA je jeho použitie bežnou "
        "praxou pre výpočet RPN (Risk Priority Number = S × O × D).",
        "—",
        "—",
        "—",
        "—",
        "—",
    ],
]


KLASIFIKACIA_LEGENDA = [
    [
        "Skratka",
        "Kategória (Special Characteristic)",
        "Kritérium FMEA",
        "Popis charakteristiky",
        "Požiadavky na riadenie / poznámka",
    ],
    [
        "CC",
        "Kritická (Critical Characteristic)",
        "Význam (S) = 9 alebo 10",
        "Parametre produktu alebo požiadavky, ktoré môžu ovplyvniť súlad so zákonnými reguláciami, bezpečnosť koncového používateľa alebo zákazníka, prípadne bezpečnú funkciu výrobku alebo poskytovanej služby.",
        "Vyžaduje špeciálne opatrenia a riadenie, ktoré musia byť uvedené v Control Plane (Plán riadenia). Sledované so zvýšenou kontrolou.",
    ],
    [
        "OS",
        "Bezpečnosť operátora (Operator Safety)",
        "Význam (S) = 9 alebo 10",
        "Parametre, ktoré priamo neovplyvňujú produkt, ale môžu mať dopad na bezpečnosť operátora alebo súlad s predpismi BOZP, hygieny práce a ochrany zdravia pri práci. Predstavujú riziko pre pracovníkov v prevádzke.",
        "Musia byť zahrnuté v bezpečnostnom podpísaní (safety signoff) a pracovnom postupe pre daný krok procesu.",
    ],
    [
        "SC",
        "Významná (Significant Characteristic)",
        "Význam (S) = 5 – 8",
        "Parametre produktu a požiadavky, ktoré sú dôležité pre spokojnosť zákazníka, ale nepredstavujú bezpečnostné riziko. Priorita opatrení sa stupňuje podľa hodnoty Výskytu (O).",
        "Opatrenia plánovania kvality (Quality Planning) musia byť zdokumentované v Control Plane.",
    ],
    [
        "HI",
        "Vysoký dopad (High Impact Characteristic)",
        "Význam (S) = 5 – 8",
        "Parametre, ktoré pri prekročení tolerancie výrazne ovplyvnia priebeh procesu alebo nasledujúcich operácií (prestoje, prepracovanie, znížená efektivita). Priorita opatrení sa stupňuje podľa hodnoty Výskytu (O).",
        "Sledované v rámci riadenia procesu; odporúča sa zaradiť do Control Planu pre daný krok alebo operáciu.",
    ],
    [
        "Dôležité upozornenie",
        "—",
        "—",
        "Klasifikácia špeciálnej charakteristiky sa priraďuje podľa hodnotení Význam (S) a Výskyt (O) daného riadku FMEA. "
        "Klasifikácia vychádza z normy IEC 60812:2018 (Failure modes and effects analysis), "
        "rozšírenej o automotive metodiku AIAG & VDA (vydanie 2019), ktorá zavádza špecifické "
        "charakteristiky CC, OS, SC a HI.",
        "Položky označené ako CC alebo OS musia byť povinne zahrnuté v Control Plane a safety signoff. Finálna klasifikácia musí byť schválená kvalifikovaným tímom FMEA.",
    ],
]


ISTOTA_LEGENDA = [
    [
        "Úroveň istoty AI",
        "Rozsah (%)",
        "Farba",
        "Interpretácia",
        "Odporúčaná akcia",
    ],
    [
        "Vysoká istota",
        "75 % – 100 %",
        "Zelená",
        "Chyba, príčina alebo opatrenie sú explicitne doložené vo vstupných dokumentoch "
        "(záznamy o nezhodách, kontrolný plán, pracovný postup). "
        "AI vychádzala z konkrétnych a jednoznačných informácií.",
        "Položku možno akceptovať po základnej odbornej kontrole. "
        "Odporúča sa overiť relevantnosť v kontexte aktuálneho procesu.",
    ],
    [
        "Stredná istota",
        "50 % – 74 %",
        "Žltá",
        "Chyba alebo príčina sú odvoditeľné z kontextu dokumentov, ale nie sú explicitne pomenované. "
        "AI vychádzala z nepriamych informácií alebo zo všeobecných znalostí daného typu operácie.",
        "Položku je potrebné preskúmať odborníkom. "
        "Overiť, či chyba, príčina a opatrenie zodpovedajú skutočnému stavu procesu. "
        "Prípadne doplniť alebo upraviť pred finálnym schválením FMEA.",
    ],
    [
        "Nízka istota",
        "0 % – 49 %",
        "Červená",
        "Chyba alebo príčina sú generické a kontext dokumentov ich priamo nepodporuje. "
        "AI nemala dostatok informácií a vygenerovala položku na základe všeobecných predpokladov "
        "bez konkrétnej opory v podkladoch.",
        "Položku je potrebné manuálne prehodnotiť alebo nahradiť. "
        "Zvážiť doplnenie relevantnejších vstupných dokumentov (napr. záznamy o nezhodách, "
        "FMEA z podobného procesu) a opätovné spustenie analýzy.",
    ],
    [
        "Dôležité upozornenie",
        "—",
        "—",
        "Hodnoty istoty AI sú orientačné. Vyjadrujú mieru opory vo vstupných dokumentoch, "
        "nie absolútnu správnosť obsahu. Aj položka s vysokou istotou môže byť obsahovo nesprávna, "
        "ak boli vstupné dokumenty nekvalitné alebo neaktuálne. "
        "Hodnoty istoty AI nie sú súčasťou normy IEC 60812:2018 – ide o doplnkovú metriku "
        "pre podporu odbornej kontroly automaticky generovaných položiek.",
        "Finálne hodnoty S / O / D, klasifikáciu CC/SC a odporúčané opatrenia musí vždy "
        "schváliť kvalifikovaný tím FMEA v súlade s normou IEC 60812:2018. "
        "Tento dokument je AI-asistovaný NÁVRH, nie finálny auditovateľný záznam.",
    ],
] 