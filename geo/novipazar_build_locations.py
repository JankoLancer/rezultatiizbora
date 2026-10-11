#!/usr/bin/env python3
"""Build the RIK 2023 locations file for Град Нови Пазар.

Uses the shared generic doc parser (geo/opstina_docs.py) on the official
2022-referendum "glasačka mesta" document, applies the 31.12.2021 izmena,
then aligns the resulting 98 doc rows to the 99-station RIK 2023 manifest.

Alignment method
----------------
Distinctive (globally unique) venue names in the reference document act as
anchors; each anchor yields a delta = manifest_no - ref_no.  Here the early
stations anchor at delta 0 and the later ones at delta +1, i.e. the 2023
manifest contains ONE extra polling station placed somewhere between the last
delta-0 anchor and the first delta+1 anchor.  The exact insertion position is
resolved by trying every slot in that middle block and keeping the one that
maximises normalized venue-name similarity; the inserted row inherits the
address of its most similar reference neighbour.

Produces:
  geo/novipazar_ref_rows.json           -> [{no,name,address,area}] (amended)
  geo/novipazar_stations_locations.json -> [{municipality,no,name,address}]
  geo/novipazar_align_report.txt        -> alignment notes
"""
import csv, json, os, re
from collections import defaultdict
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
import opstina_docs  # noqa: E402

MUNI = "Град Нови Пазар"
REF = os.path.join(HERE, "novipazar_ref.docx")
MANIFEST = os.path.join(ROOT, "rik_2023_novipazar", "manifest.csv")
REF_OUT = os.path.join(HERE, "novipazar_ref_rows.json")
LOC_OUT = os.path.join(HERE, "novipazar_stations_locations.json")
REPORT = os.path.join(HERE, "novipazar_align_report.txt")

# 31.12.2021 izmena rešenja: no 54 is renamed (village unchanged: Хотково).
IZMENA = {54: {"name": "КУЋА ХАЈРОВИЋ САБАХУДИНА"}}


def norm_name(s):
    s = (s or "").upper().replace("\u201c", '"').replace("\u201d", '"').replace("\u201e", '"')
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    s = re.sub(r"\bОШ\b", "ОСНОВНА ШКОЛА", s)
    s = re.sub(r"\bМЗ\b", "МЕСНА ЗАЈЕДНИЦА", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    return SequenceMatcher(None, norm_name(a), norm_name(b)).ratio()


# ---------------------------------------------------------------- parse ref
ref = opstina_docs.parse(REF)
ref = [r for r in ref if r["no"] and (r["name"] or r["address"])]
ref.sort(key=lambda r: r["no"])
for r in ref:
    if r["no"] in IZMENA:
        r.update(IZMENA[r["no"]])
assert not [n for n in range(1, len(ref) + 1) if n not in {r["no"] for r in ref}], "ref gaps"
json.dump(ref, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
ref_by_no = {r["no"]: r for r in ref}

# ---------------------------------------------------------------- read manifest
man = []
with open(MANIFEST, encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        m = re.match(r"\s*(\d+)\s*-\s*(.*)$", row["station_name"])
        man.append({"station_id": row["station_id"], "no": int(m.group(1)),
                    "venue": m.group(2).strip()})
man.sort(key=lambda r: r["no"])

# ------------------------------------------- anchor-based piecewise offset
by_norm = defaultdict(list)
for r in ref:
    by_norm[norm_name(r["name"])].append(r["no"])
anchors = {}
for s in man:
    cand = by_norm.get(norm_name(s["venue"]))
    if cand and len(cand) == 1:
        anchors[s["no"]] = s["no"] - cand[0]

deltas = sorted(set(anchors.values()))
assert deltas == [0, 1], f"unexpected anchor deltas {deltas}"
H = max(no for no, d in anchors.items() if d == 0)          # last delta-0 anchor
T = min(no for no, d in anchors.items() if d == 1)          # first delta-1 anchor
mid_man = [s for s in man if H < s["no"] < T]
mid_ref = [r for r in ref if H < r["no"] <= T - 2]          # one fewer: the insertion
assert len(mid_man) - len(mid_ref) == 1, (len(mid_man), len(mid_ref))

# choose insertion slot p (which middle manifest row has no ref counterpart)
best_p, best_score = None, None
for p in range(len(mid_man)):
    peers = mid_man[:p] + mid_man[p + 1:]
    score = sum(sim(s["venue"], r["name"]) for s, r in zip(peers, mid_ref))
    if best_score is None or score > best_score:
        best_p, best_score = p, score
inserted_no = mid_man[best_p]["no"]
# inheritance: most similar reference neighbour of the inserted row
inserted_venue = mid_man[best_p]["venue"]
neighbours = [r for r in (mid_ref[best_p - 1] if best_p > 0 else None,
                          mid_ref[best_p] if best_p < len(mid_ref) else None) if r]
inherit = max(neighbours, key=lambda r: sim(inserted_venue, r["name"])) if neighbours else None

report = [
    f"ref rows: {len(ref)}; manifest stations: {len(man)}",
    f"unique-name anchors ({len(anchors)}): {dict(sorted(anchors.items()))}",
    f"delta 0 through manifest {H}; delta +1 from manifest {T}",
    f"2023 insertion at manifest no {inserted_no} "
    f"(no reference row; inherits address of doc no {inherit['no']}: "
    f"{inherit['name']!r} -> {inherit['address']!r})" if inherit else
    f"2023 insertion at manifest no {inserted_no} (no address to inherit)",
]


def ref_for(no):
    """Return the reference row matching manifest number `no` (or None)."""
    if no == inserted_no:
        return None
    if no <= H:
        return ref_by_no.get(no)
    if no >= T:
        return ref_by_no.get(no - 1)
    peers = mid_man[:best_p] + mid_man[best_p + 1:]
    idx = [s["no"] for s in peers].index(no)
    return ref_by_no.get(mid_ref[idx]["no"])


locations, unmatched, renamed = [], [], []
for s in man:
    no, venue = s["no"], s["venue"]
    if no == inserted_no:
        d = inherit
    else:
        d = ref_for(no)
    if d is None:
        unmatched.append((no, venue))
        locations.append({"municipality": MUNI, "no": no, "name": venue, "address": ""})
        continue
    if norm_name(d["name"]) != norm_name(venue):
        renamed.append((no, d["name"], venue, d["address"]))
    locations.append({"municipality": MUNI, "no": no, "name": venue,
                      "address": (d["address"] or "").strip()})

assert len(locations) == len(man) == 99, len(locations)
json.dump(locations, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

empty = [x["no"] for x in locations if not x["address"]]
with open(REPORT, "w", encoding="utf-8") as fh:
    for line in report:
        fh.write(line + "\n")
    fh.write(f"izmena applied: {IZMENA}\n")
    fh.write(f"renamed venue names ({len(renamed)}):\n")
    for no, on, nv, ad in renamed:
        fh.write(f"  no {no}: {on!r} -> {nv!r} (addr {ad!r})\n")
    fh.write(f"unmatched: {unmatched}\n")
    fh.write(f"empty addresses: {empty}\n")

print(f"ref rows: {len(ref)}; manifest: {len(man)}; locations: {len(locations)}")
print(f"insertion at manifest no {inserted_no}; renamed: {len(renamed)}; "
      f"unmatched: {len(unmatched)}; empty addresses: {empty}")
print(f"-> {LOC_OUT}")
