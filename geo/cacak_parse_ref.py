#!/usr/bin/env python3
"""Parse the Čačak 2022 referendum decision (polling-station list) into rows.

The wvText output terminates each table cell with the BEL char \\x07.
After the table header the layout is:
    empty | no | name | address | area | empty | no | name | address | area ...
So each row is located by its digit-only "no" cell; the following two cells
are the venue name and the address.
"""
import json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
REF_TXT = os.path.join(BASE, "cacak_ref.txt")
OUT = os.path.join(BASE, "cacak_ref_rows.json")

MUNI = "Град Чачак"


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def parse_ref(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    cells = raw.replace("\r", "\n").split("\x07")
    rows = []
    for i, c in enumerate(cells):
        if not re.fullmatch(r"\d+", c.strip()):
            continue
        no = int(c.strip())
        name = norm(cells[i + 1]) if i + 1 < len(cells) else ""
        address = norm(cells[i + 2]) if i + 2 < len(cells) else ""
        area = norm(cells[i + 3]) if i + 3 < len(cells) else ""
        rows.append({"municipality": MUNI, "no": no, "name": name,
                     "address": address, "area": area})
    return rows


def main():
    rows = parse_ref(REF_TXT)
    # keep document order but sort by no, verify contiguous 1..N
    rows.sort(key=lambda r: r["no"])
    missing = [n for n in range(1, len(rows) + 1) if n not in {r["no"] for r in rows}]
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"parsed {len(rows)} rows -> {OUT}; missing numbers: {missing}")
    for r in rows[:3] + rows[-3:]:
        print(f"  {r['no']:>3} {r['name'][:44]:<44} {r['address']}")


if __name__ == "__main__":
    main()
