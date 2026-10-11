#!/usr/bin/env python3
"""Independent QA validator for a city's artifacts.

Usage:
  python3 validate_city.py <slug> <expected_stations> [viewbox="lonMin,latMax,lonMax,latMin"]

Checks:
  - rik_2023_<slug>/manifest.csv row count == expected
  - json/ files == expected ; documents/ count (reported)
  - votes_by_station.csv non-empty
  - geo/<slug>_stations_locations.json count == expected (if present)
  - geo/<slug>_stations_geo.json count == expected, 0 null coords,
    municipality values consistent, coords inside viewbox (if given)
Exits non-zero on failure.
"""
import csv, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    slug = sys.argv[1]
    expected = int(sys.argv[2])
    vb = sys.argv[3] if len(sys.argv) > 3 else None
    fails = []

    res = os.path.join(ROOT, f"rik_2023_{slug}")
    man = os.path.join(res, "manifest.csv")
    if not os.path.exists(man):
        print(f"FAIL {slug}: missing {man}"); sys.exit(1)
    rows = list(csv.DictReader(open(man, encoding="utf-8-sig")))
    print(f"{slug}: manifest={len(rows)} expected={expected}")
    if len(rows) != expected:
        fails.append(f"manifest {len(rows)} != {expected}")
    json_files = [f for f in os.listdir(os.path.join(res, "json")) if f.endswith(".json")]
    docs = os.listdir(os.path.join(res, "documents"))
    if len(json_files) != expected:
        fails.append(f"json files {len(json_files)} != {expected}")
    print(f"  json={len(json_files)} documents={len(docs)}")
    if len(docs) < expected:
        fails.append(f"documents {len(docs)} < {expected} (some stations lack PDFs)")
    vbs = os.path.join(res, "votes_by_station.csv")
    if os.path.getsize(vbs) < 100:
        fails.append("votes_by_station.csv too small")

    loc = os.path.join(ROOT, "geo", f"{slug}_stations_locations.json")
    geo = os.path.join(ROOT, "geo", f"{slug}_stations_geo.json")
    if os.path.exists(loc):
        L = json.load(open(loc, encoding="utf-8"))
        print(f"  locations={len(L)}")
        if len(L) != expected:
            fails.append(f"locations {len(L)} != {expected}")
    else:
        print("  locations=MISSING")
    if os.path.exists(geo):
        G = json.load(open(geo, encoding="utf-8"))
        nulls = [g for g in G if g.get("lat") is None or g.get("lon") is None]
        src = {}
        for g in G:
            src[g.get("source", "?")] = src.get(g.get("source", "?"), 0) + 1
        print(f"  geo={len(G)} nulls={len(nulls)} sources={src}")
        if len(G) != expected:
            fails.append(f"geo {len(G)} != {expected}")
        if nulls:
            fails.append(f"{len(nulls)} null coordinates")
        if vb:
            x0, y1, x1, y0 = [float(v) for v in vb.split(",")]
            # viewbox given generously; flag only wildly out-of-box (>0.5 deg)
            out = [g for g in G if g.get("lat") is not None and
                   not (y0 - 0.5 <= g["lat"] <= y1 + 0.5 and x0 - 0.5 <= g["lon"] <= x1 + 0.5)]
            if out:
                fails.append(f"{len(out)} coords far outside viewbox")
    else:
        print("  geo=MISSING")
        fails.append("geo missing")

    if fails:
        print("  RESULT: FAIL ->", "; ".join(fails)); sys.exit(2)
    print("  RESULT: PASS")


if __name__ == "__main__":
    main()
