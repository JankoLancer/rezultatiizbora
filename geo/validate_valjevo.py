#!/usr/bin/env python3
"""Validate the Valjevo artifacts: counts, coordinate nulls, alignment, sources."""
import csv, json, os, re
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(BASE)
MANIFEST = os.path.join(PROJ, "rik_2023_valjevo", "manifest.csv")
LOC = os.path.join(BASE, "valjevo_stations_locations.json")
GEO = os.path.join(BASE, "valjevo_stations_geo.json")
TARGET = 103
# viewbox given to Nominatim: lon_min,lat_min,lon_max,lat_max (corners)
VB_LO_LON, VB_LO_LAT, VB_HI_LON, VB_HI_LAT = 19.186, 44.821, 20.586, 43.721
LON_MIN, LON_MAX = min(VB_LO_LON, VB_HI_LON), max(VB_LO_LON, VB_HI_LON)
LAT_MIN, LAT_MAX = min(VB_LO_LAT, VB_HI_LAT), max(VB_LO_LAT, VB_HI_LAT)

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

# municipality consistency
munis = set(r["municipality"] for r in man)
loc_munis = set(l["municipality"] for l in loc)
print(f"manifest municipality(ies): {munis}; locations municipality(ies): {loc_munis}")

# coords inside viewbox
outside = [(g["no"], g["lat"], g["lon"]) for g in geo
           if g.get("lat") is not None and not (LAT_MIN <= g["lat"] <= LAT_MAX and LON_MIN <= g["lon"] <= LON_MAX)]
print(f"coords outside viewbox: {len(outside)} {outside}")

# duplicate exact coords remaining
dups = [c for c, n in Counter((round(g["lat"], 6), round(g["lon"], 6)) for g in geo
                              if g.get("lat") is not None).items() if n > 1]
print(f"exact duplicate coords remaining: {len(dups)}")

no_addr = [g["no"] for g in geo if not g.get("address")]
print(f"rows missing address: {len(no_addr)} {no_addr}")

print("\n5 sample rows:")
for g in geo[:5]:
    print(f"  {g['no']:>3} | {g['name'][:30]:<30} | {g['address'][:30]:<30} | "
          f"{g['lat']:.5f},{g['lon']:.5f} | {g['source']:<7} | {g['geocoded_with']}")

ok = (len(man) == len(loc) == len(geo) == TARGET and not nulls and not mismatches
      and not outside and loc_munis == munis)
print(f"\nVALIDATION {'PASS' if ok else 'FAIL'}")
