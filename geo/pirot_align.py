#!/usr/bin/env python3
"""Align RIK 2023 Pirot manifest venues to the 2022 referendum address doc.

Uses the shared generic parser geo/opstina_docs.py (no custom parsing).
Writes geo/pirot_stations_locations.json.
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

DOC = os.path.join(HERE, "pirot_ref.doc")
MANIFEST = os.path.join(ROOT, "rik_2023_pirot", "manifest.csv")
OUT = os.path.join(HERE, "pirot_stations_locations.json")
MUNI = "Град Пирот"


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^0-9a-zа-шђћљњџј]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def main():
    docs = opstina_docs.parse(DOC)
    by_no = {d["no"]: d for d in docs}
    man = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))

    loc, mism = [], 0
    for m in man:
        rk = m["station_name"].strip()
        mm = re.match(r"^(\d+)\s*-\s*(.*)$", rk)
        no = int(mm.group(1)) if mm else 0
        venue = (mm.group(2) if mm else rk).strip()
        d = by_no.get(no)
        if d is None:
            loc.append({"municipality": m.get("municipality") or MUNI, "no": no,
                        "name": venue, "address": "", "_venue": venue,
                        "_docname": ""})
            mism += 1
            continue
        if sim(d.get("name", ""), venue) < 0.4:
            mism += 1
        loc.append({"municipality": m.get("municipality") or MUNI, "no": no,
                    "name": venue, "address": (d.get("address") or "").strip(),
                    "_venue": venue, "_docname": d.get("name", "")})

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(loc, fh, ensure_ascii=False, indent=1)
    print(f"wrote {OUT} ({len(loc)} rows, name mismatches {mism})")
    return loc


if __name__ == "__main__":
    main()
