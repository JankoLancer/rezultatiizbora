#!/usr/bin/env python3
"""Build a compact 2023 registered-voter lookup for the 2026 stations.

The 2026 per-station voter counts are not published in the committee documents
and the public voter-list site does not expose a stable per-station export.
Until they are available, the "missing" view shows the 2023 registered-voter
count for the same municipality and station number, clearly labelled as 2023.

Output: map/odbori-voters.json
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = os.path.join(ROOT, "map", "data.json")
NEW = os.path.join(ROOT, "map", "odbori.json")
OUT = os.path.join(ROOT, "map", "odbori-voters.json")


def norm(s):
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    s = re.sub(r"^(град|општина|градска општина)\s+", "", s)
    return s


def main():
    old = json.load(open(OLD, encoding="utf-8"))["stations"]
    new = json.load(open(NEW, encoding="utf-8"))["stations"]
    lookup = {}
    for s in old:
        reg = s.get("registered")
        if reg is None:
            continue
        for name in (s.get("muni"), s.get("city")):
            if name:
                lookup[(norm(name), s["no"])] = int(reg)
    out = {}
    matched = 0
    for s in new:
        reg = lookup.get((norm(s.get("city")), s["no"]))
        if reg is not None:
            out[f"{s['city_slug']}:{s['no']}"] = reg
            matched += 1
    payload = {
        "meta": {
            "source": "map/data.json — parlamentarni izbori 2023",
            "year": 2023,
            "note": "Broj upisanih birača po biračkom mestu iz 2023. Podaci za 2026. po biračkom mestu nisu objavljeni u RIK dokumentima o odborima.",
            "matched_stations": matched,
            "total_2026_stations": len(new),
        },
        "stations": out,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT}: {matched}/{len(new)} stations, {os.path.getsize(OUT)/1024:.1f} KB")


if __name__ == "__main__":
    main()
