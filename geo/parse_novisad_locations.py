#!/usr/bin/env python3
"""Parse the Novi Sad 2022 referendum decision (polling-station list) + amendments.

The wvText output puts each table cell on its own physical line, terminated by
the BEL char \\x07.  In the Novi Sad document the 'Ред. бр.' (number) cell is
emitted empty, so station numbers are taken from document order (1..N, which
matches the document's own ordering).  Cells can wrap over several physical
lines; rows are delimited by the empty number line '\\x07\\x07'.
"""
import json, os, re, zipfile
from html import unescape

BASE = os.path.dirname(os.path.abspath(__file__))
REF_TXT = os.path.join(BASE, "novisad_ref.txt")
IZM1_TXT = os.path.join(BASE, "novisad_izmena1.txt")
IZM2_DOCX = os.path.join(BASE, "novisad_izmena2.docx")
OUT = os.path.join(BASE, "novisad_ref_rows.json")

MUNI = "Град Нови Сад"


def parse_ref(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    lines = raw.replace("\r", "\n").split("\n")
    stream = "\n".join(lines)
    # every BEL (\x07) terminates a table cell; cells may span physical lines
    cells = stream.split("\x07")[:-1]
    pi = next(i for i, c in enumerate(cells) if "ПОДРУЧЈЕ" in c)
    start = pi + 1
    rows = []
    i = start
    while i + 4 < len(cells):
        name = re.sub(r"\s+", " ", cells[i + 2]).strip()
        address = re.sub(r"\s+", " ", cells[i + 3]).strip()
        area = re.sub(r"\s+", " ", cells[i + 4]).strip()
        if not name or name.startswith("II"):
            break
        rows.append({"no": len(rows) + 1, "name": name, "address": address, "area": area})
        i += 5
    return rows


QUOTE = "„“”\""  # all quote styles used in these documents


def _qt(s):
    return s.strip().strip(QUOTE).strip()


def parse_izmena1(path):
    """Returns {no: address} seat changes."""
    txt = open(path, encoding="utf-8", errors="replace").read()
    overrides = {}
    # split into per-station clauses starting at each 'број N.'
    parts = re.split(r"(?=на гласачком месту број \d+\.)", txt)
    for part in parts:
        m = re.match(r"на гласачком месту број (\d+)\.", part)
        if not m:
            continue
        if "треба да стоји" not in part:
            continue
        after = part.split("треба да стоји", 1)[1]
        new = re.search(r"[„“\"]([^„“\"]+)[„“\"]", after)
        if new:
            overrides[int(m.group(1))] = _qt(new.group(1))
    return overrides


def parse_izmena2(path):
    """Returns {no: {name?, address?}} from the .docx."""
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S))
        t = unescape(re.sub(r"<[^>]+>", "", t)).strip()
        if t:
            paras.append(t)
    overrides = {}
    for p in paras:
        m = re.search(r"На гласачком месту број (\d+)\.", p)
        if not m or "замењују речима" not in p:
            continue
        no = int(m.group(1))
        new = p.split("замењују речима", 1)[1]
        q = re.search(r"[„“\"]([^„“\"]+)[„“\"]", new)
        if not q:
            continue
        val = _qt(q.group(1))
        if "назив и седиште" in p:
            nm, rest = val.split(",", 1)
            overrides[no] = {"name": nm.strip(), "address": rest.strip()}
        else:  # seat (address) only
            overrides[no] = {"address": val}
    return overrides


def main():
    rows = parse_ref(REF_TXT)
    iz1 = parse_izmena1(IZM1_TXT)
    iz2 = parse_izmena2(IZM2_DOCX)
    for r in rows:
        if r["no"] in iz1:
            r["address"] = iz1[r["no"]]
            r["_override"] = "izmena1"
        if r["no"] in iz2:
            if "name" in iz2[r["no"]]:
                r["name"] = iz2[r["no"]]["name"]
            if "address" in iz2[r["no"]]:
                r["address"] = iz2[r["no"]]["address"]
            r["_override"] = "izmena2"
    for r in rows:
        r["municipality"] = MUNI
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"parsed {len(rows)} rows -> {OUT}")
    print(f"izmena1 address overrides: {iz1}")
    print(f"izmena2 overrides: {iz2}")
    for r in rows[:3] + rows[-3:]:
        print(f"  {r['no']:>3} {r['name'][:44]:<44} {r['address']} [{r.get('_override','')}]")


if __name__ == "__main__":
    main()
