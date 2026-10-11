#!/usr/bin/env python3
"""Validate the Belgrade g3 artifacts (STEP 6).

Compares the RIK 2023 manifest against the parsed 2022 document using the same
normalisation as the aligner, so that only *genuine* differences (re-matches,
renames and newly-added 2023 venues with no 2022 address) are reported.
"""
import csv
import importlib.util
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_beograd_g3", "manifest.csv")
LOC = os.path.join(BASE, "beograd_g3_locations.json")
GEO = os.path.join(BASE, "beograd_g3_geo.json")
REF = os.path.join(BASE, "beograd_g3_ref_rows.json")

spec = importlib.util.spec_from_file_location(
    "bg3build", os.path.join(BASE, "beograd_g3_build_locations.py"))
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

man = list(csv.DictReader(open(MAN, encoding="utf-8-sig")))
loc = json.load(open(LOC, encoding="utf-8"))
geo = json.load(open(GEO, encoding="utf-8"))
doc = json.load(open(REF, encoding="utf-8"))
ref_by = {(r["municipality"], r["no"]): r for r in doc}

MUNIS = ["Градска општина Вождовац", "Градска општина Звездара",
         "Градска општина Врачар", "Градска општина Стари Град"]
print(f"manifest stations: {len(man)}  locations: {len(loc)}  geo: {len(geo)}  "
      f"parsed 2022 rows: {len(doc)}")
for m in MUNIS:
    print(f"  {m}: manifest={sum(1 for r in man if r['municipality'] == m)} "
          f"locations={sum(1 for r in loc if r['municipality'] == m)}")

nulls = [s for s in geo if s.get("lat") is None or s.get("lon") is None]
print(f"\nnull coordinates: {len(nulls)}")
for s in nulls:
    print("   NULL", s["municipality"], s["no"], s["name"])

lats = [s["lat"] for s in geo]
lons = [s["lon"] for s in geo]
print(f"coordinate range: lat {min(lats):.4f}..{max(lats):.4f}  "
      f"lon {min(lons):.4f}..{max(lons):.4f}")

# meaningful mismatch classification
cats = {"rebound": [], "inherited": [], "unresolved": []}
for r in man:
    m = r["municipality"]
    nm = r["station_name"].strip()
    no = int(nm.split(" - ", 1)[0])
    venue = nm.split(" - ", 1)[1].strip() if " - " in nm else nm
    d = ref_by.get((m, no))
    vsig = B.sig_tokens(venue)
    if d is not None and vsig == B.sig_tokens(d["name"]):
        continue  # cosmetic only (suffixes/quotes) -> same address
    cand = [x for x in doc if x["municipality"] == m
            and B.sig_tokens(x["name"]) == vsig and vsig]
    if cand and cand[0]["no"] != no:
        cats["rebound"].append((m, no, venue, cand[0]["no"], cand[0]["name"]))
    elif d and (vsig & B.sig_tokens(d["name"])):
        cats["inherited"].append((m, no, venue, d["name"]))
    else:
        cats["unresolved"].append((m, no, venue))

print(f"\nname differences (RIK 2023 vs 2022): rebound={len(cats['rebound'])} "
      f"inherited={len(cats['inherited'])} unresolved/new={len(cats['unresolved'])}")
for m, no, venue, dno, dname in cats["rebound"]:
    print(f"   rebound    {m.split()[-1]:<10} {no:>3} {venue[:38]:<38} -> 2022 #{dno} {dname[:30]}")
for m, no, venue, dname in cats["inherited"]:
    print(f"   inherited  {m.split()[-1]:<10} {no:>3} {venue[:38]:<38} ~ {dname[:34]}")
for m, no, venue in cats["unresolved"]:
    print(f"   new-2023   {m.split()[-1]:<10} {no:>3} {venue[:44]:<44} (no 2022 address)")

src = {}
for s in geo:
    src[s.get("source")] = src.get(s.get("source"), 0) + 1
print("\nsources:", src)

empty = [(s["municipality"], s["no"], s["name"]) for s in loc if not s["address"].strip()]
print(f"locations with empty address: {len(empty)}")

print("\nsample rows:")
sample = loc[:2] + loc[100:102] + loc[200:201] + loc[-2:]
for s in sample:
    g = next((x for x in geo if x["municipality"] == s["municipality"]
              and x["no"] == s["no"]), {})
    print(f"   {s['municipality'].split()[-1]:<10} {s['no']:>3} {s['name'][:30]:<30} "
          f"{s['address'][:28]:<28} {round(g.get('lat', 0), 5)},{round(g.get('lon', 0), 5)} "
          f"[{g.get('source')}]")
