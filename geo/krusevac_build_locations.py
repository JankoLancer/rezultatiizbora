#!/usr/bin/env python3
"""Build geo/krusevac_stations_locations.json for Grad Krusevac.

Aligns the RIK 2023 station manifest (rik_2023_krusevac/manifest.csv) with the
addresses parsed from the RIK 2022 referendum decision (krusevac_ref_rows.json).
RIK 2023 venue names take precedence; addresses come from the 2022 decision.

The 2022 decision lists 130 polling stations while the 2023 manifest lists 132,
so a sequence alignment (difflib) is used to cope with inserted stations and any
renumbering.  RIK 2023 station numbers are always kept; addresses are inherited
by position from the aligned 2022 row, or rematched by exact venue name.
"""
import csv
import difflib
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
MAN = os.path.join(BASE, "..", "rik_2023_krusevac", "manifest.csv")
REF = os.path.join(BASE, "krusevac_ref_rows.json")
OUT = os.path.join(BASE, "krusevac_stations_locations.json")
REPORT = os.path.join(BASE, "krusevac_align_report.json")
MUNI = "Град Крушевац"


def infer_settlement(venue, settlements):
    """Return a known settlement named inside a venue string, if any."""
    v = norm(venue)
    hits = [s for s in settlements if re.search(rf"\b{re.escape(s)}\b", v)]
    return max(hits, key=len) if hits else None


def norm(s):
    s = s.upper()
    for ch in '"„“”':
        s = s.replace(ch, " ")
    s = s.replace("–", "-")
    s = re.sub(r"[^А-ШЂЈЉЊЋЏЂA-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_manifest():
    rows = []
    for r in csv.DictReader(open(MAN, encoding="utf-8-sig")):
        rikname = re.sub(r"\s+", " ", r["station_name"].strip())
        no = int(rikname.split(" - ", 1)[0])
        venue = rikname.split(" - ", 1)[1].strip() if " - " in rikname else rikname
        rows.append({"no": no, "name": venue})
    rows.sort(key=lambda x: x["no"])
    return rows


def main():
    ref = json.load(open(REF, encoding="utf-8"))
    ref_sorted = sorted(ref, key=lambda r: r["no"])
    rik = parse_manifest()

    ref_names = [norm(r["name"]) for r in ref_sorted]
    rik_names = [norm(r["name"]) for r in rik]

    sm = difflib.SequenceMatcher(None, ref_names, rik_names, autojunk=False)
    # map rik list-index -> ref list-index  (renames = positional "replace" blocks)
    rik2ref, inserted = {}, []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "replace"):
            for k in range(min(i2 - i1, j2 - j1)):
                rik2ref[j1 + k] = i1 + k
        if tag == "insert":
            inserted.extend(range(j1, j2))
        # "delete" (ref rows absent from 2023) simply drops those rows

    # Fallback rematch by exact venue name (only unambiguous names)
    by_name = {}
    for idx, r in enumerate(ref_sorted):
        by_name.setdefault(norm(r["name"]), []).append(idx)
    GENERIC = {"ОСНОВНА ШКОЛА", "ДОМ КУЛТУРЕ", "ДРУШТВЕНИ ДОМ", "МЕСНА ЗАЈЕДНИЦА",
               "МЕСНА КАНЦЕЛАРИЈА", "ЗАДРУЖНИ ДОМ", "НАРОДНИ ДОМ", "ПРОСТОРИЈЕ ДОМА",
               "ДОМ ОМЛАДИНЕ", "ПОШТА", "СЕОСКИ ДОМ"}

    # settlements = 2022 rows whose address is a bare village name (no "КРУШЕВАЦ," prefix)
    settlements = []
    for r in ref_sorted:
        head = r["address"].split(",")[0].strip()
        if head and not head.upper().startswith("КРУШЕВАЦ") and len(head) >= 4:
            settlements.append(norm(head))
    settlements = sorted(set(settlements), key=len, reverse=True)

    out, mismatches, new_stations, align_rows = [], [], [], []
    for j, r in enumerate(rik):
        refidx = rik2ref.get(j)
        address = ""
        origin = None
        if refidx is not None:
            address = ref_sorted[refidx]["address"]
            origin = ref_sorted[refidx]["no"]
            if norm(ref_sorted[refidx]["name"]) != norm(r["name"]):
                mismatches.append((r["no"], r["name"], ref_sorted[refidx]["name"], origin))
        elif j in inserted:
            # genuinely new 2023 station: no 2022 address; try a distinctive name only
            if norm(r["name"]) not in GENERIC:
                cands = by_name.get(norm(r["name"]), [])
                if len(cands) == 1:
                    address = ref_sorted[cands[0]]["address"]
                    origin = ref_sorted[cands[0]]["no"]
            if not address:
                # infer a settlement if the venue name contains a known village name
                hit = infer_settlement(r["name"], settlements)
                if hit:
                    address = hit
                    origin = f"settlement:{hit}"
            new_stations.append(r["no"])
        else:
            cands = by_name.get(norm(r["name"]), [])
            if len(cands) == 1:
                address = ref_sorted[cands[0]]["address"]
                origin = ref_sorted[cands[0]]["no"]
            elif cands:
                refidx = min(cands, key=lambda idx: abs(idx - j))
                address = ref_sorted[refidx]["address"]
                origin = ref_sorted[refidx]["no"]
            else:
                new_stations.append(r["no"])
        out.append({"municipality": MUNI, "no": r["no"], "name": r["name"],
                    "address": address})
        align_rows.append({"municipality": MUNI, "no": r["no"], "name": r["name"],
                           "address": address, "ref_no": origin})

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"mismatches": mismatches, "new_stations": new_stations,
               "rik_count": len(rik), "ref_count": len(ref_sorted),
               "alignment": align_rows},
              open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"manifest stations : {len(rik)}")
    print(f"2022 doc rows     : {len(ref_sorted)}")
    print(f"locations written : {len(out)} -> {OUT}")
    print(f"name mismatches   : {len(mismatches)}")
    for no, a, b, orig in mismatches:
        print(f"  {no:>3}: RIK='{a}'  doc[{orig}]='{b}'")
    print(f"stations without a 2022 address ({len(new_stations)}): {new_stations}")
    empty = [r["no"] for r in out if not r["address"]]
    print(f"empty addresses   : {len(empty)} {empty}")


if __name__ == "__main__":
    main()
