#!/usr/bin/env python3
"""Build geo/kraljevo_stations_locations.json for Grad Kraljevo.

Aligns the RIK 2023 station manifest (rik_2023_kraljevo/manifest.csv) with the
addresses parsed from the RIK 2022 referendum decision
(geo/kraljevo_ref_rows.json).  RIK 2023 venue names take precedence; addresses
come from the 2022 decision.

The 2023 poll has 129 stations vs 130 in 2022 (one 2022 station was dropped),
so station numbers are not a reliable one-to-one key across the whole range.
We therefore align the two name sequences with difflib.SequenceMatcher (which
infers the single deleted station and keeps the mapping monotonic) and then
report every name mismatch between the aligned pair.
"""
import csv
import json
import os
import re
from difflib import SequenceMatcher

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_kraljevo", "manifest.csv")
REF = os.path.join(BASE, "kraljevo_ref_rows.json")
OUT = os.path.join(BASE, "kraljevo_stations_locations.json")
MUNI = "Град Краљево"


def norm(s):
    s = s.upper()
    for ch in '"„“”':
        s = s.replace(ch, " ")
    s = re.sub(r"[^А-ШЂЈЉЊЋЏЂA-Z0-9 ]", " ", s)
    s = re.sub(r"\bОШ\b", "ОСНОВНА ШКОЛА", s)
    s = re.sub(r"\bОСНОВНО\b", "ОСНОВНА", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_rik(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        nm = re.sub(r"\s+", " ", r["station_name"].strip())
        if " - " in nm:
            no, venue = nm.split(" - ", 1)
        else:
            no, venue = nm, ""
        out.append({"no": int(no), "name": venue.strip()})
    return out


def main():
    rik = parse_rik(MAN)
    ref = json.load(open(REF, encoding="utf-8"))
    ref_by_no = {r["no"]: r for r in ref}

    # monotonic alignment of the two venue-name sequences
    a = [norm(x["name"]) for x in rik]
    b = [norm(x["name"]) for x in ref]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    rik_to_ref = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" or tag == "replace":
            for k in range(min(i2 - i1, j2 - j1)):
                rik_to_ref[rik[i1 + k]["no"]] = ref[j1 + k]["no"]
        # 'insert' (extra 2022 rows) / 'delete' (extra 2023 rows) left unmapped

    out, mismatches, inherited = [], [], []
    for r in rik:
        no = r["no"]
        src = rik_to_ref.get(no, no)          # fall back to same number
        doc = ref_by_no.get(src)
        if doc is None:
            doc = ref_by_no.get(no)
        address = doc["address"] if doc else ""
        if doc and norm(doc["name"]) != norm(r["name"]):
            mismatches.append((no, src, r["name"], doc["name"]))
        if src != no:
            inherited.append((no, src))
        out.append({"municipality": MUNI, "no": no, "name": r["name"],
                    "address": address})

    out.sort(key=lambda x: x["no"])
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"RIK 2023 stations: {len(rik)}  parsed 2022 doc rows: {len(ref)}")
    print(f"locations written: {len(out)} -> {OUT}")
    print(f"number shifts (RIK no -> 2022 doc no): {len(inherited)}")
    for no, src in inherited[:6]:
        print(f"   RIK {no} -> doc {src}")
    if len(inherited) > 6:
        print(f"   ... (+{len(inherited)-6} more)")
    print(f"name mismatches (RIK 2023 vs aligned 2022 doc): {len(mismatches)}")
    for no, src, x, y in mismatches:
        print(f"   {no:>3} (doc {src:>3}): RIK='{x}'  doc='{y}'")
    missing = [r["no"] for r in out if not r["address"]]
    print(f"stations with empty address: {missing}")


if __name__ == "__main__":
    main()
