#!/usr/bin/env python3
"""Parse the Valjevo 2022 referendum polling-stations .doc (wvText output) plus the
two amendment .docx files, then align to the RIK 2023 manifest (the target).

The wvText output terminates each table cell with the BEL char \\x07. After the
header the layout repeats: no | name | address | area | empty. Each row is located
by its digit-only "no" cell; the following three cells are name, address, area.

Amendments applied (both are single-row replacements):
  * izmena1: row 83 -> name "МЕСНА КАНЦЕЛАРИЈА", address "Нема промене"
             ("no change"), so the original address (БРАНКОВИНА) is kept.
  * izmena2: row 30 -> "ОШ \"АНДРА САВЧИЋ\"" / "ЈОВАНА ДУЧИЋА БР. 5".

The 2022 decision has 118 stations while RIK 2023 has 103, so the numbers are not a
reliable one-to-one key. Like build_kraljevo_stations.py, we align the two venue-name
sequences monotonically with difflib.SequenceMatcher (extra 2022 rows are dropped,
extra 2023 rows fall back to the same number) and report every name mismatch.

Produces:
  geo/valjevo_ref_rows.json           -> [{municipality,no,name,address,area}]
  geo/valjevo_stations_locations.json -> [{municipality,no,name,address}] (RIK 2023 target)
  geo/valjevo_align_report.txt        -> alignment notes vs RIK 2023 manifest
"""
import csv, json, os, re
from difflib import SequenceMatcher

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
REF_TXT = os.path.join(BASE, "valjevo_ref.txt")
MANIFEST = os.path.join(PROJ, "rik_2023_valjevo", "manifest.csv")
REF_OUT = os.path.join(BASE, "valjevo_ref_rows.json")
LOC_OUT = os.path.join(BASE, "valjevo_stations_locations.json")
REPORT = os.path.join(BASE, "valjevo_align_report.txt")

MUNI = "Град Ваљево"
TARGET = 103


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def parse_ref(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    cells = raw.replace("\r", "\n").split("\x07")
    rows = []
    for i, c in enumerate(cells):
        t = c.strip()
        if not t or not re.fullmatch(r"\d+\.?", t):
            continue
        no = int(t.rstrip("."))
        name = norm(cells[i + 1]) if i + 1 < len(cells) else ""
        address = norm(cells[i + 2]) if i + 2 < len(cells) else ""
        area = norm(cells[i + 3]) if i + 3 < len(cells) else ""
        address = address.replace("–", "-").replace("—", "-")
        address = re.sub(r"\s*,\s*", ", ", address).strip(" ,")
        rows.append({"municipality": MUNI, "no": no, "name": name,
                     "address": address, "area": area})
    return rows


def apply_amendments(rows):
    by_no = {r["no"]: r for r in rows}
    # izmena1: row 83 renamed; address column reads "Нема промене" -> keep old address
    if 83 in by_no:
        by_no[83]["name"] = "МЕСНА КАНЦЕЛАРИЈА"
    # izmena2: row 30 replaced
    if 30 in by_no:
        by_no[30]["name"] = 'ОШ "АНДРА САВЧИЋ"'
        by_no[30]["address"] = "ЈОВАНА ДУЧИЋА БР. 5"
    return [by_no[r["no"]] for r in rows]


def norm_name(s):
    s = s.upper()
    for q in '"„“”\'':
        s = s.replace(q, " ")
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    s = re.sub(r"\bОШ\b", "ОСНОВНА ШКОЛА", s)
    s = re.sub(r"\bМЗ\b", "МЕСНА ЗАЈЕДНИЦА", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_rik(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        nm = norm(r["station_name"])
        if " - " in nm:
            no, venue = nm.split(" - ", 1)
        else:
            no, venue = nm, ""
        out.append({"no": int(no), "name": venue.strip()})
    return out


def main():
    ref = apply_amendments(parse_ref(REF_TXT))
    ref.sort(key=lambda r: r["no"])
    missing = [n for n in range(1, len(ref) + 1) if n not in {r["no"] for r in ref}]
    json.dump(ref, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"parsed ref rows: {len(ref)}; missing numbers: {missing}")
    for n in (30, 83):
        r = next(r for r in ref if r["no"] == n)
        print(f"  amended {r['no']}: {r['name']} | {r['address']}")

    rik = parse_rik(MANIFEST)
    print(f"RIK stations: {len(rik)}")
    ref_by_no = {r["no"]: r for r in ref}

    # monotonic alignment of the two venue-name sequences
    a = [norm_name(x["name"]) for x in rik]
    b = [norm_name(x["name"]) for x in ref]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    rik_to_ref = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "replace"):
            for k in range(min(i2 - i1, j2 - j1)):
                rik_to_ref[rik[i1 + k]["no"]] = ref[j1 + k]["no"]

    out, mismatches, inherited = [], [], []
    for r in rik:
        no = r["no"]
        src = rik_to_ref.get(no, no)          # fall back to same number
        doc = ref_by_no.get(src) or ref_by_no.get(no)
        address = doc["address"] if doc else ""
        if doc and norm_name(doc["name"]) != norm_name(r["name"]):
            mismatches.append((no, src, r["name"], doc["name"]))
        if src != no:
            inherited.append((no, src))
        out.append({"municipality": MUNI, "no": no, "name": r["name"], "address": address})

    out.sort(key=lambda x: x["no"])
    json.dump(out, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(f"RIK 2023 stations: {len(rik)}; 2022 doc rows: {len(ref)}; "
                 f"locations: {len(out)}\n")
        fh.write(f"number shifts (RIK no -> 2022 doc no): {len(inherited)}\n")
        for no, src in inherited:
            fh.write(f"  RIK {no} -> doc {src}\n")
        fh.write(f"name mismatches (RIK 2023 vs aligned 2022 doc): {len(mismatches)}\n")
        for no, src, x, y in mismatches:
            fh.write(f"  {no:>3} (doc {src:>3}): RIK={x!r}  doc={y!r}\n")
        fh.write("\nall rows:\n")
        for r in out:
            src = rik_to_ref.get(r["no"], r["no"])
            fh.write(f"  {r['no']:>3} <- doc {src:>3}  {r['name'][:44]:<44} {r['address']}\n")

    print(f"locations written: {len(out)} -> {LOC_OUT}")
    print(f"number shifts: {len(inherited)}; name mismatches: {len(mismatches)}")
    for no, src, x, y in mismatches:
        print(f"   {no:>3} (doc {src:>3}): RIK={x!r}  doc={y!r}")
    empty = [r["no"] for r in out if not r["address"]]
    print(f"stations with empty address: {empty}")


if __name__ == "__main__":
    main()
