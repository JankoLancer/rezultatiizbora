#!/usr/bin/env python3
"""Build geo/vrsac_stations_locations.json for ГРАД ВРШАЦ (RIK 2023).

Uses the shared generic doc parser (geo/opstina_docs.py) on the official
"glasacka mesta" document, then aligns the parsed rows to the RIK 2023
manifest by station number (with a name-similarity fallback).

The Vrsac document has many wrapped continuation rows (the "podrucje" column
spans multiple physical lines) which pushes the numbered/sequential ratio of
the generic parser below its threshold, so it parses in sequential mode and
mis-splits station 10 ("... ЕЛЕКТРОДИСТРИБУЦИJА ... / огранак ВРШАЦ"). We merge
that one wrapped continuation row back before aligning. No shared file is
modified.

Output rows: {"municipality": "Град Вршац", "no": <int>, "name": <RIK venue>,
              "address": <doc address>}
"""
import csv
import json
import os
import re
import sys
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import opstina_docs  # noqa: E402

SLUG = "vrsac"
MUNI = "Град Вршац"
DOC = os.path.join(HERE, f"{SLUG}_ref.doc")
MANIFEST = os.path.join(ROOT, f"rik_2023_{SLUG}", "manifest.csv")
OUT = os.path.join(HERE, f"{SLUG}_stations_locations.json")
REPORT = os.path.join(HERE, f"{SLUG}_align_report.txt")


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^0-9a-zа-шђћљњџј]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def parse_doc():
    rows = opstina_docs.parse(DOC)
    rows = [r for r in rows if r.get("no") and (r.get("name") or r.get("address"))]
    # Merge the known wrapped continuation of station 10 ("огранак ВРШАЦ",
    # address "173-175") back into the previous row.
    merged = []
    for r in rows:
        name = (r.get("name") or "").strip()
        addr = (r.get("address") or "").strip()
        if merged and name in ("огранак ВРШАЦ",) and re.match(r"^[\d\-/]+$", addr):
            prev = merged[-1]
            prev["name"] = (prev["name"] + " " + name).strip()
            prev["address"] = (prev["address"] + " " + addr).strip()
            continue
        merged.append(dict(r))
    # Renumber sequentially to guarantee 1..N
    for i, r in enumerate(merged, 1):
        r["no"] = i
    return merged


def read_manifest():
    out = []
    with open(MANIFEST, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            raw = (r.get("station_name") or "").strip()
            m = re.match(r"^(\d+)\s*-\s*(.*)$", raw)
            no = int(m.group(1)) if m else 0
            venue = (m.group(2) if m else raw).strip()
            out.append({"station_id": r.get("station_id"), "no": no, "venue": venue,
                        "muni": (r.get("municipality") or MUNI).strip() or MUNI})
    return out


def align(docs, man):
    by_no = {d["no"]: d for d in docs}
    loc, report = [], []
    for m in man:
        d = by_no.get(m["no"])
        if not (d and sim(d.get("name", ""), m["venue"]) >= 0.4):
            best = max(docs, key=lambda x: sim(x["name"], m["venue"])) if docs else None
            if best is not None and sim(best["name"], m["venue"]) >= 0.6:
                d = best
        if d is None:
            d = by_no.get(m["no"])
        addr = (d.get("address") or "").strip() if d else ""
        docname = (d.get("name") or "").strip() if d else ""
        status = "ok"
        if d is None:
            status = "MISSING"
        elif sim(docname, m["venue"]) < 0.4:
            status = "name-mismatch"
        if not addr:
            status += "+no-address"
        if status != "ok":
            report.append(f"{m['no']:>3} [{status}] manifest='{m['venue']}' "
                          f"doc='{docname}' addr='{addr}'")
        loc.append({"municipality": m["muni"] or MUNI, "no": m["no"],
                    "name": m["venue"], "address": addr})
    return loc, report


def main():
    docs = parse_doc()
    man = read_manifest()
    print(f"[{SLUG}] doc rows={len(docs)} manifest rows={len(man)}")
    loc, report = align(docs, man)
    json.dump(loc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[{SLUG}] wrote {OUT} ({len(loc)})")
    if report:
        print(f"[{SLUG}] {len(report)} alignment notes:")
        for line in report:
            print("   " + line)
    else:
        print(f"[{SLUG}] no alignment mismatches")
    open(REPORT, "w", encoding="utf-8").write(
        f"vrsac alignment report\nmanifest={len(man)} doc={len(docs)} out={len(loc)}\n"
        + "\n".join(report) + "\n")


if __name__ == "__main__":
    main()
