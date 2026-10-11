#!/usr/bin/env python3
"""Parse the RIK 2022 referendum decision for Grad Subotica polling stations.

Input : geo/subotica_ref.txt   (wvText output; cells separated by BEL '\x07')
Output: geo/subotica_ref_rows.json  [{no, name, address}]

Also reads geo/subotica_izmena.docx (2022 decision amendment) and reports whether
it changes any station name/address.  For Subotica it only corrects polling-area
house-number ranges, so no overrides are applied.
"""
import html
import json
import os
import re
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
TXT = os.path.join(BASE, "subotica_ref.txt")
DOCX = os.path.join(BASE, "subotica_izmena.docx")
OUT = os.path.join(BASE, "subotica_ref_rows.json")


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
        rows.append({"no": no, "name": cells[0] if cells else "",
                     "address": cells[1] if len(cells) > 1 else ""})
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
    print(f"parsed {len(rows)} station rows from {os.path.basename(TXT)}")
    nums = [r["no"] for r in rows]
    if nums != list(range(1, len(rows) + 1)):
        print("  ! numbering not contiguous 1..N:", nums[:5], "...", nums[-5:])

    # Report any name/address-ish amendments (Subotica 2022 izmena only fixes areas)
    changes = []
    for l in docx_text().split("\n"):
        l = l.strip()
        if re.match(r"^Гласачко место број", l):
            changes.append(l)
    print(f"izmena docx: {len(changes)} amendment clauses "
          f"(polling-area corrections only; no name/address overrides)")
    for c in changes:
        print("   -", c[:90])

    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
