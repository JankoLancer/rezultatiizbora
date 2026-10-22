#!/usr/bin/env python3
"""Report proposer strings that do not match any configured list/group."""
import glob
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "odbori"))
from build_odbori import list_for, DEFAULT_LIST  # noqa: E402

DATA = os.path.join(ROOT, "odbori", "data")


def main():
    c = Counter()
    examples = {}
    for path in glob.glob(os.path.join(DATA, "*_decisions.json")):
        slug = os.path.basename(path).replace("_decisions.json", "")
        try:
            rows = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for r in rows:
            entries = r.get("entries") or []
            for e in entries:
                p = (e.get("proposer") or "").strip()
                if p and list_for(p) is DEFAULT_LIST:
                    c[p] += 1
                    examples.setdefault(p, (slug, r.get("station_no"), e.get("name")))
            for ch in r.get("changes") or []:
                p = (ch.get("proposer") or "").strip()
                if p and list_for(p) is DEFAULT_LIST:
                    c[p] += 1
                    examples.setdefault(p, (slug, r.get("station_no"), ch.get("name")))
    print("unmapped proposer strings:", len(c), "occurrences:", sum(c.values()))
    for p, n in c.most_common():
        print(f"{n:5}  {p}  | {examples[p]}")


if __name__ == "__main__":
    main()
