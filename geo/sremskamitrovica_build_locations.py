#!/usr/bin/env python3
"""Align the RIK Sremska Mitrovica "glasacka mesta" doc to the RIK 2023 manifest.

Reuses the generic opstina_docs parser and pipeline_opstina align/read_manifest
helpers; writes geo/sremskamitrovica_stations_locations.json.

Usage: python3 geo/sremskamitrovica_build_locations.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import opstina_docs  # noqa: E402
import pipeline_opstina as P  # noqa: E402

SPEC = {"slug": "sremskamitrovica", "name": "Град Сремска Митровица"}
DOC = os.path.join(HERE, "sremskamitrovica_ref.doc")
OUT = os.path.join(HERE, "sremskamitrovica_stations_locations.json")


def main():
    man = P.read_manifest(SPEC)
    docs = [r for r in opstina_docs.parse(DOC) if r["no"] and (r["name"] or r["address"])]
    print(f"manifest={len(man)} doc_rows={len(docs)}")
    loc = P.align(SPEC, man, docs)

    mism = []
    for m in man:
        match = loc[[x["no"] for x in loc].index(m["no"])]
        if match["_docname"] and P.sim(match["_docname"], m["venue"]) < 0.4:
            mism.append((m["no"], m["venue"], match["_docname"]))

    json.dump(loc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {OUT} ({len(loc)})")
    if mism:
        print(f"NAME MISMATCHES ({len(mism)}):")
        for no, venue, docname in mism:
            print(f"  {no}: manifest={venue!r} doc={docname!r}")
    else:
        print("NAME MISMATCHES: none")
    missing_addr = [x["no"] for x in loc if not x["address"].strip()]
    print(f"empty addresses: {missing_addr or 'none'}")


if __name__ == "__main__":
    main()
