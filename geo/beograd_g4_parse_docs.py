#!/usr/bin/env python3
"""Parse the RIK 2022 referendum polling-station decisions for the five
Belgrade city municipalities in group g4 (Раковица, Лазаревац, Младеновац,
Обреновац, Гроцка).

Inputs (all in geo/):
  beograd_g4_rakovica.doc   -> beograd_g4_rakovica.txt   (wvText, BEL '\x07' cells)
  beograd_g4_obrenovac.doc  -> beograd_g4_obrenovac.txt
  beograd_g4_grocka.doc     -> beograd_g4_grocka.txt
  beograd_g4_lazarevac.docx (cells: num, name, address, area; num cell empty)
  beograd_g4_mladenovac.docx (cells: num, name, address, area)
  beograd_g4_rakovica_izmena.docx (amendment: BM 52 -> new name/address)

Output: geo/beograd_g4_ref_rows.json  [{municipality,no,name,address,area}]
"""
import json
import os
import re
import zipfile
from html import unescape

BASE = os.path.dirname(os.path.abspath(__file__))

DOC_TXT = {
    "Градска општина Раковица": "beograd_g4_rakovica.txt",
    "Градска општина Обреновац": "beograd_g4_obrenovac.txt",
    "Градска општина Гроцка": "beograd_g4_grocka.txt",
}
DOCX = {
    "Градска општина Лазаревац": "beograd_g4_lazarevac.docx",
    "Градска општина Младеновац": "beograd_g4_mladenovac.docx",
}
IZMENA = "beograd_g4_rakovica_izmena.docx"
OUT = os.path.join(BASE, "beograd_g4_ref_rows.json")


def norm(s):
    return re.sub(r"\s+", " ", s.replace("\x0b", " ")).strip()


def parse_txt(path):
    """wvText .doc: cells terminated by BEL.  Rows are groups of 5 cells
    ['', no, name, address, area] after the 4 header cells."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    cells = [norm(c) for c in raw.replace("\r", "\n").split("\x07")[:-1]]
    hi = next(i for i, c in enumerate(cells) if "НАЗИВ ГЛАСАЧКОГ МЕСТА" in c)
    body = cells[hi + 3:]  # skip name/address/area headers
    rows = []
    for g in range(0, len(body) - 4, 5):
        grp = body[g:g + 5]
        no, name, address, area = grp[1], grp[2], grp[3], grp[4]
        m = re.match(r"^(\d+)\.?$", no)
        if not m:
            continue
        rows.append({"no": int(m.group(1)), "name": name,
                     "address": address, "area": area})
    return rows


def docx_cells(path):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    out = []
    for tc in re.findall(r"<w:tc[ >].*?</w:tc>", xml, re.S):
        t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", tc, re.S))
        out.append(norm(unescape(re.sub(r"<[^>]+>", "", t))))
    return out


def parse_docx(path):
    """Rows are groups of 4 cells [no, name, address, area]; the number cell
    may be empty (Lazarevac) in which case document order supplies it."""
    cells = docx_cells(path)
    hi = next(i for i, c in enumerate(cells) if "НАЗИВ ГЛАСАЧКОГ МЕСТА" in c)
    body = cells[hi + 3:]
    rows = []
    for g in range(0, len(body) - 3, 4):
        no, name, address, area = body[g:g + 4]
        m = re.match(r"^(\d+)\.?$", no)
        rows.append({"no": int(m.group(1)) if m else None,
                     "name": name, "address": address, "area": area})
    return rows


def parse_izmena(path):
    """Rakovica amendment overrides BM 52 name/address."""
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S))
        t = norm(unescape(re.sub(r"<[^>]+>", "", t)))
        if t:
            paras.append(t)
    text = " ".join(paras)
    m = re.search(r"БМ\s*(\d+).*?гласи\s+(.+?)\.\s*Подручје", text)
    if not m:
        return {}
    no = int(m.group(1))
    new = m.group(2)
    # 'ОШ "14.ОКТОБАР", ул. Гочка бр.40'
    nm = re.match(r'\s*([^,]+?)\s*,\s*ул\.\s*(.+?)\s*бр\.?\s*([\w/]+)\s*$', new)
    if not nm:
        return {no: {"name": new.strip()}}
    name = nm.group(1).strip()
    street = nm.group(2).strip()
    num = nm.group(3).strip()
    return {no: {"name": name, "address": f"РАКОВИЦА, {street.upper()} БР. {num}"}}


def main():
    data = {}
    for muni, f in DOC_TXT.items():
        rows = parse_txt(os.path.join(BASE, f))
        data[muni] = rows
        print(f"[txt ] {muni:<28} {len(rows):>3} rows  ({f})")
    for muni, f in DOCX.items():
        rows = parse_docx(os.path.join(BASE, f))
        # fill empty numbers by document order
        nxt = 1
        for r in rows:
            if r["no"] is None:
                r["no"] = nxt
            nxt = r["no"] + 1
        data[muni] = rows
        print(f"[docx] {muni:<28} {len(rows):>3} rows  ({f})")

    # apply Rakovica amendment
    iz = parse_izmena(os.path.join(BASE, IZMENA))
    print("izmena overrides:", iz)
    if iz:
        muni = "Градска општина Раковица"
        for r in data[muni]:
            if r["no"] in iz:
                ov = iz[r["no"]]
                old = (r["name"], r["address"])
                r["name"] = ov.get("name", r["name"])
                if ov.get("address"):
                    r["address"] = ov["address"]
                r["_override"] = "izmena"
                print(f"  BM 52 {old} -> {(r['name'], r['address'])}")

    out = []
    for muni, rows in data.items():
        for r in rows:
            out.append({"municipality": muni, "no": r["no"], "name": r["name"],
                        "address": r["address"], "area": r["area"]})
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {len(out)} rows -> {OUT}")


if __name__ == "__main__":
    main()
