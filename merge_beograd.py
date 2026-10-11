#!/usr/bin/env python3
"""Merge the four Belgrade groups (g1..g4) into one city dataset.

Creates:
  rik_2023_beograd/{json/, documents/, manifest.csv, votes_by_station.csv}
  geo/beograd_stations_locations.json
  geo/beograd_stations_geo.json
Idempotent: rebuilds the merged dirs from the group dirs.
"""
import csv, json, os, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
GROUPS = ["g1", "g2", "g3", "g4"]
DST = os.path.join(ROOT, "rik_2023_beograd")


def merge_dir(name):
    out = os.path.join(DST, name)
    os.makedirs(out, exist_ok=True)
    n = 0
    for g in GROUPS:
        src = os.path.join(ROOT, f"rik_2023_beograd_{g}", name)
        if not os.path.isdir(src):
            continue
        for f in os.listdir(src):
            s = os.path.join(src, f)
            d = os.path.join(out, f)
            if os.path.isfile(s) and not os.path.exists(d):
                shutil.copy2(s, d); n += 1
    return n


def merge_csv(name):
    rows, seen = [], set()
    fields = None
    for g in GROUPS:
        p = os.path.join(ROOT, f"rik_2023_beograd_{g}", name)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8-sig") as fh:
            r = csv.DictReader(fh)
            fields = fields or r.fieldnames
            for row in r:
                key = row.get("station_id")
                if key and key not in seen:
                    seen.add(key); rows.append(row)
    out = os.path.join(DST, name)
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    return len(rows)


def merge_json_list(prefix, outname, keyf):
    out, seen = [], set()
    for g in GROUPS:
        p = os.path.join(ROOT, "geo", f"beograd_{g}_{prefix}.json")
        if not os.path.exists(p):
            continue
        for row in json.load(open(p, encoding="utf-8")):
            k = keyf(row)
            if k not in seen:
                seen.add(k); out.append(row)
    json.dump(out, open(os.path.join(ROOT, "geo", outname), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return len(out)


if __name__ == "__main__":
    os.makedirs(os.path.join(DST, "json"), exist_ok=True)
    os.makedirs(os.path.join(DST, "documents"), exist_ok=True)
    print("copied json  :", merge_dir("json"))
    print("copied docs  :", merge_dir("documents"))
    print("manifest rows:", merge_csv("manifest.csv"))
    print("votes rows   :", merge_csv("votes_by_station.csv"))
    n1 = merge_json_list("locations", "beograd_stations_locations.json", lambda r: (r["municipality"], r["no"]))
    n2 = merge_json_list("geo", "beograd_stations_geo.json", lambda r: (r["municipality"], r["no"]))
    print("locations    :", n1)
    print("geo (coords) :", n2, "| null:", sum(1 for r in json.load(open(os.path.join(ROOT, "geo", "beograd_stations_geo.json"), encoding="utf-8")) if r.get("lat") is None))
