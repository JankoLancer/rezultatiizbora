#!/usr/bin/env python3
"""Build geo data for the two special RIK categories:
  * Заводи за извршење кривичних санкција (region 100) - official 2022 doc with addresses
  * Иностранство (region 101) - located by the city/place embedded in the venue name
"""
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import opstina_docs  # noqa: E402
import pipeline_opstina as P  # noqa: E402

SERBIA_VB = "18.7,46.3,23.2,41.7"     # left,top,right,bottom


def nominatim_global(q, cache, cache_path):
    """Global Nominatim lookup (no country filter), via the shared limiter."""
    if q in cache:
        return cache[q]
    res = None
    any_ok = False
    for attempt in range(5):
        try:
            P.limiter.wait()
            r = P.requests.get(P.NOMINATIM, headers=P.H, timeout=30,
                               params={"q": q, "format": "json", "limit": 1})
            if r.status_code == 429:
                P.limiter.penalize(150); continue
            any_ok = True
            d = r.json()
            if d:
                res = {"lat": float(d[0]["lat"]), "lon": float(d[0]["lon"]),
                       "display": d[0].get("display_name", "")}
            break
        except Exception:  # noqa: BLE001
            pass
    if any_ok:
        cache[q] = res
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
    return res

# foreign place to search for, per station number (index = manifest order)
FOREIGN = {
    1: "Vienna", 2: "Vienna", 3: "Vienna", 4: "Salzburg", 5: "Linz", 6: "Brussels",
    7: "Sarajevo", 8: "Banja Luka", 9: "Banja Luka", 10: "Mostar", 11: "Drvar",
    12: "Trebinje", 15: "Bratunac", 16: "Višegrad", 19: "Branjevo Zvornik",
    22: "Rudo", 23: "Mrkonjić Grad", 25: "Novo Goražde", 26: "Sofia",
    27: "Copenhagen", 28: "Rome", 29: "Milan", 30: "Trieste", 31: "Vicenza",
    32: "Valdagno", 33: "Ottawa", 34: "Vancouver", 35: "Toronto", 36: "Nicosia",
    38: "Luxembourg", 39: "Valletta", 40: "Budapest", 41: "Berlin",
    42: "Düsseldorf", 43: "Munich", 44: "Stuttgart", 45: "Frankfurt",
    46: "Hamburg", 47: "Auckland", 48: "Oslo", 49: "Lisbon", 50: "Bucharest",
    51: "Moscow", 53: "Skopje", 54: "Kumanovo", 55: "Washington",
    56: "Chicago", 57: "New York", 58: "Bratislava", 59: "Ljubljana",
    60: "Istanbul", 61: "Abu Dhabi", 62: "London", 63: "Helsinki",
    65: "Strasbourg", 66: "The Hague", 67: "Zagreb", 68: "Vukovar", 69: "Bangui",
    70: "Podgorica", 71: "Herceg Novi", 74: "Prague", 75: "Bern", 76: "Zurich",
    77: "Geneva", 78: "Lugano", 79: "Stockholm", 80: "Malmö", 81: "Madrid",
    # ambiguous venues - best-effort country/town (approx)
    13: "Bijeljina", 14: "Prijedor", 17: "Doboj", 18: "Zvornik",
    20: "Bihać", 21: "Tuzla", 24: "Brčko", 37: "Nicosia",
    52: "Tirana", 64: "Beijing", 72: "Budapest", 73: "Novi Sad",
}


def build_zavodi():
    slug = "zavodi"
    name = "Заводи за извршење кривичних санкција"
    rows = opstina_docs.parse(os.path.join(HERE, "zavodi_ref.doc"))
    by_no = {r["no"]: r for r in rows}
    man = list(csv.DictReader(open(os.path.join(ROOT, "rik_2023_zavodi", "manifest.csv"), encoding="utf-8-sig")))
    cache_path = os.path.join(HERE, f"{slug}_cache.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    loc = []
    for r in man:
        rk = r["station_name"].strip()
        no = int(rk.split(" - ", 1)[0])
        venue = rk.split(" - ", 1)[1].strip()
        d = by_no.get(no, {})
        loc.append({"municipality": name, "no": no, "name": venue,
                    "address": (d.get("address") or "").strip()})
    for s in loc:
        a = P.clean_addr(s["address"])
        hit = None
        for q in ([f"{a}, Србија"] if a else []) + [f"{s['name']}, Србија"]:
            hit = P.nominatim(q, cache, cache_path, SERBIA_VB)
            if hit:
                break
        if hit:
            s["lat"], s["lon"], s["display"] = hit["lat"], hit["lon"], hit.get("display", "")
            s["source"] = "address" if a else "venue"
            s["geocoded_with"] = q
        else:
            s["lat"], s["lon"], s["display"], s["source"] = 44.0, 21.0, "", "center"
    out = os.path.join(HERE, f"{slug}_stations_geo.json")
    json.dump(loc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"name": name, "default_muni": name, "muni_from_manifest": True,
               "geo": f"geo/{slug}_stations_geo.json"},
              open(os.path.join(ROOT, "rik_2023_zavodi", "city.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"zavodi: {len(loc)} rows, {sum(1 for x in loc if x['source']!='center')} geocoded")


def build_inostranstvo():
    slug = "inostranstvo"
    name = "Иностранство"
    man = list(csv.DictReader(open(os.path.join(ROOT, "rik_2023_inostranstvo", "manifest.csv"), encoding="utf-8-sig")))
    cache_path = os.path.join(HERE, f"{slug}_cache.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    loc = []
    for r in man:
        rk = r["station_name"].strip()
        no = int(rk.split(" - ", 1)[0])
        venue = rk.split(" - ", 1)[1].strip()
        q = FOREIGN.get(no, venue)
        hit = nominatim_global(q, cache, cache_path)
        if not hit and q != venue:
            hit = nominatim_global(venue, cache, cache_path)
        if hit:
            lat, lon, disp, src = hit["lat"], hit["lon"], hit.get("display", ""), "address"
        else:
            lat, lon, disp, src = None, None, "", "center"
        loc.append({"municipality": name, "no": no, "name": venue, "address": "",
                    "lat": lat, "lon": lon, "display": disp, "source": src})
    # fill missing with the mean of the geocoded ones (approximate)
    good = [x for x in loc if x["lat"] is not None]
    if good:
        clat = sum(x["lat"] for x in good) / len(good)
        clon = sum(x["lon"] for x in good) / len(good)
    else:
        clat, clon = 44.0, 21.0
    import math
    for x in loc:
        if x["lat"] is None:
            x["lat"], x["lon"] = clat, clon
        x["geocoded_with"] = FOREIGN.get(x["no"], "")
    groups = {}
    for i, s in enumerate(loc):
        groups.setdefault((round(s["lat"], 4), round(s["lon"], 4)), []).append(i)
    for idxs in groups.values():
        for j, i in enumerate(idxs):
            ang = 2 * math.pi * j / len(idxs)
            loc[i]["lat"] += 0.002 * math.sin(ang)
            loc[i]["lon"] += 0.002 * math.cos(ang)
    out = os.path.join(HERE, f"{slug}_stations_geo.json")
    json.dump(loc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"name": name, "default_muni": name, "muni_from_manifest": True,
               "geo": f"geo/{slug}_stations_geo.json"},
              open(os.path.join(ROOT, "rik_2023_inostranstvo", "city.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"inostranstvo: {len(loc)} rows, {sum(1 for x in loc if x['source']!='center')} geocoded")


if __name__ == "__main__":
    build_zavodi()
    build_inostranstvo()
