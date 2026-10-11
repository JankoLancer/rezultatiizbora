#!/usr/bin/env python3
"""Validate the Grad Subotica artifacts and print a summary."""
import csv
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_subotica", "manifest.csv")
LOC = os.path.join(BASE, "subotica_stations_locations.json")
GEO = os.path.join(BASE, "subotica_stations_geo.json")


def norm(s):
    return " ".join(s.upper().replace('"', " ").replace("„", " ").replace("“", " ")
                    .replace("”", " ").split())


def main():
    man = list(csv.DictReader(open(MAN, encoding="utf-8-sig")))
    loc = json.load(open(LOC, encoding="utf-8"))
    geo = json.load(open(GEO, encoding="utf-8"))

    print(f"manifest stations : {len(man)}")
    print(f"locations rows    : {len(loc)}")
    print(f"geo rows          : {len(geo)}")

    rik_names = {}
    for r in man:
        n = r["station_name"].strip()
        rik_names[int(n.split(" - ", 1)[0])] = n.split(" - ", 1)[1].strip()

    # name mismatches vs 2022 reference
    ref_path = os.path.join(BASE, "subotica_ref_rows.json")
    ref = {r["no"]: r for r in json.load(open(ref_path, encoding="utf-8"))}
    mism = [(no, rik_names[no], ref[no]["name"]) for no in sorted(rik_names)
            if no in ref and norm(rik_names[no]) != norm(ref[no]["name"])]
    print(f"\nname mismatches (RIK 2023 vs 2022 doc): {len(mism)}")
    for no, a, b in mism:
        print(f"  {no:>3}: RIK='{a}'  doc='{b}'")

    nulls = [s["no"] for s in geo if s.get("lat") is None or s.get("lon") is None]
    print(f"\nstations missing coordinates: {len(nulls)} {nulls}")

    src = {}
    for s in geo:
        src[s.get("source")] = src.get(s.get("source"), 0) + 1
    print("source counts:", src)

    outside = [s["no"] for s in geo
               if not (19.0 < (s.get("lon") or 0) < 20.3 and 45.5 < (s.get("lat") or 0) < 46.5)]
    print("coords outside Subotica bounding box:", outside)

    print("\nsample rows:")
    for s in geo[:5]:
        print(f"  {s['no']:>3} {s['name'][:34]:<34} {s['address'][:30]:<30} "
              f"{round(s['lat'],4)},{round(s['lon'],4)} [{s['source']}]")


if __name__ == "__main__":
    main()
