#!/usr/bin/env python3
"""Validate the Grad Kraljevo pipeline outputs."""
import csv
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_kraljevo", "manifest.csv")
REF = os.path.join(BASE, "kraljevo_ref_rows.json")
LOC = os.path.join(BASE, "kraljevo_stations_locations.json")
GEO = os.path.join(BASE, "kraljevo_stations_geo.json")
MUNI = "Град Краљево"


def main():
    man = list(csv.DictReader(open(MAN, encoding="utf-8-sig")))
    ref = json.load(open(REF, encoding="utf-8"))
    loc = json.load(open(LOC, encoding="utf-8"))
    geo = json.load(open(GEO, encoding="utf-8"))

    rik_names = {}
    for r in man:
        nm = re.sub(r"\s+", " ", r["station_name"].strip())
        no, venue = nm.split(" - ", 1)
        rik_names[int(no)] = venue.strip()

    print(f"RIK 2023 manifest stations : {len(man)}")
    print(f"2022 doc parsed rows       : {len(ref)}")
    print(f"locations rows             : {len(loc)}")
    print(f"geo rows                   : {len(geo)}")

    errs = []
    if len(man) != 129:
        errs.append(f"expected 129 RIK stations, got {len(man)}")
    if len(loc) != len(man):
        errs.append(f"locations count {len(loc)} != manifest {len(man)}")
    if len(geo) != len(loc):
        errs.append(f"geo count {len(geo)} != locations {len(loc)}")

    nos = [r["no"] for r in geo]
    if nos != sorted(nos):
        errs.append("geo not sorted by no")
    if len(set(nos)) != len(nos):
        errs.append("duplicate station numbers in geo")
    if set(nos) != set(rik_names):
        errs.append("geo station numbers != RIK numbers")

    for r in geo:
        if r.get("municipality") != MUNI:
            errs.append(f"station {r['no']}: bad municipality {r.get('municipality')!r}")
        if r["name"] != rik_names.get(r["no"], r["name"]):
            errs.append(f"station {r['no']}: name != RIK 2023 ({r['name']!r})")
        if r.get("lat") is None or r.get("lon") is None:
            errs.append(f"station {r['no']}: null coordinates")
        else:
            if not (43.2 <= r["lat"] <= 44.1 and 20.2 <= r["lon"] <= 21.2):
                errs.append(f"station {r['no']}: coords out of Kraljevo bbox ({r['lat']},{r['lon']})")
        if not r.get("address"):
            errs.append(f"station {r['no']}: empty address")

    src = {}
    for r in geo:
        src[r.get("source")] = src.get(r.get("source"), 0) + 1
    print(f"sources                    : {src}")
    print(f"null coordinates           : {sum(1 for r in geo if r.get('lat') is None or r.get('lon') is None)}")
    print(f"distinct coordinates       : {len(set((round(r['lat'],5), round(r['lon'],5)) for r in geo))}")

    print("\n5 sample rows:")
    for r in geo[:5]:
        print(f"  {r['municipality']} | {r['no']:>3} | {r['name'][:34]:<34} | {r['address'][:30]:<30} | "
              f"{r['lat']:.5f},{r['lon']:.5f} | {r['source']} | {r.get('geocoded_with')}")

    if errs:
        print(f"\nVALIDATION FAILED ({len(errs)} issues):")
        for e in errs[:30]:
            print("  -", e)
        raise SystemExit(1)
    print("\nVALIDATION OK")


if __name__ == "__main__":
    main()
