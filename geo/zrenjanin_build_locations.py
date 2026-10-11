#!/usr/bin/env python3
"""Build the RIK 2023 polling-station locations for ГРАД ЗРЕЊАНИН.

Inputs (generic tooling only):
  geo/zrenjanin_ref.doc          -- 2022 referendum "glasacka mesta" (70 stations)
  rik_2023_zrenjanin/manifest.csv -- RIK 2023 authoritative station list (71 stations)

The shared opstina_docs parser reaches sequential mode on this doc (191 raw
table rows, 70 of them numbered), so the six venue names that wrap onto a
second physical row come back as extra address-less rows.  We merge those
continuation rows back into the previous row's name, giving the 70 real
polling stations of the reference document.

Output rows are aligned to the RIK 2023 manifest by polling-station number
(with wrapped continuation merged), plus a venue-name fallback for the one
station that has no numbered counterpart, and written as
geo/zrenjanin_stations_locations.json -> [{municipality,no,name,address}].

Also writes geo/zrenjanin_ref_rows.json and geo/zrenjanin_align_report.txt.
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

REF = os.path.join(HERE, "zrenjanin_ref.doc")
MANIFEST = os.path.join(ROOT, "rik_2023_zrenjanin", "manifest.csv")
LOC_OUT = os.path.join(HERE, "zrenjanin_stations_locations.json")
REF_OUT = os.path.join(HERE, "zrenjanin_ref_rows.json")
REPORT = os.path.join(HERE, "zrenjanin_align_report.txt")

MUNI = "Град Зрењанин"
EXPECTED_REF = 70
EXPECTED_LOC = 71


def load_ref():
    """Parse the base doc and merge wrapped-name continuation rows."""
    rows = opstina_docs.parse(REF)
    merged = []
    for r in rows:
        if not (r["name"] or r["address"]):
            continue
        if merged and not r["address"].strip() and r["name"].strip():
            # wrapped continuation of the previous venue name
            merged[-1]["name"] = (merged[-1]["name"] + " " + r["name"]).strip()
            if r["area"]:
                merged[-1]["area"] = (merged[-1]["area"] + " " + r["area"]).strip()
            continue
        merged.append(dict(r))
    # renumber sequentially 1..N (raw doc numbering is 1..70 contiguous)
    for i, r in enumerate(merged, 1):
        r["no"] = i
    return merged


def load_manifest():
    out = []
    with open(MANIFEST, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            sn = row["station_name"].strip()
            m = re.match(r"^\s*(\d+)\s*-\s*(.*)$", sn)
            no = int(m.group(1)) if m else 0
            venue = (m.group(2) if m else sn).strip()
            out.append({"station_id": row["station_id"], "no": no, "venue": venue,
                        "muni": row.get("municipality") or MUNI})
    out.sort(key=lambda r: r["no"])
    return out


def norm_name(s):
    s = (s or "").upper().replace("“", '"').replace("”", '"').replace("„", '"')
    s = s.replace("–", "-").replace("’", "'").replace("''", '"')
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ref = load_ref()
    assert len(ref) == EXPECTED_REF, f"ref rows {len(ref)} != {EXPECTED_REF}"
    json.dump(ref, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ref rows (after merge): {len(ref)} -> {REF_OUT}")

    man = load_manifest()
    print(f"manifest stations: {len(man)}")
    ref_by_no = {r["no"]: r for r in ref}
    by_name = {}
    for r in ref:
        by_name.setdefault(norm_name(r["name"]), []).append(r)

    # Detect a possible global numbering shift (rik no - ref no).
    offsets = range(-4, 5)
    scores = {d: sum(1 for m in man if m["no"] + d in ref_by_no
                     and norm_name(ref_by_no[m["no"] + d]["name"]) == norm_name(m["venue"]))
              for d in offsets}
    best_offset = max(scores, key=scores.get)
    print(f"offset scores: {dict(sorted(scores.items()))} -> best {best_offset}")

    report = [f"offset scores (rik no - ref no): {dict(sorted(scores.items()))}",
              f"best offset: {best_offset}"]
    locations = []
    n_by_no = n_by_name = n_flag = 0
    for m in man:
        no, venue = m["no"], m["venue"]
        match, how = None, None
        if best_offset == 0:
            match, how = ref_by_no.get(no), "number"
            if match is not None and norm_name(match["name"]) != norm_name(venue):
                # number agrees but the venue name differs: prefer an exact
                # venue-name match when it is unique (renames / renumbering).
                cand = by_name.get(norm_name(venue), [])
                if len(cand) == 1:
                    match, how = cand[0], "venue-name"
                else:
                    how = "number(renamed)"
        if match is None:
            cand = by_name.get(norm_name(venue), [])
            if len(cand) == 1:
                match, how = cand[0], "venue-name"
            elif no in ref_by_no:
                match, how = ref_by_no[no], "number(flag)"
        if match is None:
            report.append(f"MISS no={no} venue={venue!r}: no matching ref venue")
            n_flag += 1
            addr = ""
        else:
            addr = (match.get("address") or "").strip()
            if how in ("number", "number(renamed)", "number(flag)"):
                n_by_no += 1
                if norm_name(match["name"]) != norm_name(venue):
                    report.append(f"RENAMED no={no}: ref {match['name']!r} -> rik {venue!r} "
                                  f"(address inherited: {addr!r})")
            else:
                n_by_name += 1
                report.append(f"REMATCH no={no} venue={venue!r} -> ref#{match['no']} "
                              f"{match['name']!r} ({addr!r})")
        locations.append({"municipality": m["muni"], "no": no, "name": venue, "address": addr})

    assert len(locations) == EXPECTED_LOC, f"locations {len(locations)} != {EXPECTED_LOC}"
    json.dump(locations, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    empty = [l for l in locations if not l["address"]]
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(f"manifest stations: {len(man)}; ref rows: {len(ref)}\n")
        fh.write(f"matched by number: {n_by_no}; by venue-name: {n_by_name}; "
                 f"unmatched: {n_flag}; empty addresses: {len(empty)}\n")
        fh.write("number mismatches / notes:\n")
        if report:
            for line in report:
                fh.write("  " + line + "\n")
        else:
            fh.write("  (none)\n")
        if empty:
            fh.write("stations with empty address:\n")
            for l in empty:
                fh.write(f"  no={l['no']} {l['name']!r}\n")
    print(f"locations: {len(locations)}; by-number {n_by_no}; by-name {n_by_name}; "
          f"flagged {n_flag}; empty addresses {len(empty)}")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
