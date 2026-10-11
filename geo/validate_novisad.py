#!/usr/bin/env python3
"""Validate the Novi Sad artifacts (STEP 6)."""
import csv, json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_novisad", "manifest.csv")
LOC = os.path.join(BASE, "novisad_stations_locations.json")
GEO = os.path.join(BASE, "novisad_stations_geo.json")
DOC = os.path.join(BASE, "novisad_ref_rows.json")
_QUOTES = "„“”\"'❝❞«»"


def norm(s):
    s = s.upper()
    for q in _QUOTES:
        s = s.replace(q, " ")
    s = re.sub(r"[^0-9A-ZА-ШЂЈЉЊЋЏЂ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


man = list(csv.DictReader(open(MAN, encoding="utf-8-sig")))
loc = json.load(open(LOC, encoding="utf-8"))
geo = json.load(open(GEO, encoding="utf-8"))
doc = json.load(open(DOC, encoding="utf-8"))
doc_by_no = {d["no"]: d for d in doc}

print(f"manifest stations: {len(man)}")
print(f"locations rows:    {len(loc)}")
print(f"geo rows:          {len(geo)}")
print(f"parsed doc rows:   {len(doc)}")

nulls = [(s["no"], s["name"]) for s in geo if s.get("lat") is None or s.get("lon") is None]
print(f"geo rows with null coords: {len(nulls)}")
for n in nulls:
    print("   NULL", n)

mism = []
for r in man:
    nm = r["station_name"].strip()
    num = int(nm.split(" - ", 1)[0])
    venue = nm.split(" - ", 1)[1].strip() if " - " in nm else nm
    d = doc_by_no.get(num)
    if d and norm(venue) != norm(d["name"]):
        mism.append((num, venue, d["name"]))
print(f"name mismatches (doc vs RIK 2023): {len(mism)}")
for m in mism:
    print(f"   {m[0]:>3} RIK={m[1][:38]:<38} DOC={m[2][:38]}")

src = {}
for s in geo:
    src[s.get("source")] = src.get(s.get("source"), 0) + 1
print("sources:", src)

print("\nsample rows:")
for s in loc[:3] + loc[len(loc)//2:len(loc)//2+1] + loc[-1:]:
    g = next((x for x in geo if x["no"] == s["no"]), {})
    print(f"   {s['no']:>3} {s['name'][:32]:<32} {s['address'][:34]:<34} "
          f"{g.get('lat')},{g.get('lon')} [{g.get('source')}]")
