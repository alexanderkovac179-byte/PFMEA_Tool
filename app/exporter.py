import pandas as pd
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from app.legends import VYZNAM_LEGENDA, VYSKYT_LEGENDA, ODHALENIE_LEGENDA
from app.config import FMEA_METADATA_DEFAULTS


def write_legend_sheet(ws, data):
    thin = Side(style="thin", color="000000")
    thin_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    medium_border = thin_border

    header_fill = PatternFill(fill_type="solid", fgColor="D9EAF7")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="top", wrap_text=True)
    bold = Font(bold=True)

    for r_idx, row in enumerate(data, start=1):
        for c_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.border = thin_border

            if r_idx == 1:
                cell.fill = header_fill
                cell.font = bold
                cell.alignment = center
                cell.border = medium_border
            else:
                if isinstance(value, (int, float)) or str(value).strip() in {"X", "x"}:
                    cell.alignment = center
                else:
                    cell.alignment = left

    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_length + 2, 45)


def export_to_excel(items: list[dict], output_path: str, metadata: dict | None = None):
    metadata = {**FMEA_METADATA_DEFAULTS, **(metadata or {})}

    desired_order = [
        "funkcia_procesu_pozadavky",
        "mozna_chyba",
        "mozny_nasledok_chyby",
        "vyznam",
        "klasifikacia",
        "mozna_pricina_mechanizmus_chyby",
        "vyskyt",
        "pouzivane_metody_prevencie",
        "pouzivane_metody_odhalenia",
        "odhalenie",
        "rpn",
        "doporucene_opatrenia",
        "zodp_pracovnik_datum_ukoncenia",
        "novy_vyznam",
        "novy_vyskyt",
        "nove_odhalenie",
        "novy_rpn"
    ]

    rename_map = {
        "funkcia_procesu_pozadavky": "Funkcia procesu / požiadavky",
        "mozna_chyba": "Možná chyba",
        "mozny_nasledok_chyby": "Možný následok chyby",
        "vyznam": "Význam",
        "klasifikacia": "Klasifikácia",
        "mozna_pricina_mechanizmus_chyby": "Možná príčina / mechanizmus chyby",
        "vyskyt": "Výskyt",
        "pouzivane_metody_prevencie": "Používané metódy k prevencii voči výskytu",
        "pouzivane_metody_odhalenia": "Používané metódy k odhaleniu",
        "odhalenie": "Odhalenie",
        "rpn": "RPN",
        "doporucene_opatrenia": "Doporučené opatrenia",
        "zodp_pracovnik_datum_ukoncenia": "Zodp. pracovník / dátum ukončenia",
        "novy_vyznam": "Nový význam",
        "novy_vyskyt": "Nový výskyt",
        "nove_odhalenie": "Nové odhalenie",
        "novy_rpn": "Nový RPN"
    }

    df = pd.DataFrame(items)

    for col in desired_order:
        if col not in df.columns:
            df[col] = ""

    df = df[desired_order]
    df = df.sort_values(by="rpn", ascending=False)
    df = df.rename(columns=rename_map)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Procesna_FMEA", startrow=6)

    wb = load_workbook(output_path)
    ws = wb["Procesna_FMEA"]

    thin = Side(style="thin", color="000000")
    thin_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    medium_border = thin_border

    title_fill = PatternFill(fill_type="solid", fgColor="9DC3E6")
    info_label_fill = PatternFill(fill_type="solid", fgColor="D9EAF7")
    group_fill = PatternFill(fill_type="solid", fgColor="BDD7EE")
    header_fill = PatternFill(fill_type="solid", fgColor="EAF2F8")

    red_fill = PatternFill(fill_type="solid", fgColor="F4CCCC")
    yellow_fill = PatternFill(fill_type="solid", fgColor="FFF2CC")
    green_fill = PatternFill(fill_type="solid", fgColor="D9EAD3")

    bold = Font(bold=True)
    title_font = Font(bold=True, size=14)
    normal_font = Font(size=10)

    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="top", wrap_text=True)

    ws.merge_cells("A1:Q1")
    ws["A1"] = metadata["nazov_hlavicky"]
    ws["A1"].font = title_font
    ws["A1"].fill = title_fill
    ws["A1"].alignment = center
    ws["A1"].border = medium_border

    today = datetime.now().strftime("%d.%m.%Y")

    info_rows = {
        "A2": "Názov procesu:",
        "F2": metadata["nazov_procesu"],
        "J2": "Číslo FMEA:",
        "N2": metadata["cislo_fmea"],

        "A3": "Typ FMEA:",
        "F3": metadata["typ_fmea"],
        "J3": "Revízia:",
        "N3": metadata["revizia"],

        "A4": "Vypracoval:",
        "F4": metadata["vypracoval"],
        "J4": "Dátum:",
        "N4": today,

        "A5": "Poznámka:",
        "F5": metadata["poznamka"],
    }

    merge_ranges = [
        "A2:E2", "F2:I2", "J2:M2", "N2:Q2",
        "A3:E3", "F3:I3", "J3:M3", "N3:Q3",
        "A4:E4", "F4:I4", "J4:M4", "N4:Q4",
        "A5:E5", "F5:Q5",
    ]
    for r in merge_ranges:
        ws.merge_cells(r)

    for ref, value in info_rows.items():
        ws[ref] = value

    for row in ws.iter_rows(min_row=2, max_row=5, min_col=1, max_col=17):
        for cell in row:
            cell.border = thin_border
            cell.alignment = left
            cell.font = normal_font

    for cell in ["A2", "A3", "A4", "A5", "J2", "J3", "J4"]:
        ws[cell].font = bold
        ws[cell].fill = info_label_fill

    group_row = 7
    header_row = 8
    data_start_row = 9

    for col in range(1, ws.max_column + 1):
        ws.cell(row=header_row, column=col).value = ws.cell(row=group_row, column=col).value
        ws.cell(row=group_row, column=col).value = None

    groups = [
        ("A7:A8", "Funkcia"),
        ("B7:B8", "Možná chyba"),
        ("C7:C8", "Možný následok chyby"),
        ("D7:D8", "Význam"),
        ("E7:E8", "Klasifikácia"),
        ("F7:F8", "Možná príčina / mechanizmus chyby"),
        ("G7:G8", "Výskyt"),
        ("H7:I7", "Súčasné riadenie procesu"),
        ("J7:J8", "Odhalenie"),
        ("K7:K8", "RPN"),
        ("L7:L8", "Doporučené opatrenia"),
        ("M7:M8", "Zodp. pracovník / dátum ukončenia"),
        ("N7:Q7", "Výsledky opatrení"),
    ]

    for rng, value in groups:
        ws.merge_cells(rng)
        first = ws[rng.split(":")[0]]
        first.value = value
        first.font = bold
        first.fill = group_fill
        first.alignment = center
        first.border = medium_border

    second_headers = {
        "H8": "Prevencia",
        "I8": "Odhalenie",
        "N8": "Nový význam",
        "O8": "Nový výskyt",
        "P8": "Nové odhalenie",
        "Q8": "Nový RPN",
    }

    for ref, value in second_headers.items():
        ws[ref] = value

    for row in ws.iter_rows(min_row=7, max_row=8, min_col=1, max_col=17):
        for cell in row:
            cell.font = bold
            if cell.fill.fill_type is None:
                cell.fill = header_fill
            cell.alignment = center
            cell.border = medium_border

    for row in ws.iter_rows(min_row=data_start_row, max_row=ws.max_row, min_col=1, max_col=17):
        for cell in row:
            cell.alignment = left
            cell.border = thin_border
            cell.font = normal_font

    numeric_cols = ["D", "G", "J", "K", "N", "O", "P", "Q"]
    for col in numeric_cols:
        for row in range(data_start_row, ws.max_row + 1):
            ws[f"{col}{row}"].alignment = center

    widths = {
        "A": 34,
        "B": 30,
        "C": 36,
        "D": 10,
        "E": 18,
        "F": 36,
        "G": 10,
        "H": 34,
        "I": 34,
        "J": 10,
        "K": 10,
        "L": 38,
        "M": 24,
        "N": 12,
        "O": 12,
        "P": 14,
        "Q": 12,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    ws.row_dimensions[1].height = 24
    ws.row_dimensions[7].height = 24
    ws.row_dimensions[8].height = 34

    for row in range(data_start_row, ws.max_row + 1):
        ws.row_dimensions[row].height = 64

    for row in range(data_start_row, ws.max_row + 1):
        cell = ws[f"K{row}"]
        try:
            val = int(cell.value)
            if val >= 200:
                cell.fill = red_fill
            elif val >= 100:
                cell.fill = yellow_fill
            else:
                cell.fill = green_fill
            cell.font = bold
            cell.alignment = center
        except Exception:
            pass

    for row in range(data_start_row, ws.max_row + 1):
        cell = ws[f"Q{row}"]
        try:
            val = int(cell.value)
            if val >= 200:
                cell.fill = red_fill
            elif val >= 100:
                cell.fill = yellow_fill
            else:
                cell.fill = green_fill
            cell.font = bold
            cell.alignment = center
        except Exception:
            pass

    for col in range(1, 18):
        ws.cell(7, col).border = medium_border
        ws.cell(ws.max_row, col).border = medium_border

    for row in range(7, ws.max_row + 1):
        ws.cell(row, 1).border = medium_border
        ws.cell(row, 17).border = medium_border

    ws.auto_filter.ref = f"A8:Q{ws.max_row}"
    ws.freeze_panes = "A9"

    if "Legenda_Vyznam" in wb.sheetnames:
        del wb["Legenda_Vyznam"]
    if "Legenda_Vyskyt" in wb.sheetnames:
        del wb["Legenda_Vyskyt"]
    if "Legenda_Odhalenie" in wb.sheetnames:
        del wb["Legenda_Odhalenie"]

    ws_vyznam = wb.create_sheet("Legenda_Vyznam")
    write_legend_sheet(ws_vyznam, VYZNAM_LEGENDA)

    ws_vyskyt = wb.create_sheet("Legenda_Vyskyt")
    write_legend_sheet(ws_vyskyt, VYSKYT_LEGENDA)

    ws_odhalenie = wb.create_sheet("Legenda_Odhalenie")
    write_legend_sheet(ws_odhalenie, ODHALENIE_LEGENDA)

    wb.save(output_path)