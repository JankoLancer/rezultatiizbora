#!/usr/bin/env python3
"""Validate the Šabac artifacts: counts, coordinate nulls, alignment, sources,
viewbox containment and duplicate coordinates."""
import csv, json, os, re
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
MANIFEST = os.path.join(PROJ, "rik_2023_sabac", "manifest.csv")
LOC = os.path.join(BASE, "sabac_stations_locations.json")
GEO = os.path.join(BASE, "sabac_stations_geo.json")

# viewbox: lon_min, lat_max, lon_max, lat_min  (same string as the geocoder)
VIEWBOX = "18.995,45.307,20.395,44.207"
vb_lon_min, vb_lat_max, vb_lon_max, vb_lat_min = (float(x) for x in VIEWBOX.split(","))

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

# viewbox containment
outside = [g["no"] for g in geo if g["lat"] is not None and not (
    vb_lon_min <= g["lon"] <= vb_lon_max and vb_lat_min <= g["lat"] <= vb_lat_max)]
print(f"coords outside viewbox: {len(outside)} {outside}")

# missing addresses
no_addr = [g["no"] for g in geo if not g.get("address")]
print(f"rows missing address: {len(no_addr)} {no_addr}")

print("\n5 sample rows:")
for g in geo[:5]:
    print(f"  {g['no']:>3} | {g['name'][:32]:<32} | {str(g['address'])[:34]:<34} | "
          f"{g['lat']:.5f},{g['lon']:.5f} | {g['source']:<7} | {g.get('geocoded_with')}")

ok = (len(man) == len(loc) == len(geo) == 100 and not nulls and not mismatches
      and not outside and not dups)
print(f"\nVALIDATION {'PASS' if ok else 'FAIL'}")
