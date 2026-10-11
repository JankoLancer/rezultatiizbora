#!/usr/bin/env python3
"""Parse the 2022 referendum polling-station decisions for the Belgrade g1 group:
Gradske opštine Novi Beograd, Zemun, Surčin and Barajevo.

Inputs (in geo/):
  beograd_g1_novibeograd_ref.txt  (wvText; BEL '\x07' separated cells)
  beograd_g1_zemun_ref.txt
  beograd_g1_barajevo_ref.txt
  beograd_g1_surcin.docx          (native Word table)
Output:
  beograd_g1_ref_rows.json  -> {"<municipality>": [{no, name, address}, ...]}

Layouts in the .doc files are [empty, number, name, address, area] per row
(Novi Beograd number is plain "1", Zemun/Barajevo use "1.").
Surčin's .docx has a 4-column table [Р.б., name, address, area].
"""
import html
import json
import os
import re
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
MUNIS = {
    "Нови Београд": "beograd_g1_novibeograd_ref.txt",
    "Земун": "beograd_g1_zemun_ref.txt",
    "Барајево": "beograd_g1_barajevo_ref.txt",
    "Сурчин": "beograd_g1_surcin.docx",
}
OUT = os.path.join(BASE, "beograd_g1_ref_rows.json")

NUM_RE = re.compile(r"^\d+\.?$")


def clean(s):
    return re.sub(r"\s+", " ", s.replace("\x0b", " ").replace("\xa0", " ")).strip()


def parse_doc_txt(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    cells = raw.split("\x07")
    rows = []
    for i, c in enumerate(cells):
        if NUM_RE.match(clean(c)) and i + 2 < len(cells):
            name = clean(cells[i + 1])
            addr = clean(cells[i + 2])
            if name and addr:
                rows.append({"no": int(clean(c).rstrip(".")), "name": name, "address": addr})
    return rows


def parse_docx(path):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    tbl = re.findall(r"<w:tbl>.*?</w:tbl>", xml, re.S)[0]
    trs = re.findall(r"<w:tr[ >].*?</w:tr>", tbl, re.S)
    rows = []
    for tr in trs:
        tcs = re.findall(r"<w:tc>.*?</w:tc>", tr, re.S)
        cells = []
        for tc in tcs:
            txt = "".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", tc, re.S))
            cells.append(clean(html.unescape(txt)))
        if len(cells) >= 3 and re.match(r"^\d+$", cells[0]):
            rows.append({"no": int(cells[0]), "name": cells[1], "address": cells[2]})
    return rows


def main():
    out = {}
    for muni, fname in MUNIS.items():
        path = os.path.join(BASE, fname)
        rows = parse_docx(path) if fname.endswith(".docx") else parse_doc_txt(path)
        out[muni] = rows
        nums = [r["no"] for r in rows]
        print(f"[{muni}] parsed {len(rows)} rows; numbering 1..{max(nums) if nums else 0} "
              f"contiguous={nums == list(range(1, len(rows) + 1))}")
        for r in rows[:2]:
            print(f"    {r['no']:>3} {r['name'][:46]:<46} | {r['address'][:46]}")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
