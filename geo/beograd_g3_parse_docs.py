#!/usr/bin/env python3
"""Parse the RIK 2022 referendum decision (polling-station lists) for the four
Belgrade city municipalities of group g3:

    Градска општина Вождовац, Звездара, Врачар, Стари Град.

Sources:
  * .doc  -> wvText output; table cells terminated by the BEL char '\x07'.
  * .docx -> word/document.xml; one cell per <w:tc>.

Output: geo/beograd_g3_ref_rows.json
    [{municipality, no, name, address, area?}, ...] ordered by municipality, no.

Amendments (Стари Град) are applied on top of the base rows and reported.
"""
import html
import json
import os
import re
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "beograd_g3_ref_rows.json")

DOCS = {
    "Градска општина Вождовац": {"txt": "beograd_g3_vozdovac.txt"},
    "Градска општина Звездара": {"xml": "beograd_g3_zvezdara.xml"},
    "Градска општина Врачар": {"xml": "beograd_g3_vracar.xml"},
    "Градска општина Стари Град": {"txt": "beograd_g3_starigrad.txt"},
}

STARI_DOPUNE = ["beograd_g3_starigrad_dopuna1.txt",
                "beograd_g3_starigrad_dopuna2.txt"]


def clean(s):
    s = s.replace("\x0b", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


_NUM = re.compile(r"^\s*(\d+)\s*\.?\s*$")


def _rows_from_cells(cells, strict=True):
    """cells: list of cleaned non-empty cell strings [num,name,address,area,...]."""
    rows = []
    i = 0
    while i + 3 < len(cells) + 0 and i < len(cells):
        m = _NUM.match(cells[i])
        if not m:
            # skip until a number cell (headers etc.)
            i += 1
            continue
        no = int(m.group(1))
        name = cells[i + 1] if i + 1 < len(cells) else ""
        address = cells[i + 2] if i + 2 < len(cells) else ""
        area = cells[i + 3] if i + 3 < len(cells) else ""
        if strict and no != len(rows) + 1:
            # numbering must be contiguous 1..N
            break
        rows.append({"no": no, "name": name, "address": address, "area": area})
        i += 4
    return rows


def parse_txt(path, strict=True):
    raw = open(path, encoding="utf-8", errors="replace").read().replace("\r", "\n")
    cells = [clean(c) for c in raw.split("\x07")]
    cells = [c for c in cells if c]
    return _rows_from_cells(cells, strict=strict)


def parse_docx_xml(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if path.endswith(".docx"):
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8")
    else:
        xml = open(path, encoding="utf-8", errors="replace").read()
    tcs = re.findall(r"<w:tc[ >].*?</w:tc>", xml, re.S)
    cells = []
    for tc in tcs:
        t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", tc, re.S))
        t = html.unescape(re.sub(r"<[^>]+>", " ", t))
        cells.append(clean(t))
    cells = [c for c in cells if c]
    return _rows_from_cells(cells)


def parse_docx(path):
    return parse_docx_xml(path)


def parse_amendments():
    """Return {no: row} from the Стари Град 'dopuna resenja' documents."""
    overrides = {}
    for fn in STARI_DOPUNE:
        p = os.path.join(BASE, fn)
        if not os.path.exists(p):
            continue
        rows = parse_txt(p, strict=False)
        for r in rows:
            overrides[r["no"]] = r
    return overrides


def main():
    munis = {
        "Градска општина Вождовац": parse_txt(os.path.join(BASE, DOCS["Градска општина Вождовац"]["txt"])),
        "Градска општина Звездара": parse_docx(os.path.join(BASE, DOCS["Градска општина Звездара"]["xml"])),
        "Градска општина Врачар": parse_docx(os.path.join(BASE, DOCS["Градска општина Врачар"]["xml"])),
        "Градска општина Стари Град": parse_txt(os.path.join(BASE, DOCS["Градска општина Стари Град"]["txt"])),
    }
    for m, rows in munis.items():
        print(f"{m}: {len(rows)} rows")

    # apply Стари Град amendments
    overrides = parse_amendments()
    print(f"Стари Град dopuna rows: {sorted(overrides)}")
    for no, r in sorted(overrides.items()):
        base = next((x for x in munis["Градска општина Стари Град"] if x["no"] == no), None)
        tag = "replace" if base else "add"
        print(f"  dopuna {tag} no={no}: {r['name']} | {r['address']}")

    all_rows = []
    for m in ["Градска општина Вождовац", "Градска општина Звездара",
              "Градска општина Врачар", "Градска општина Стари Град"]:
        rows = munis[m]
        if m == "Градска општина Стари Град":
            by_no = {r["no"]: r for r in rows}
            for no, r in overrides.items():
                r = dict(r)
                r["_override"] = "dopuna"
                by_no[no] = r
            rows = [by_no[k] for k in sorted(by_no)]
        for r in rows:
            r = dict(r)
            r["municipality"] = m
            all_rows.append(r)

    json.dump(all_rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {len(all_rows)} rows -> {OUT}")
    # numbering continuity warning
    for m in ["Градска општина Вождовац", "Градска општина Звездара",
              "Градска општина Врачар", "Градска општина Стари Град"]:
        rows = [r for r in all_rows if r["municipality"] == m]
        nums = [r["no"] for r in rows]
        ok = nums == list(range(1, len(rows) + 1))
        print(f"  {m}: n={len(rows)} contiguous={ok}")
    for r in all_rows[:2] + all_rows[-2:]:
        print(f"   {r['no']:>3} {r['name'][:40]:<40} {r['address']}")


if __name__ == "__main__":
    main()
