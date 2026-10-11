#!/usr/bin/env python3
"""Build the RIK 2023 locations file for Град Зајечар.

Uses the shared generic doc parser (geo/opstina_docs.py) on the official
2022-referendum "glasačka mesta" document (geo/zajecar_ref.doc), then aligns
the 69 real polling stations to the 69-station RIK 2023 manifest.

Layout / parsing note
---------------------
The .doc is a 4-column table [no, name, address, area] whose long cells wrap.
antiword emits the wrapped fragments as extra table lines, and the generic
parser (no explicit number column recovered cleanly) falls back to *sequential*
mode, producing 72 rows instead of 69.  Exactly three of those rows are
fragments of their predecessor:
  * row 10 & row 14 : empty name, address == "Зајечар" -> address continuation
  * row 24          : name "Градске управе" -> wrapped remainder of station 21
                      ("ДОМ КУЛТУРЕ МЗ \"КОТЛУЈЕВАЦ\" – ШАЛТЕР САЛА ГРАДСКЕ УПРАВЕ")
Folding those fragments into the previous row yields the true 69 stations,
whose order is identical to the RIK 2023 numbering (1:1 by number).

Two station numbers kept the same slot but were re-designated in 2023:
  no  7: ПЈ Шумска управа Зајечар              -> ВРТИЋ "ЗДРАВАЦ"
  no 25: Стари млин "25. мај" (Велики Извор)   -> ПРОДАВНИЦА "ЗАЈЕЧАР ПРОМЕТ" -
                                                  ПРЕКО ПУТА СТАРОГ МЛИНА
For these the 2022 address of the same station number is retained (the polling
station slot is the same); they are flagged as name mismatches in the report.

Produces:
  geo/zajecar_stations_locations.json -> [{municipality,no,name,address}]
  geo/zajecar_align_report.txt        -> alignment notes
"""
import csv
import json
import os
import re
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
import opstina_docs  # noqa: E402

MUNI = "Град Зајечар"
REF = os.path.join(HERE, "zajecar_ref.doc")
MANIFEST = os.path.join(ROOT, "rik_2023_zajecar", "manifest.csv")
LOC_OUT = os.path.join(HERE, "zajecar_stations_locations.json")
REPORT = os.path.join(HERE, "zajecar_align_report.txt")


def norm_name(s):
    s = (s or "").upper().replace("\u201c", '"').replace("\u201d", '"').replace("\u201e", '"')
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    s = re.sub(r"\bОШ\b", "ОСНОВНА ШКОЛА", s)
    s = re.sub(r"\bМЗ\b", "МЕСНА ЗАЈЕДНИЦА", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    return SequenceMatcher(None, norm_name(a), norm_name(b)).ratio()


# ---------------------------------------------------------------- parse ref
rows = [r for r in opstina_docs.parse(REF) if r["no"] and (r["name"] or r["address"])]
folded = []
for r in rows:
    if folded and not r["name"] and r["address"]:
        folded[-1]["address"] = (folded[-1]["address"] + " " + r["address"]).strip()
        continue
    if folded and r["name"] and not r["address"]:
        folded[-1]["name"] = (folded[-1]["name"] + " " + r["name"]).strip()
        continue
    folded.append(dict(r))
assert len(folded) == 69, f"expected 69 folded ref rows, got {len(folded)}"

# ---------------------------------------------------------------- read manifest
man = []
with open(MANIFEST, encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        m = re.match(r"\s*(\d+)\s*-\s*(.*)$", row["station_name"])
        man.append({"station_id": row["station_id"], "no": int(m.group(1)),
                    "venue": m.group(2).strip()})
man.sort(key=lambda r: r["no"])
assert len(man) == 69, len(man)

# ------------------------------------------------ align 1:1 by station number
locations, mismatches = [], []
for r, ref in zip(man, folded):
    addr = (ref.get("address") or "").strip()
    s = sim(ref.get("name", ""), r["venue"])
    if s < 0.4:
        mismatches.append((r["no"], ref.get("name", ""), r["venue"], addr, round(s, 2)))
    locations.append({"municipality": MUNI, "no": r["no"],
                      "name": r["venue"], "address": addr})

assert [x["no"] for x in locations] == list(range(1, 70))
json.dump(locations, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

empty = [x["no"] for x in locations if not x["address"]]
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(f"doc rows parsed: {len(rows)}; folded to: {len(folded)}; "
             f"manifest stations: {len(man)}\n")
    fh.write("alignment: 1:1 by station number (doc order == RIK 2023 order)\n")
    fh.write(f"name mismatches ({len(mismatches)}):\n")
    for no, dn, mv, ad, sc in mismatches:
        fh.write(f"  no {no}: doc {dn!r} -> manifest {mv!r} (sim {sc}, addr {ad!r})\n")
    fh.write(f"empty addresses: {empty}\n")

print(f"ref rows {len(rows)} -> folded {len(folded)}; manifest {len(man)}; "
      f"locations {len(locations)}; mismatches {len(mismatches)}; empty addresses {empty}")
for no, dn, mv, ad, sc in mismatches:
    print(f"  mismatch no {no}: {dn!r} -> {mv!r} (sim {sc})")
print(f"-> {LOC_OUT}")
