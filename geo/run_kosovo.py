#!/usr/bin/env python3
"""Download + map the 22 Kosovo-region (region 5) municipalities.

No address documents exist for region 5, so every station is placed at its
municipality center (with a small offset). Results/PDFs are downloaded normally.
"""
import csv
import json
import math
import os
import re
import subprocess
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from city_slugs import city_slug  # noqa: E402
from ratelimit import limiter  # noqa: E402

H = {"User-Agent": "izbori-vizualizacija/1.0"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def center_for(name, cache):
    if name in cache:
        return cache[name]
    info = {"lat": None, "lon": None}
    for _ in range(4):
        try:
            limiter.wait()
            r = requests.get(NOMINATIM, headers=H, timeout=30,
                             params={"q": name, "format": "json", "limit": 1,
                                     "viewbox": "19.9,43.3,21.9,41.8", "bounded": 1})
            if r.status_code == 429:
                limiter.penalize(150); continue
            d = r.json()
            if d:
                info = {"lat": float(d[0]["lat"]), "lon": float(d[0]["lon"])}
            break
        except Exception:  # noqa: BLE001
            pass
    cache[name] = info
    return info


def main():
    munis = [m for m in json.load(open("/tmp/opencode/rik_municipalities.json", encoding="utf-8"))
             if m["region"] == 5 and m["stations"] > 0]
    cpath = os.path.join(HERE, "kosovo_centers.json")
    centers = json.load(open(cpath, encoding="utf-8")) if os.path.exists(cpath) else {}
    for m in munis:
        name, val, n = m["name"], m["value"], m["stations"]
        slug = city_slug(name)
        res = os.path.join(ROOT, f"rik_2023_{slug}")
        man = os.path.join(res, "manifest.csv")
        if not (os.path.exists(man) and sum(1 for _ in open(man, encoding="utf-8-sig")) - 1 == n):
            subprocess.run([sys.executable, os.path.join(ROOT, "download_rik_generic.py"),
                            f"rik_2023_{slug}", "341140", "5", f"{name}:{val}"],
                           cwd=ROOT, check=True)
        rows = list(csv.DictReader(open(man, encoding="utf-8-sig")))
        c = center_for(name, centers)
        json.dump(centers, open(cpath, "w", encoding="utf-8"), ensure_ascii=False)
        clat, clon = c.get("lat"), c.get("lon")
        if clat is None:
            clat, clon = 42.66, 21.17   # Kosovo centroid
        loc = []
        for i, r in enumerate(rows):
            rk = r["station_name"].strip()
            mm = re.match(r"^(\d+)\s*-\s*(.*)$", rk)
            no = int(mm.group(1)) if mm else i + 1
            venue = (mm.group(2) if mm else rk).strip()
            loc.append({"municipality": name, "no": no, "name": venue, "address": "",
                        "lat": clat, "lon": clon, "display": f"{name} (centar opštine)",
                        "source": "center"})
        groups = {}
        for i, s in enumerate(loc):
            groups.setdefault((round(s["lat"], 4), round(s["lon"], 4)), []).append(i)
        for idxs in groups.values():
            for j, i in enumerate(idxs):
                ang = 2 * math.pi * j / len(idxs)
                loc[i]["lat"] += 0.0012 * math.sin(ang)
                loc[i]["lon"] += 0.0012 * math.cos(ang) / math.cos(math.radians(loc[i]["lat"]))
        out = os.path.join(HERE, f"{slug}_stations_geo.json")
        json.dump(loc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump({"name": name, "default_muni": name, "muni_from_manifest": True,
                   "geo": f"geo/{slug}_stations_geo.json"},
                  open(os.path.join(res, "city.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"{name}: {len(loc)} stations @ {clat:.4f},{clon:.4f}")
    print("KOSOVO DONE")


if __name__ == "__main__":
    main()
