#!/usr/bin/env python3
"""Parse the RIK 2022 referendum decision for Grad Kraljevo polling stations.

Input : geo/kraljevo_ref.txt     (wvText output; cells separated by BEL '\x07')
        geo/kraljevo_izmena.txt  (2022 decision amendment, changes station 34)
Output: geo/kraljevo_ref_rows.json  [{municipality, no, name, address, area}]

wvText emits each table cell terminated by '\x07'.  A row starts at a cell that,
after collapsing whitespace, is exactly a station number (e.g. "1." or "34");
the following cells are [name, address, area] (a trailing empty cell may appear).
The amendment re-issues station 34 (venue renamed to "ОСНОВНА ШКОЛА",
settlement "ВИТАНОВАЦ" unchanged).
"""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
REF_TXT = os.path.join(BASE, "kraljevo_ref.txt")
IZM_TXT = os.path.join(BASE, "kraljevo_izmena.txt")
OUT = os.path.join(BASE, "kraljevo_ref_rows.json")
MUNI = "Град Краљево"


def _clean(cell):
    return re.sub(r"\s+", " ", cell.replace("\x0b", " ")).strip()


def _cells(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    return raw.split("\x07")


def _is_number(cell):
    return bool(re.fullmatch(r"\d+\.?", _clean(cell)))


def parse_ref(path):
    cells = _cells(path)
    numidx = [i for i, c in enumerate(cells) if _is_number(c)]
    rows = []
    for k, i in enumerate(numidx):
        end = numidx[k + 1] if k + 1 < len(numidx) else len(cells)
        body = [_clean(cells[j]) for j in range(i + 1, end)]
        # keep only leading non-empty cells (drop trailing empties / trailing footer)
        vals = []
        for b in body:
            if b:
                vals.append(b)
            elif vals:
                break
        name = vals[0] if len(vals) > 0 else ""
        address = vals[1] if len(vals) > 1 else ""
        area = vals[2] if len(vals) > 2 else ""
        rows.append({"no": int(_clean(cells[i]).rstrip(".")),
                     "name": name, "address": address, "area": area})
    return rows


def parse_izmena(path):
    """Return {no: {name, address}} overrides from the amendment table."""
    cells = _cells(path)
    numidx = [i for i, c in enumerate(cells) if _is_number(c)]
    overrides = {}
    for i in numidx:
        no = int(_clean(cells[i]).rstrip("."))
        # skip the header-ish / non-station numbers: amendment table has the
        # Ред. бр. cell followed directly by name, address, area
        body = [_clean(cells[j]) for j in range(i + 1, i + 4)]
        if len(body) < 2:
            continue
        overrides[no] = {"name": body[0], "address": body[1]}
    return overrides


def main():
    rows = parse_ref(REF_TXT)
    print(f"parsed {len(rows)} station rows from {os.path.basename(REF_TXT)}")
    nums = [r["no"] for r in rows]
    if nums != list(range(1, len(rows) + 1)):
        print("  ! numbering not contiguous 1..N:", nums[:6], "...", nums[-6:])

    izm = parse_izmena(IZM_TXT)
    applied = []
    for r in rows:
        if r["no"] in izm:
            o = izm[r["no"]]
            if o.get("name"):
                r["name"] = o["name"]
                r["_override"] = "izmena"
            if o.get("address"):
                r["address"] = o["address"]
                r["_override"] = "izmena"
            applied.append((r["no"], o))
    for r in rows:
        r["municipality"] = MUNI

    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"amendment overrides applied: {[a[0] for a in applied]}")
    for no, o in applied:
        print(f"  station {no}: name='{o['name']}' address='{o['address']}'")
    # rural stations where the doc name is only a venue type and address a settlement
    rural = sum(1 for r in rows if not r["address"].upper().startswith("КРАЉЕВО"))
    print(f"rows with non-КРАЉЕВО address (rural/settlement): {rural}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
