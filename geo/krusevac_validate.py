#!/usr/bin/env python3
"""Validate the Grad Krusevac artifacts and print a summary."""
import csv
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_krusevac", "manifest.csv")
REF = os.path.join(BASE, "krusevac_ref_rows.json")
LOC = os.path.join(BASE, "krusevac_stations_locations.json")
GEO = os.path.join(BASE, "krusevac_stations_geo.json")


def norm(s):
    s = s.upper()
    for ch in '"„“”':
        s = s.replace(ch, " ")
    return " ".join(s.split())


def main():
    man = list(csv.DictReader(open(MAN, encoding="utf-8-sig")))
    ref = {r["no"]: r for r in json.load(open(REF, encoding="utf-8"))}
    loc = json.load(open(LOC, encoding="utf-8"))
    geo = json.load(open(GEO, encoding="utf-8"))

    print(f"manifest stations : {len(man)}")
    print(f"2022 doc rows     : {len(ref)}")
    print(f"locations rows    : {len(loc)}")
    print(f"geo rows          : {len(geo)}")

    rik_names = {}
    for r in man:
        n = r["station_name"].strip()
        rik_names[int(n.split(" - ", 1)[0])] = n.split(" - ", 1)[1].strip()

    report_path = os.path.join(BASE, "krusevac_align_report.json")
    align = {a["no"]: a for a in json.load(open(report_path, encoding="utf-8"))["alignment"]}
    mism = []
    for no in sorted(rik_names):
        a = align.get(no, {})
        ref_no = a.get("ref_no")
        if isinstance(ref_no, int) and ref_no in ref \
                and norm(rik_names[no]) != norm(ref[ref_no]["name"]):
            mism.append((no, ref_no, rik_names[no], ref[ref_no]["name"]))
    print(f"\nname mismatches (RIK 2023 vs aligned 2022 row): {len(mism)}")
    for no, ref_no, a, b in mism:
        print(f"  {no:>3} (ref {ref_no:>3}): RIK='{a}'  doc='{b}'")

    empty = [r["no"] for r in loc if not r.get("address")]
    print(f"stations with empty address: {len(empty)} {empty}")

    nulls = [s["no"] for s in geo if s.get("lat") is None or s.get("lon") is None]
    print(f"\nstations missing coordinates: {len(nulls)} {nulls}")

    src = {}
    for s in geo:
        src[s.get("source")] = src.get(s.get("source"), 0) + 1
    print("source counts:", src)

    outside = [s["no"] for s in geo
               if not (20.9 < (s.get("lon") or 0) < 21.9 and 43.2 < (s.get("lat") or 0) < 44.0)]
    print("coords outside Krusevac bounding box:", outside)

    print("\nsample rows:")
    for s in geo[:5]:
        print(f"  {s['no']:>3} {s['name'][:34]:<34} {s['address'][:30]:<30} "
              f"{round(s['lat'],4)},{round(s['lon'],4)} [{s['source']}]")


if __name__ == "__main__":
    main()
