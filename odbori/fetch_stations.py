#!/usr/bin/env python3
"""Cache the official station list for every municipality."""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://www.rik.parlament.gov.rs"
H = {"X-Requested-With": "XMLHttpRequest", "User-Agent": "rezultatiizbora.rs/1.0"}
M = os.path.join(ROOT, "odbori", "municipalities_2026.json")
OUT = os.path.join(ROOT, "odbori", "stations")


def one(m):
    r = requests.post(B + "/get-election-stations/", data={
        "election_type": 2, "election_round": "680072",
        "election_region": m["region"], "election_municipality": m["id"],
    }, headers=H, timeout=45)
    r.raise_for_status()
    st = r.json().get("election_stations") or {}
    json.dump(st, open(os.path.join(OUT, m["slug"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    return m["slug"], len(st)


def main():
    os.makedirs(OUT, exist_ok=True)
    munis = json.load(open(M, encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, f in enumerate(as_completed([ex.submit(one, m) for m in munis]), 1):
            try:
                slug, n = f.result()
            except Exception as e:
                print("ERR", e)
            if i % 25 == 0:
                print(i, "/", len(munis))
    print("done")


if __name__ == "__main__":
    main()
