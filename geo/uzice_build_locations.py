#!/usr/bin/env python3
"""Build geo/uzice_stations_locations.json (88 rows) for ГРАД УЖИЦЕ.

Inputs:
  geo/uzice_ref.docx     2023 decision "Uzice glasacka mesta" -> TWO tables:
                         table 0 = Град Ужице (83 stations, no 1..83)
                         table 1 = Градска општина Севојно (5 stations, no 1..5)
  geo/uzice_izmena.docx  "Uzice izmena resenja" -> one replacement row
  rik_2023_uzice/manifest.csv  RIK 2023 target (88 stations)

The generic parser (geo/opstina_docs.py) treats the whole docx as one table and
merges the second table because the numbering restarts at 1. To stay on the
generic parser, the two <w:tbl> elements are split into standalone docx files
(just an XML selection, no station parsing) and each is parsed by
opstina_docs.parse(). The amendment is applied by matching on its unique
address/area, and every manifest row is aligned by polling-station number.

Outputs:
  geo/uzice_ref_rows.json              -> parsed+amended doc rows
  geo/uzice_stations_locations.json    -> RIK 2023 target, [municipality,no,name,address]
  geo/uzice_align_report.txt           -> alignment / mismatch notes
"""
import csv
import json
import os
import re
import zipfile
from difflib import SequenceMatcher

import opstina_docs

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
REF = os.path.join(HERE, "uzice_ref.docx")
IZMENA = os.path.join(HERE, "uzice_izmena.docx")
MANIFEST = os.path.join(PROJ, "rik_2023_uzice", "manifest.csv")
T1 = os.path.join(HERE, "uzice_ref_t1.docx")
T2 = os.path.join(HERE, "uzice_ref_t2.docx")
REF_OUT = os.path.join(HERE, "uzice_ref_rows.json")
LOC_OUT = os.path.join(HERE, "uzice_stations_locations.json")
REPORT = os.path.join(HERE, "uzice_align_report.txt")


def norm_name(s):
    s = (s or "").upper()
    for q in '"„“”\'':
        s = s.replace(q, " ")
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    s = re.sub(r"\bОШ\b", "ОСНОВНА ШКОЛА", s)
    s = re.sub(r"\bМЗ\b", "МЕСНА ЗАЈЕДНИЦА", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    return SequenceMatcher(None, norm_name(a), norm_name(b)).ratio()


def split_docx(src, dst, keep):
    """Write a docx with only the <w:tbl> elements whose indices are in `keep`."""
    zin = zipfile.ZipFile(src)
    xml = zin.read("word/document.xml").decode("utf-8", "replace")
    spans = [m.span() for m in re.finditer(r"<w:tbl>.*?</w:tbl>", xml, re.S)]
    drop = sorted((spans[i] for i in range(len(spans)) if i not in keep),
                  reverse=True)
    for s, e in drop:
        xml = xml[:s] + xml[e:]
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = xml.encode("utf-8")
            zout.writestr(item, data)


def parse_tables():
    split_docx(REF, T1, keep=[0])
    split_docx(REF, T2, keep=[1])
    uzice = opstina_docs.parse(T1)
    sevojno = opstina_docs.parse(T2)
    for r in uzice:
        r["municipality"] = "Град Ужице"
    for r in sevojno:
        r["municipality"] = "Градска општина Севојно"
    print(f"  table0 Град Ужице: {len(uzice)} rows")
    print(f"  table1 Градска општина Севојно: {len(sevojno)} rows")
    return uzice, sevojno


def apply_izmena(rows):
    """Apply the single-row amendment. The generic parser cannot recover the
    original row number from a one-row document, so the amended row is located
    by its unique (address, area) pair."""
    amd = opstina_docs.parse(IZMENA)
    applied = []
    for a in amd:
        cands = [r for r in rows
                 if r["address"] == a["address"] and r["area"] == a["area"]]
        if len(cands) == 1:
            c = cands[0]
            old = f'{c["name"]} / {c["address"]}'
            c["name"] = a["name"]
            c["address"] = a["address"]
            applied.append((c["no"], old, f'{a["name"]} / {a["address"]}'))
        else:
            print(f"  ! izmena row not uniquely matched: {a}")
    return applied


def parse_rik(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        nm = r["station_name"].strip()
        m = re.match(r"^(\d+)\s*-\s*(.*)$", nm)
        no = int(m.group(1)) if m else 0
        venue = (m.group(2) if m else nm).strip()
        out.append({"station_id": r["station_id"], "municipality": r["municipality"],
                    "no": no, "name": venue})
    return out


def main():
    uzice, sevojno = parse_tables()
    rows = uzice + sevojno
    applied = apply_izmena(rows)
    print(f"  amendment applied to doc rows: {[a[0] for a in applied]}")
    json.dump(rows, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  wrote {REF_OUT} ({len(rows)} rows)")

    rik = parse_rik(MANIFEST)
    by_muni = {"Град Ужице": {r["no"]: r for r in uzice},
               "Градска општина Севојно": {r["no"]: r for r in sevojno}}

    loc, mismatches, empty, fallback = [], [], [], []
    for r in rik:
        table = by_muni.get(r["municipality"], {})
        doc = table.get(r["no"])
        if doc is None:
            # fall back to the closest name in the same municipality table
            best = max(table.values(), key=lambda x: sim(x["name"], r["name"]),
                       default=None)
            if best is not None and sim(best["name"], r["name"]) >= 0.5:
                doc = best
                fallback.append((r["municipality"], r["no"], best["no"]))
        address = (doc.get("address") if doc else "") or ""
        if doc and sim(doc["name"], r["name"]) < 0.5:
            mismatches.append((r["municipality"], r["no"], doc["no"],
                               r["name"], doc["name"]))
        if not address:
            empty.append((r["municipality"], r["no"], r["name"]))
        loc.append({"municipality": r["municipality"], "no": r["no"],
                    "name": r["name"], "address": address})

    json.dump(loc, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(f"RIK 2023 target: {len(rik)} stations "
                 f"(Град Ужице {len(uzice)}, Градска општина Севојно {len(sevojno)})\n")
        fh.write(f"locations written: {len(loc)}\n")
        fh.write(f"amendment applied: {applied}\n")
        fh.write(f"name mismatches (RIK vs doc): {len(mismatches)}\n")
        for m, no, dno, x, y in mismatches:
            fh.write(f"  {m} {no:>3} (doc {dno:>3}): RIK={x!r}  doc={y!r}\n")
        fh.write(f"number fallbacks: {len(fallback)}\n")
        for m, no, dno in fallback:
            fh.write(f"  {m} {no} -> doc {dno}\n")
        fh.write(f"empty addresses: {len(empty)}\n")
        for m, no, x in empty:
            fh.write(f"  {m} {no}: {x!r}\n")

    print(f"  wrote {LOC_OUT} ({len(loc)} rows)")
    print(f"  name mismatches: {len(mismatches)}; number fallbacks: {len(fallback)}; "
          f"empty addresses: {len(empty)}")
    for m, no, dno, x, y in mismatches:
        print(f"   {m} {no:>3} (doc {dno:>3}): RIK={x!r} doc={y!r}")


if __name__ == "__main__":
    main()
