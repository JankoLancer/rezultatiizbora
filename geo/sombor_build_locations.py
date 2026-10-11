#!/usr/bin/env python3
"""Align the Sombor glasacka-mesta doc rows to the RIK 2023 manifest.

Writes geo/sombor_stations_locations.json with 76 rows
{"municipality":"Град Сомбор","no":N,"name":"<RIK venue>","address":"..."}.

Alignment mirrors geo/pipeline_opstina.py:align (by number, name-similarity
fallback). Read-only w.r.t. shared files; only new sombor_ artifacts.
"""
import csv
import json
import os
import re
import sys
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "geo"))
import opstina_docs  # noqa: E402

MUNI = "Град Сомбор"
MANIFEST = os.path.join(HERE, "rik_2023_sombor", "manifest.csv")
REF = os.path.join(HERE, "geo", "sombor_ref.docx")
OUT = os.path.join(HERE, "geo", "sombor_stations_locations.json")


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^0-9a-zа-шђћљњџј]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sim(a, b):
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def read_manifest():
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    out = []
    for r in rows:
        rk = r["station_name"].strip()
        m = re.match(r"^(\d+)\s*-\s*(.*)$", rk)
        no = int(m.group(1)) if m else 0
        venue = (m.group(2) if m else rk).strip()
        out.append({"station_id": r["station_id"], "no": no, "venue": venue})
    return out


def main():
    docs = opstina_docs.parse(REF)
    docs = [d for d in docs if d["no"] and (d["name"] or d["address"])]
    man = read_manifest()

    by_no = {d["no"]: d for d in docs}
    loc, mism, noaddr = [], [], 0
    for m in man:
        d = by_no.get(m["no"])
        if not (d and sim(d.get("name", ""), m["venue"]) >= 0.4):
            best = max(docs, key=lambda x: sim(x["name"], m["venue"])) if docs else None
            if best is not None and sim(best["name"], m["venue"]) >= 0.6:
                d = best
        if d is None:
            d = by_no.get(m["no"])
        addr = (d.get("address") or "").strip() if d else ""
        if not addr:
            noaddr += 1
        if d is None or sim(d.get("name", ""), m["venue"]) < 0.4:
            mism.append((m["no"], m["venue"], d.get("name") if d else None,
                         round(sim(d.get("name", ""), m["venue"]) if d else 0.0, 2)))
        loc.append({"municipality": MUNI, "no": m["no"], "name": m["venue"],
                    "address": addr})

    json.dump(loc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {OUT} ({len(loc)} rows)")
    print(f"manifest={len(man)} doc_rows={len(docs)} "
          f"name_mismatches={len(mism)} empty_addresses={noaddr}")
    for no, venue, docname, s in mism:
        print(f"  MISMATCH no={no}: RIK={venue!r} DOC={docname!r} sim={s}")

    # sanity: every manifest station number present, doc numbers 1..N unique
    man_nos = [m["no"] for m in man]
    doc_nos = [d["no"] for d in docs]
    print(f"manifest nos 1..{max(man_nos)} unique={len(set(man_nos))}")
    print(f"doc nos 1..{max(doc_nos)} unique={len(set(doc_nos))}")
    missing = sorted(set(man_nos) - set(doc_nos))
    if missing:
        print(f"  DOC MISSING for nos: {missing}")


if __name__ == "__main__":
    main()
