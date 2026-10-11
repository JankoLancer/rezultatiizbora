#!/usr/bin/env python3
"""Build geo/beograd_g2_locations.json for Belgrade group g2.

Parses the official 2022-referendum polling-station documents for
Cukarica / Palilula / Savski venac / Sopot and aligns them with the RIK 2023
parliamentary manifest (station_name = "N - VENUE").

Matching strategy (RIK 2023 is the target):
  pass 1  same number AND same venue name            -> "number"
  pass 2  same venue name (repeated venues consumed  -> "venue"/"venue-duplicate"
          in document order) at another number
  pass 3  venue absent from the 2022 document        -> "number-mismatch" (kept by
          number, flagged; coordinate resolved by venue search later)

Amendment decisions were inspected but the 2023 target reverts to the original
2022 names for Savski venac #25 and Palilula #98/#99, so the main documents are
the correct reference (see beograd_g2_amendment_notes.json).
"""
import csv, json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
OUT_DIR = os.path.join(ROOT, "rik_2023_beograd_g2")
OUT = os.path.join(BASE, "beograd_g2_locations.json")

DOCS = {
    "Градска општина Чукарица":  "beograd_g2_cukarica.txt",
    "Градска општина Палилула (Београд)": "beograd_g2_palilula.txt",
    "Градска општина Савски Венац": "beograd_g2_savskivenac.txt",
    "Градска општина Сопот": "beograd_g2_sopot.txt",
}

# amendment docs, for the audit note only
AMENDMENTS = {
    "Градска општина Чукарица": "beograd_g2_cukarica_amd.txt",
    "Градска општина Палилула (Београд)": "beograd_g2_palilula_amd.txt",
    "Градска општина Савски Венац": "beograd_g2_savskivenac_amd.txt",
    "Градска општина Сопот": "beograd_g2_sopot_amd.txt",
}


def parse_rows(f):
    with open(f, encoding="utf-8", errors="replace") as fh:
        cells = [c.strip() for c in fh.read().replace("\r", "").split("\x07")]
    hi = next(i for i, c in enumerate(cells) if "НАЗИВ" in c and "ГЛАСАЧ" in c)
    rows = {}
    i = hi + 4
    while i < len(cells):
        m = re.match(r"^(\d+)\.?$", cells[i])
        if m:
            no = int(m.group(1))
            name = re.sub(r"\s+", " ", cells[i + 1]).strip() if i + 1 < len(cells) else ""
            addr = re.sub(r"\s+", " ", cells[i + 2]).strip() if i + 2 < len(cells) else ""
            rows.setdefault(no, {"no": no, "name": name, "address": addr})
            i += 5
        else:
            i += 1
    return rows


def norm(s):
    s = s.upper().replace("„", '"').replace("“", '"').replace("”", '"')
    s = re.sub(r"[^А-ШЂЈЉЊЋЏA-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    docs = {m: parse_rows(os.path.join(BASE, f)) for m, f in DOCS.items()}
    for m, rows in docs.items():
        print(f"{m}: parsed {len(rows)} 2022 doc rows (max no {max(rows)})")

    with open(os.path.join(OUT_DIR, "manifest.csv"), encoding="utf-8-sig") as fh:
        manifest = list(csv.DictReader(fh))

    order = {m: i for i, m in enumerate(DOCS)}
    # 2023 stations grouped by municipality, in manifest order
    stations = []
    for row in manifest:
        muni = row["municipality"]
        sn = row["station_name"].strip()
        g = re.match(r"^(\d+)\s*-\s*(.+)$", sn)
        no, venue = (int(g.group(1)), g.group(2).strip()) if g else (None, sn)
        stations.append({"municipality": muni, "no": no, "name": venue,
                         "_sid": row["station_id"]})

    match = {}
    used = {m: set() for m in DOCS}

    # pass 1: number + name
    for s in stations:
        d = docs.get(s["municipality"], {})
        r = d.get(s["no"]) if s["no"] is not None else None
        if r and norm(r["name"]) == norm(s["name"]):
            match[(s["municipality"], s["no"])] = ("number", r)
            used[s["municipality"]].add(s["no"])

    # pass 2: same venue name, document order
    for s in stations:
        key = (s["municipality"], s["no"])
        if key in match:
            continue
        d = docs.get(s["municipality"], {})
        cands = sorted([r for r in d.values() if norm(r["name"]) == norm(s["name"])],
                       key=lambda r: r["no"])
        if not cands:
            continue
        free = [r for r in cands if r["no"] not in used[s["municipality"]]]
        r = free[0] if free else cands[0]
        match[key] = ("venue" if free else "venue-duplicate", r)
        used[s["municipality"]].add(r["no"])

    # pass 3: absent -> keep by number
    for s in stations:
        key = (s["municipality"], s["no"])
        if key in match:
            continue
        d = docs.get(s["municipality"], {})
        r = d.get(s["no"]) if s["no"] is not None else None
        match[key] = ("number-mismatch" if r else "no-doc", r)

    out, report = [], []
    for s in stations:
        typ, r = match[(s["municipality"], s["no"])]
        addr = r["address"] if r else None
        out.append({"municipality": s["municipality"], "no": s["no"],
                    "name": s["name"], "address": addr})
        if typ != "number":
            report.append({"municipality": s["municipality"], "no": s["no"],
                           "name": s["name"], "match": typ,
                           "doc_no": r["no"] if r else None,
                           "doc_name": r["name"] if r else None,
                           "address": addr})

    out.sort(key=lambda r: (order.get(r["municipality"], 99),
                            r["no"] if r["no"] is not None else 0))
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(report, open(os.path.join(BASE, "beograd_g2_match_report.json"),
                           "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({
        "note": "2022 referendum amendment decisions inspected; RIK 2023 reverts to "
                "original names for Savski venac #25 (ПЕТА ЗДРАВСТВЕНА СТАНИЦА...) and "
                "Palilula #98/#99 (ИСТУРЕНО ОДЕЉЕЊЕ ОШ ОЛГА ПЕТРОВ), so the main 2022 "
                "decisions are the correct address reference for the 2023 target. "
                "Cukarica and Sopot amendments changed only the polling-area column.",
        "amendments": AMENDMENTS,
    }, open(os.path.join(BASE, "beograd_g2_amendment_notes.json"), "w",
            encoding="utf-8"), ensure_ascii=False, indent=1)

    print("\n== matching ==")
    from collections import Counter
    for m in DOCS:
        t = Counter(v[0] for (mm, no), v in match.items() if mm == m)
        n = sum(t.values())
        print(f"  {m}: {n} stations | " + " | ".join(f"{k} {v}" for k, v in sorted(t.items())))
    print(f"\nTotal {len(out)} stations, non-number matches {len(report)}")
    for p in report:
        if p["match"] in ("number-mismatch", "no-doc"):
            print("   !", p)
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
