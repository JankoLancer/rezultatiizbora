#!/usr/bin/env python3
"""Automated pipeline for one rural municipality ("opstina").

Usage:
  python3 geo/pipeline_opstina.py <slug> [--force-download] [--force-geo]

Reads the spec entry from geo/opstina_spec.json, then:
  1. downloads RIK 2023 results + PDF zapisnici (download_rik_generic.py)
  2. downloads + parses the official referendum address document(s)
  3. aligns doc rows to the RIK 2023 manifest
  4. geocodes addresses inside the municipality bounding box
  5. offsets duplicates, writes geo/<slug>_stations_geo.json + city.json
  6. validates counts / nulls

Resumable: skips steps whose outputs already look complete unless --force-*.
"""
import csv, json, os, re, subprocess, sys, time
from difflib import SequenceMatcher

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import opstina_docs  # noqa: E402
from ratelimit import limiter  # noqa: E402

H = {"User-Agent": "izbori-vizualizacija/1.0 (opstina pipeline)"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^0-9a-zа-шђћљњџј]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def load_spec(slug):
    spec = json.load(open(os.path.join(HERE, "opstina_spec.json"), encoding="utf-8"))
    for s in spec:
        if s["slug"] == slug:
            return s
    raise SystemExit(f"slug {slug} not in opstina_spec.json")


def ensure_download(spec, force=False):
    res = os.path.join(ROOT, f"rik_2023_{spec['slug']}")
    man = os.path.join(res, "manifest.csv")
    if not force and os.path.exists(man):
        n = sum(1 for _ in open(man, encoding="utf-8-sig")) - 1
        if n == spec["stations"]:
            print(f"[{spec['slug']}] results already complete ({n})")
            return
    cmd = [sys.executable, os.path.join(ROOT, "download_rik_generic.py"),
           f"rik_2023_{spec['slug']}", "341140", str(spec["region"]),
           f"{spec['name']}:{spec['value']}"]
    print(f"[{spec['slug']}] downloading: {' '.join(cmd[2:])}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def download_docs(spec):
    paths = []
    for i, url in enumerate(spec["docs"]):
        ext = url.rsplit(".", 1)[-1].lower()
        dest = os.path.join(HERE, f"{spec['slug']}_ref{i}.{ext}")
        if not (os.path.exists(dest) and os.path.getsize(dest) > 0):
            r = requests.get(url, headers=H, timeout=120)
            r.raise_for_status()
            head = r.content[:400].lstrip().lower()
            if head.startswith(b"<") or b"<html" in head:
                print(f"  ! doc link returned HTML (stale?): {url}")
                continue
            open(dest, "wb").write(r.content)
        paths.append(dest)
    return paths


def parse_docs(spec, paths):
    base = None
    for p in paths:
        try:
            rows = opstina_docs.parse(p)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! parse failed {p}: {exc}")
            continue
        rows = [r for r in rows if r["no"] and (r["name"] or r["address"])]
        print(f"  {os.path.basename(p)} -> {len(rows)} rows")
        if base is None:
            base = rows
        else:
            by_no = {r["no"]: r for r in base}
            for r in rows:
                if r["no"] in by_no:
                    by_no[r["no"]].update(r)
                else:
                    best = max(base, key=lambda x: sim(x["name"], r["name"])) if base else None
                    if best is not None and sim(best["name"], r["name"]) > 0.7:
                        best.update(r)
                    else:
                        base.append(r)
    return base or []


def read_manifest(spec):
    res = os.path.join(ROOT, f"rik_2023_{spec['slug']}")
    rows = list(csv.DictReader(open(os.path.join(res, "manifest.csv"), encoding="utf-8-sig")))
    out = []
    for r in rows:
        rk = r["station_name"].strip()
        m = re.match(r"^(\d+)\s*-\s*(.*)$", rk)
        no = int(m.group(1)) if m else 0
        venue = (m.group(2) if m else rk).strip()
        out.append({"station_id": r["station_id"], "no": no, "venue": venue,
                    "muni": r.get("municipality") or spec["name"]})
    return out


def align(spec, man, docs):
    by_no = {d["no"]: d for d in docs}
    loc, mism, noaddr = [], 0, 0
    for m in man:
        d = by_no.get(m["no"])
        # prefer the by-number row when its name reasonably matches the 2023 venue
        if not (d and sim(d.get("name", ""), m["venue"]) >= 0.4):
            best = max(docs, key=lambda x: sim(x["name"], m["venue"])) if docs else None
            if best is not None and sim(best["name"], m["venue"]) >= 0.6:
                d = best
        if d is None:
            d = by_no.get(m["no"])
        if d is None:
            loc.append({"municipality": m["muni"], "no": m["no"], "name": m["venue"],
                        "address": ""})
            mism += 1
            continue
        addr = (d.get("address") or "").strip()
        if not addr:
            noaddr += 1
        if sim(d.get("name", ""), m["venue"]) < 0.4:
            mism += 1
        loc.append({"municipality": m["muni"], "no": m["no"], "name": m["venue"],
                    "address": addr, "_venue": m["venue"], "_docname": d.get("name", "")})
    print(f"[{spec['slug']}] aligned {len(loc)}/{len(man)} "
          f"(name mismatches {mism}, empty addresses {noaddr})")
    return loc


# ---------------------------------------------------------------- geocoding
def get_center(spec):
    cache = os.path.join(HERE, f"{spec['slug']}_center.json")
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    info = {"lat": None, "lon": None, "viewbox": None}
    for attempt in range(4):
        try:
            limiter.wait()
            r = requests.get(NOMINATIM, headers=H, timeout=30,
                             params={"q": f"{spec['name']}, Србија", "format": "json",
                                     "limit": 1, "countrycodes": "rs"})
            if r.status_code == 429:
                limiter.penalize(150)
                continue
            d = r.json()
            if d:
                info["lat"] = float(d[0]["lat"]); info["lon"] = float(d[0]["lon"])
                bb = d[0].get("boundingbox")  # [south, north, west, east]
                if bb:
                    s, n, w, e = [float(x) for x in bb]
                    info["viewbox"] = f"{w:.4f},{n:.4f},{e:.4f},{s:.4f}"
            break
        except Exception:  # noqa: BLE001
            time.sleep(5)
    json.dump(info, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return info


def clean_addr(a):
    """Normalise a Serbian address for Nominatim: drop 'Ул.', 'бр.', 'ББ' etc."""
    a = re.sub(r"(?i)^\s*ул\.?\s*", "", a or "")
    a = re.sub(r"(?i)\bбр\.?\s*", " ", a)
    a = re.sub(r"(?i)\s*б\.?\s*б\.?\s*$", "", a)
    a = re.sub(r"\s+", " ", a).strip(" ,")
    return a


def nominatim(q, cache, cache_path, viewbox):
    if q in cache:
        return cache[q]          # may be a cached miss (None)
    res = None
    any_ok = False
    for bounded in (1, 0):
        params = {"q": q, "format": "json", "limit": 1, "countrycodes": "rs"}
        if viewbox and bounded:
            params.update({"viewbox": viewbox, "bounded": 1})
        done = False
        for attempt in range(5):
            try:
                limiter.wait()
                r = requests.get(NOMINATIM, headers=H, timeout=30, params=params)
                if r.status_code == 429:
                    limiter.penalize(150)
                    continue
                any_ok = True
                d = r.json()
                if d:
                    res = {"lat": float(d[0]["lat"]), "lon": float(d[0]["lon"]),
                           "display": d[0].get("display_name", "")}
                done = True
                break
            except Exception:  # noqa: BLE001
                time.sleep(5)
        if done and res:
            break
    if any_ok:
        cache[q] = res           # negative caching: None means "no result"
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
    return res


def geocode(spec, loc, force=False):
    geo_path = os.path.join(HERE, f"{spec['slug']}_stations_geo.json")
    if not force and os.path.exists(geo_path):
        g = json.load(open(geo_path, encoding="utf-8"))
        if len(g) == len(loc) and not any(x.get("lat") is None for x in g):
            print(f"[{spec['slug']}] geo already complete ({len(g)})")
            return g
    center = get_center(spec)
    vb = center.get("viewbox")
    cache_path = os.path.join(HERE, f"{spec['slug']}_cache.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    mun = spec["name"]
    for i, s in enumerate(loc):
        addr = s.get("address", "").strip()
        addr2 = clean_addr(addr)
        settle = (addr.split(",")[0] or "").strip()
        settle2 = (addr2.split(",")[0] or "").strip()
        cands = []
        if addr2:
            cands.append(f"{addr2}, {mun}, Србија")
        if addr:
            cands += [f"{addr}, {mun}, Србија", f"{addr}, Србија"]
        for st in (settle2, settle):
            if st and st not in (addr, addr2):
                cands.append(f"{st}, {mun}, Србија")
        if settle:
            cands.append(f"{settle}, Србија")
        if s.get("_venue"):
            cands.append(f"{s['_venue']}, {mun}, Србија")
        hit = None
        for q in cands:
            hit = nominatim(q, cache, cache_path, vb)
            if hit:
                hit = dict(hit); hit["q"] = q
                break
        if hit:
            s["lat"], s["lon"], s["display"] = hit["lat"], hit["lon"], hit.get("display", "")
            is_addr = bool(addr and (hit["q"].startswith(addr) or (addr2 and hit["q"].startswith(addr2))))
            s["source"] = "address" if is_addr else "venue"
            s["geocoded_with"] = hit["q"]
        else:
            s["lat"], s["lon"] = center.get("lat"), center.get("lon")
            s["display"] = ""
            s["source"] = "center"
            s["geocoded_with"] = ""
        if (i + 1) % 10 == 0:
            print(f"  geo {i+1}/{len(loc)} ...")
    # guarantee: no null coordinates -> fill from center or from the city centroid
    good = [s for s in loc if s.get("lat") is not None]
    if center.get("lat") is not None:
        clat, clon = center["lat"], center["lon"]
    elif good:
        clat = sum(s["lat"] for s in good) / len(good)
        clon = sum(s["lon"] for s in good) / len(good)
    else:
        clat, clon = 44.0, 21.0
    for s in loc:
        if s.get("lat") is None:
            s["lat"], s["lon"] = clat, clon
            s["source"] = "center"
            s["display"] = s.get("display", "") or ""
    # offset co-located
    import math
    groups = {}
    for i, s in enumerate(loc):
        if s.get("lat") is None:
            continue
        groups.setdefault((round(s["lat"], 4), round(s["lon"], 4)), []).append(i)
    for idxs in groups.values():
        if len(idxs) > 1:
            for j, i in enumerate(idxs):
                ang = 2 * math.pi * j / len(idxs)
                r = 0.0010 + 0.0003 * (j // 10)
                loc[i]["lat"] += r * math.sin(ang)
                loc[i]["lon"] += r * math.cos(ang) / math.cos(math.radians(loc[i]["lat"]))
    for s in loc:
        s.pop("_venue", None); s.pop("_docname", None)
    tmp = geo_path + ".tmp"
    json.dump(loc, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, geo_path)
    print(f"[{spec['slug']}] wrote {geo_path} ({len(loc)})")
    return loc


def write_city_json(spec):
    res = os.path.join(ROOT, f"rik_2023_{spec['slug']}")
    os.makedirs(res, exist_ok=True)
    json.dump({"name": spec["name"], "default_muni": spec["name"], "muni_from_manifest": True,
               "geo": f"geo/{spec['slug']}_stations_geo.json"},
              open(os.path.join(res, "city.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def main():
    slug = sys.argv[1]
    force_dl = "--force-download" in sys.argv
    force_geo = "--force-geo" in sys.argv
    no_geo = "--no-geo" in sys.argv
    spec = load_spec(slug)
    print(f"=== {spec['name']} ({slug}) region {spec['region']} value {spec['value']} "
          f"expected {spec['stations']} ===")
    ensure_download(spec, force_dl)
    man = read_manifest(spec)
    if len(man) != spec["stations"]:
        print(f"  ! manifest {len(man)} != expected {spec['stations']}")
    doc_paths = download_docs(spec)
    docs = parse_docs(spec, doc_paths)
    loc = align(spec, man, docs)
    if no_geo:
        out = os.path.join(HERE, f"{spec['slug']}_stations_locations.json")
        json.dump(loc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"wrote {out} (no-geo)")
        return
    geo = geocode(spec, loc, force_geo)
    write_city_json(spec)
    nulls = sum(1 for x in geo if x.get("lat") is None)
    src = {}
    for x in geo:
        src[x.get("source", "?")] = src.get(x.get("source", "?"), 0) + 1
    print(f"RESULT {slug}: stations={len(man)} geo={len(geo)} nulls={nulls} sources={src}")


if __name__ == "__main__":
    main()
