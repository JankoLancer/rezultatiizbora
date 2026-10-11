#!/usr/bin/env python3
"""Validate the Belgrade-g1 deliverables.

Checks:
  * per-municipality RIK 2023 manifest station count vs geo station count
  * null / out-of-range coordinates and source tallies
  * stations whose 2022 address could not be resolved (empty address)
  * prints 5 sample rows
"""
import csv
import json
import os
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_beograd_g1", "manifest.csv")
LOC = os.path.join(BASE, "beograd_g1_locations.json")
GEO = os.path.join(BASE, "beograd_g1_geo.json")

ORDER = ["Градска општина Нови Београд", "Градска општина Земун",
         "Градска општина Сурчин", "Градска општина Барајево"]


def main():
    man = list(csv.DictReader(open(MAN, encoding="utf-8-sig")))
    loc = json.load(open(LOC, encoding="utf-8"))
    geo = json.load(open(GEO, encoding="utf-8"))

    man_c = Counter(r["municipality"] for r in man)
    loc_c = Counter(r["municipality"] for r in loc)
    geo_c = Counter(r["municipality"] for r in geo)
    loc_keys = {(r["municipality"], r["no"]) for r in loc}
    geo_keys = {(r["municipality"], r["no"]) for r in geo}

    print("per-municipality counts (manifest / locations / geo):")
    for m in ORDER:
        flag = "" if man_c[m] == geo_c[m] == loc_c[m] else "  <-- MISMATCH"
        print(f"  {m:<34} {man_c[m]:>4} / {loc_c[m]:>4} / {geo_c[m]:>4}{flag}")

    print(f"\ntotals: manifest={len(man)} locations={len(loc)} geo={len(geo)}")
    print(f"location keys missing from geo: {sorted(loc_keys - geo_keys)}")

    bad = [r for r in geo if r.get("lat") is None or r.get("lon") is None]
    print(f"\nnull coordinates: {len(bad)}")
    for r in bad:
        print("   ", r["municipality"], r["no"], r["name"][:50], r.get("address", "")[:40])

    oob = [r for r in geo if r.get("lat") is not None and not (44.0 <= r["lat"] <= 45.4)]
    oob += [r for r in geo if r.get("lon") is not None and not (19.8 <= r["lon"] <= 21.2)]
    print(f"out-of-Belgrade-range coordinates: {len(oob)}")
    for r in oob[:10]:
        print("   ", r["municipality"], r["no"], round(r["lat"], 4), round(r["lon"], 4))

    src = Counter(r.get("source", "?") for r in geo)
    print(f"\nsources: {dict(src)}")

    empty = [r for r in loc if not r.get("address")]
    print(f"stations with empty 2022 address: {len(empty)}")
    for r in empty[:10]:
        print("   ", r["municipality"], r["no"], r["name"][:50])

    print("\n5 sample rows:")
    for r in geo[:3] + geo[-2:]:
        print(f"  {r['municipality'][-12:]:<12} {r['no']:>3} {r['name'][:34]:<34} "
              f"{r['address'][:30]:<30} {round(r['lat'], 5)},{round(r['lon'], 5)} [{r['source']}] "
              f"{str(r.get('geocoded_with'))[:40]}")


if __name__ == "__main__":
    main()
