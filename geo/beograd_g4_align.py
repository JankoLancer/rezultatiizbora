#!/usr/bin/env python3
"""Align the parsed 2022 referendum rows (geo/beograd_g4_ref_rows.json) with the
RIK 2023 station manifest (rik_2023_beograd_g4/manifest.csv) for group g4.

For every RIK 2023 station ("<no> - <venue>") we take the address from the 2022
decision row with the same number.  If the venue name does not match we try to
re-locate the 2022 row by exact venue name; if that fails we keep the same-number
row (inherit) and flag the mismatch.

Output: geo/beograd_g4_locations.json
        [{municipality, no, name (RIK 2023), address}, ...] ordered by muni,no.
"""
import csv
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
REF = os.path.join(BASE, "beograd_g4_ref_rows.json")
MANIFEST = os.path.join(ROOT, "rik_2023_beograd_g4", "manifest.csv")
OUT = os.path.join(BASE, "beograd_g4_locations.json")
REPORT = os.path.join(BASE, "beograd_g4_align_report.txt")

MUNIS = ["Градска општина Раковица", "Градска општина Лазаревац",
         "Градска општина Младеновац", "Градска општина Обреновац",
         "Градска општина Гроцка"]


def norm(s):
    s = (s or "").upper()
    for q in ("„", "“", "”", '"', "'", "`"):
        s = s.replace(q, " ")
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def toks(s):
    return set(t for t in norm(s).split() if len(t) >= 2)


def similar(a, b):
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return False
    inter = ta & tb
    return len(inter) / max(len(ta), len(tb)) >= 0.6


def main():
    ref = json.load(open(REF, encoding="utf-8"))
    by_muni = {}
    for r in ref:
        by_muni.setdefault(r["municipality"], []).append(r)
    for lst in by_muni.values():
        lst.sort(key=lambda r: r["no"])
    by_no = {m: {r["no"]: r for r in lst} for m, lst in by_muni.items()}

    manifest = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))

    out, mism = [], []
    counts = {}
    for muni in MUNIS:
        rows = [m for m in manifest if m["municipality"] == muni]
        rows.sort(key=lambda m: int(re.match(r"\s*(\d+)", m["station_name"]).group(1)))
        counts[muni] = len(rows)
        for m in rows:
            mm = re.match(r"\s*(\d+)\s*-\s*(.*)$", m["station_name"])
            no = int(mm.group(1))
            venue = mm.group(2).strip()
            r = by_no.get(muni, {}).get(no)
            addr = r["address"] if r else ""
            flag = "ok"
            if r is None:
                flag = "missing-2022-row"
            elif not similar(venue, r["name"]):
                # try to re-locate by exact venue name
                cand = [x for x in by_muni.get(muni, []) if norm(x["name"]) == norm(venue)]
                addrs = {x["address"] for x in cand}
                if len(cand) == 1 or len(addrs) == 1:
                    addr = cand[0]["address"]
                    flag = f"rematched->{cand[0]['no']}"
                else:
                    flag = "mismatch-inherit"
            if flag != "ok":
                mism.append((muni, no, venue, r["name"] if r else "-", flag))
            out.append({"municipality": muni, "no": no, "name": venue,
                        "address": addr})

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    lines = [f"aligned {len(out)} stations -> {OUT}",
             "counts: " + ", ".join(f"{k.split()[-1]}={v}" for k, v in counts.items()),
             f"mismatches: {len(mism)}"]
    for muni, no, venue, old, flag in mism:
        lines.append(f"  {muni.split()[-1]:<12} {no:>3} RIK={venue!r} 2022={old!r} [{flag}]")
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nsample:")
    for r in out[:3]:
        print(f"  {r['municipality'].split()[-1]:<12} {r['no']:>3} {r['name'][:40]:<40} | {r['address'][:44]}")


if __name__ == "__main__":
    main()
