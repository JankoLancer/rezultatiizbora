#!/usr/bin/env python3
"""Validate the Врање artifacts: counts, coordinate nulls, alignment, sources, viewbox."""
import csv, json, os
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
MANIFEST = os.path.join(PROJ, "rik_2023_vranje", "manifest.csv")
LOC = os.path.join(BASE, "vranje_stations_locations.json")
GEO = os.path.join(BASE, "vranje_stations_geo.json")
VIEWBOX = (21.198, 42.004, 22.598, 43.104)   # lon_min, lat_min, lon_max, lat_max

man = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
loc = json.load(open(LOC, encoding="utf-8"))
geo = json.load(open(GEO, encoding="utf-8"))

print(f"manifest stations : {len(man)}")
print(f"locations rows    : {len(loc)}")
print(f"geo rows          : {len(geo)}")

nulls = [g["no"] for g in geo if g.get("lat") is None or g.get("lon") is None]
print(f"null coordinates  : {len(nulls)} {nulls}")

sources = Counter(g.get("source") for g in geo)
print(f"sources           : {dict(sources)}")

# name / number alignment vs RIK 2023 (compare per municipality name -> (no,name))
import re
man_by = {}
for r in man:
    m = re.match(r"\s*(\d+)\s*-\s*(.*)$", r["station_name"])
    man_by[(r["municipality"], int(m.group(1)))] = m.group(2).strip()

mismatches = []
for g in geo:
    ref = man_by.get((g["municipality"], g["no"]))
    if ref is None or ref != g["name"]:
        mismatches.append((g["municipality"], g["no"], g["name"], ref))
print(f"name mismatches   : {len(mismatches)}")
for mm in mismatches:
    print("   ", mm)

# out-of-viewbox
ov = []
for g in geo:
    if g.get("lat") is None:
        continue
    lon, lat = g["lon"], g["lat"]
    if not (VIEWBOX[0] <= lon <= VIEWBOX[2] and VIEWBOX[1] <= lat <= VIEWBOX[3]):
        ov.append((g["no"], g["name"], lat, lon, g["source"]))
print(f"out of viewbox    : {len(ov)}")
for o in ov:
    print("   ", o)

# duplicate exact coords remaining
dups = [c for c, n in Counter((round(g["lat"], 6), round(g["lon"], 6)) for g in geo).items() if n > 1]
print(f"exact duplicate coords remaining: {len(dups)}")

# missing addresses
no_addr = [g["no"] for g in geo if not g.get("address")]
print(f"rows missing address: {len(no_addr)} {no_addr}")

print("\n5 sample rows:")
for g in geo[:5]:
    print(f"  {g['municipality'][:9]:<9} {g['no']:>2} | {g['name'][:30]:<30} | "
          f"{g['address'][:30]:<30} | {g['lat']:.5f},{g['lon']:.5f} | {g['source']:<7} | "
          f"{g.get('geocoded_with')}")

ok = (len(man) == len(loc) == len(geo) == 106 and not nulls and not mismatches
      and not ov and not no_addr)
print(f"\nVALIDATION {'PASS' if ok else 'FAIL'}")
