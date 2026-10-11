#!/usr/bin/env python3
"""Build geo/subotica_stations_locations.json for Grad Subotica.

Aligns the RIK 2023 station manifest (rik_2023_subotica/manifest.csv) with the
addresses parsed from the RIK 2022 referendum decision (subotica_ref_rows.json).
RIK 2023 venue names take precedence; addresses come from the 2022 decision.
"""
import csv
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_subotica", "manifest.csv")
REF = os.path.join(BASE, "subotica_ref_rows.json")
OUT = os.path.join(BASE, "subotica_stations_locations.json")
MUNI = "Град Суботица"


def norm(s):
    s = s.upper()
    for ch in '"„“”':
        s = s.replace(ch, " ")
    s = s.replace("–", "-")
    s = re.sub(r"[^А-ШЂЈЉЊЋЏЂA-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ref = json.load(open(REF, encoding="utf-8"))
    ref_by_no = {r["no"]: r for r in ref}
    rows = list(csv.DictReader(open(MAN, encoding="utf-8-sig")))

    out, mismatches = [], []
    for r in rows:
        rikname = re.sub(r"\s+", " ", r["station_name"].strip())
        no = int(rikname.split(" - ", 1)[0])
        venue = rikname.split(" - ", 1)[1].strip() if " - " in rikname else rikname
        doc = ref_by_no.get(no)
        address = doc["address"] if doc else ""
        if doc and norm(doc["name"]) != norm(venue):
            mismatches.append((no, venue, doc["name"]))
        out.append({"municipality": MUNI, "no": no, "name": venue,
                    "address": address})

    out.sort(key=lambda x: x["no"])
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"manifest stations: {len(rows)}  parsed doc rows: {len(ref)}")
    print(f"locations written: {len(out)} -> {OUT}")
    print(f"name mismatches (RIK 2023 vs 2022 doc): {len(mismatches)}")
    for no, a, b in mismatches:
        print(f"  {no:>3}: RIK='{a}'  doc='{b}'")
    missing = [r["no"] for r in out if not r["address"]]
    print(f"stations with empty address: {missing}")


if __name__ == "__main__":
    main()
