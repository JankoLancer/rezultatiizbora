#!/usr/bin/env python3
"""Build the RIK 2023 polling-station locations for ГРАД ЛОЗНИЦА.

Inputs (generic tooling only):
  geo/loznica_ref.doc      -- 2022 referendum "glasacka mesta" (base, 90 rows)
  geo/loznica_izmena1.doc  -- 31.12.2021 izmena (station 36)
  geo/loznica_izmena2.doc  -- 12.01.2022 izmena (station 36, final; overrides 1)
  rik_2023_loznica/manifest.csv -- RIK 2023 authoritative station list

The generic opstina_docs parser returns 92 rows for the base doc because two
venue names wrap onto a second physical table row (rows 19/20 and 38/39 of the
raw numbering).  Those continuation rows carry no address; we merge them back
into the previous row's name and renumber to the 90 real polling stations.

Amendments override by polling-station number (36); izmena2 is applied last so
it wins.  Output rows are aligned to the RIK 2023 manifest and written as
geo/loznica_stations_locations.json -> [{municipality,no,name,address}].

Also writes geo/loznica_align_report.txt.
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

REF = os.path.join(HERE, "loznica_ref.doc")
IZ1 = os.path.join(HERE, "loznica_izmena1.doc")
IZ2 = os.path.join(HERE, "loznica_izmena2.doc")
MANIFEST = os.path.join(ROOT, "rik_2023_loznica", "manifest.csv")
LOC_OUT = os.path.join(HERE, "loznica_stations_locations.json")
REF_OUT = os.path.join(HERE, "loznica_ref_rows.json")
REPORT = os.path.join(HERE, "loznica_align_report.txt")

MUNI = "Град Лозница"
EXPECTED = 90


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
    # renumber sequentially 1..N (raw doc numbering is 1..90 contiguous)
    for i, r in enumerate(merged, 1):
        r["no"] = i
    return merged


def amendment_rows():
    """Return [(no, {name,address})] applying izmena1 then izmena2 (2 wins)."""
    notes = []
    by_no = {}
    for path, label in ((IZ1, "izmena1"), (IZ2, "izmena2")):
        rows = opstina_docs.parse(path)
        rows = [r for r in rows if r["name"] or r["address"]]
        if not rows:
            continue
        # The amendment decisions name the target explicitly:
        # "гласачко место под редним бројем 36 мења се".
        target = 36
        # Join a wrapped name (e.g. '... -' + 'УЧИОНИЦА БР.3').
        name = rows[0]["name"].strip()
        addr = rows[0]["address"].strip()
        for extra in rows[1:]:
            if extra["name"] and not extra["address"]:
                name = (name + " " + extra["name"]).strip()
            else:
                break
        by_no[target] = {"name": name, "address": addr}
        notes.append((label, target, name, addr))
    return by_no, notes


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
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    s = re.sub(r"\bОШ\b", "ОСНОВНА ШКОЛА", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ref = load_ref()
    assert len(ref) == EXPECTED, f"ref rows {len(ref)} != {EXPECTED}"
    amd, amd_notes = amendment_rows()
    for no, patch in amd.items():
        for r in ref:
            if r["no"] == no:
                r["name"] = patch["name"]
                r["address"] = patch["address"]
    json.dump(ref, open(REF_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ref rows (after merge+amendments): {len(ref)} -> {REF_OUT}")

    man = load_manifest()
    print(f"manifest stations: {len(man)}")
    ref_by_no = {r["no"]: r for r in ref}
    by_name = {}
    for r in ref:
        by_name.setdefault(norm_name(r["name"]), []).append(r)

    # Detect a possible global numbering shift (rik no - ref no), like the
    # Šabac aligner, to decide whether to match by number or by venue name.
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
            if how in ("number", "number(flag)"):
                n_by_no += 1
                if norm_name(match["name"]) != norm_name(venue):
                    report.append(f"RENAMED no={no}: ref {match['name']!r} -> rik {venue!r} "
                                  f"(address inherited: {addr!r})")
            else:
                n_by_name += 1
                report.append(f"REMATCH no={no} venue={venue!r} -> ref#{match['no']} "
                              f"{match['name']!r} ({addr!r})")
        locations.append({"municipality": m["muni"], "no": no, "name": venue, "address": addr})

    assert len(locations) == EXPECTED, f"locations {len(locations)} != {EXPECTED}"
    json.dump(locations, open(LOC_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    empty = [l for l in locations if not l["address"]]
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(f"manifest stations: {len(man)}; ref rows: {len(ref)}\n")
        fh.write(f"matched by number: {n_by_no}; by venue-name: {n_by_name}; "
                 f"unmatched: {n_flag}; empty addresses: {len(empty)}\n")
        fh.write("amendments applied (in order):\n")
        for label, target, name, addr in amd_notes:
            fh.write(f"  {label} no {target}: {name!r} | {addr!r}\n")
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
