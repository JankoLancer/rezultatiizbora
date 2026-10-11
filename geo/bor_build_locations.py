#!/usr/bin/env python3
"""Build geo/bor_stations_locations.json for ГРАД БОР (RIK 2023 target).

Sources:
  * rik_2023_bor/manifest.csv      -> RIK 2023 station numbers + venue names (target)
  * geo/bor_ref.docx               -> referendum 2022 glasacka mesta (no,name,address,area)
  * geo/bor_izmena.doc             -> prose resenje o izmeni (applied manually below)

Alignment is by station number (the ref doc numbers match the manifest 1:1).
The izmena is a prose act (no table), so its overrides are applied explicitly.
"""
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import opstina_docs  # noqa: E402
from difflib import SequenceMatcher  # noqa: E402

MUNI = "Град Бор"

# --- Resenje o izmeni (broj 014-3/2021-I-01 od 21.12.2021), applied by station no.
# #2: name МЗ "СЕВЕР" -> ЦЕНТАР ЗА СОЦИЈАЛНИ РАД ; address ВОЈСКЕ ЈУГОСЛАВИЈЕ БР.19 -> бр.11
# #4 and #5: address КЕСТЕНОВА БР.3 -> БОЖИНА ЈОВАНОВИЋА БР.3 (бивша Кестенова)
IZMENA = {
    2: {"address": "БОР, ВОЈСКЕ ЈУГОСЛАВИЈЕ 11"},
    4: {"address": "БОР, БОЖИНА ЈОВАНОВИЋА БР.3 (БИВША КЕСТЕНОВА)"},
    5: {"address": "БОР, БОЖИНА ЈОВАНОВИЋА БР.3 (БИВША КЕСТЕНОВА)"},
}


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^0-9a-zа-шђћљњџј]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def read_manifest():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "rik_2023_bor", "manifest.csv"),
                                    encoding="utf-8-sig")))
    out = []
    for r in rows:
        rk = r["station_name"].strip()
        m = re.match(r"^(\d+)\s*-\s*(.*)$", rk)
        no = int(m.group(1)) if m else 0
        venue = (m.group(2) if m else rk).strip()
        out.append({"no": no, "venue": venue, "muni": r.get("municipality") or MUNI})
    return out


def main():
    docs = [d for d in opstina_docs.parse(os.path.join(HERE, "bor_ref.docx"))
            if d["no"] and (d["name"] or d["address"])]
    by_no = {d["no"]: d for d in docs}
    man = read_manifest()

    loc, mismatches = [], []
    for m in man:
        d = by_no.get(m["no"])
        if d is None:
            d = max(docs, key=lambda x: sim(x["name"], m["venue"]))
        addr = (d.get("address") or "").strip()
        if m["no"] in IZMENA:
            addr = IZMENA[m["no"]]["address"]
        score = sim(d.get("name", ""), m["venue"])
        if score < 0.4:
            mismatches.append((m["no"], m["venue"], d.get("name"), round(score, 3)))
        loc.append({"municipality": m["muni"], "no": m["no"], "name": m["venue"],
                    "address": addr, "_venue": m["venue"], "_docname": d.get("name", "")})

    out = os.path.join(HERE, "bor_stations_locations.json")
    json.dump(loc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {out} ({len(loc)} rows)")
    print(f"name mismatches vs RIK (<0.4): {len(mismatches)}")
    for mm in mismatches:
        print("   no=%s RIK=%r doc=%r sim=%s" % mm)
    return loc


if __name__ == "__main__":
    main()
