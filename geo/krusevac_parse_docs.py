#!/usr/bin/env python3
"""Parse the RIK 2022 referendum decision for Grad Krusevac polling stations.

Input : geo/krusevac_ref.txt     (wvText output; cells separated by BEL '\x07')
Output: geo/krusevac_ref_rows.json  [{no, name, address, area}]

Also reads geo/krusevac_izmena.docx (2022 decision amendment) and applies it:
for polling station 96 the venue name "ОСНОВНА ШКОЛА" becomes "ДОМ КУЛТУРЕ".
"""
import html
import json
import os
import re
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
TXT = os.path.join(BASE, "krusevac_ref.txt")
DOCX = os.path.join(BASE, "krusevac_izmena.docx")
OUT = os.path.join(BASE, "krusevac_ref_rows.json")

# venue name override coming from the 2022 amendment (Krusevac izmena resenja c)
AMEND = {96: {"name": "ДОМ КУЛТУРЕ"}}


def parse_rows():
    lines = open(TXT, encoding="utf-8", errors="replace").read().split("\n")
    num_idx = [i for i, l in enumerate(lines)
               if re.match(r"^\x07\d+\x07?$", l.strip())]
    rows = []
    for k, i in enumerate(num_idx):
        no = int(lines[i].strip().strip("\x07"))
        end = num_idx[k + 1] if k + 1 < len(num_idx) else len(lines)
        cells = []
        for l in lines[i + 1:end]:
            c = l.replace("\x07", "").replace("\x0b", " ").strip()
            if c:
                cells.append(c)
        rows.append({
            "no": no,
            "name": cells[0] if cells else "",
            "address": cells[1] if len(cells) > 1 else "",
            "area": cells[2] if len(cells) > 2 else "",
        })
    return rows


def docx_text():
    if not os.path.exists(DOCX):
        return ""
    z = zipfile.ZipFile(DOCX)
    x = z.read("word/document.xml").decode("utf-8")
    x = re.sub(r"</w:p>", "\n", x)
    x = re.sub(r"<[^>]+>", "", x)
    return html.unescape(x)


def main():
    rows = parse_rows()
    by_no = {r["no"]: r for r in rows}
    print(f"parsed {len(rows)} station rows from {os.path.basename(TXT)}")
    nums = [r["no"] for r in rows]
    if nums != list(range(1, len(rows) + 1)):
        print("  ! numbering not contiguous 1..N:", nums[:5], "...", nums[-5:])

    for no, ov in AMEND.items():
        if no in by_no:
            old = by_no[no]["name"]
            by_no[no].update(ov)
            print(f"amendment: station {no} name {old!r} -> {ov['name']!r}")
        else:
            print(f"  ! amendment for station {no} but no such row")

    print("izmena docx clauses:")
    for l in docx_text().split("\n"):
        l = l.strip()
        if l.startswith("У Решењу") or re.match(r"^на гласачком месту", l):
            print("   -", l[:100])

    rows = [by_no[n] for n in sorted(by_no)]
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
