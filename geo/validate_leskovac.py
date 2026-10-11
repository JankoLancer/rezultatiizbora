#!/usr/bin/env python3
"""Validate the Leskovac artifacts: counts, coordinate nulls, alignment, sources,
viewbox containment."""
import csv, json, os, re
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
MANIFEST = os.path.join(PROJ, "rik_2023_leskovac", "manifest.csv")
LOC = os.path.join(BASE, "leskovac_stations_locations.json")
GEO = os.path.join(BASE, "leskovac_stations_geo.json")

# viewbox = lon_min,lat_max,lon_max,lat_min
VBOX = (21.246, 43.545, 22.646, 42.445)

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

# name / number alignment vs RIK 2023
man_by_no = {}
for r in man:
    m = re.match(r"\s*(\d+)\s*-\s*(.*)$", r["station_name"])
    man_by_no[int(m.group(1))] = m.group(2).strip()

mismatches = []
for g in geo:
    ref = man_by_no.get(g["no"])
    if ref is None or ref != g["name"]:
        mismatches.append((g["no"], g["name"], ref))
print(f"name mismatches   : {len(mismatches)}")
for mm in mismatches:
    print("   ", mm)

# duplicate exact coords remaining
dups = [c for c, n in Counter((round(g["lat"], 6), round(g["lon"], 6)) for g in geo).items() if n > 1]
print(f"exact duplicate coords remaining: {len(dups)}")

# missing addresses
no_addr = [g["no"] for g in geo if not g.get("address")]
print(f"rows missing address: {len(no_addr)} {no_addr}")

# viewbox containment
def inside(g):
    lon, lat = g["lon"], g["lat"]
    lon_lo, lon_hi = min(VBOX[0], VBOX[2]), max(VBOX[0], VBOX[2])
    lat_lo, lat_hi = min(VBOX[1], VBOX[3]), max(VBOX[1], VBOX[3])
    return lon_lo <= lon <= lon_hi and lat_lo <= lat <= lat_hi

outside = [g["no"] for g in geo if g.get("lat") is not None and not inside(g)]
print(f"coords outside viewbox: {len(outside)} {outside}")

print("\n5 sample rows:")
for g in geo[:5]:
    print(f"  {g['no']:>3} | {g['name'][:32]:<32} | {(g['address'] or '')[:30]:<30} | "
          f"{g['lat']:.5f},{g['lon']:.5f} | {g['source']:<7} | {g.get('geocoded_with')}")

ok = (len(man) == len(loc) == len(geo) == 194 and not nulls and not mismatches
      and not outside)
print(f"\nVALIDATION {'PASS' if ok else 'FAIL'}")
