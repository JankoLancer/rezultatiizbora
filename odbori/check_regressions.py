#!/usr/bin/env python3
"""Small regression checks for issues found during the 2026 audit.

Run after a rebuild:
  python3 odbori/check_regressions.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path):
    return json.load(open(os.path.join(ROOT, path), encoding="utf-8"))


def main():
    # Aleksinac BM 9: the RIK change was previously classified as a fresh
    # appointment with zero entries and erased the whole expanded roster.
    city = load("odbori/data/aleksinac_odbori.json")
    station = next(s for s in city["stations"] if s["no"] == 9)
    assert station["committees"]["prosireni"]["total"] >= 20, station["committees"]["prosireni"]["total"]
    names = {p["name"] for p in station["committees"]["prosireni"]["members"]}
    assert "Славица Радић" in names, "the 21 Oct change was not applied"

    # Permanent decisions sometimes carry only a party acronym after the name
    # ("Milan Pavlović, SNS"), without "na predlog ...".
    city = load("odbori/data/aleksinac_odbori.json")
    station = next(s for s in city["stations"] if s["no"] == 68)
    milan = next(p for p in station["committees"]["stalni"]["members"] if p["name"] == "Милан Павловић")
    assert milan.get("list") == "sns", milan

    # JMBG columns between a name and its deputy must not be mistaken for a
    # party acronym, otherwise the Student-list member loses its list.
    city = load("odbori/data/gradvrsac_odbori.json")
    station = next(s for s in city["stations"] if s["no"] == 1)
    tatjana = next(p for p in station["committees"]["prosireni"]["members"] if p["name"] == "ТАТЈАНА ПЕТРОВИЋ")
    assert tatjana.get("list") == "studenti", tatjana

    # A document whose official RIK title says "измена" must never be parsed
    # as a base appointment; that was the root cause of wiped rosters.
    bad = []
    for path in glob.glob(os.path.join(ROOT, "odbori", "data", "*_decisions.json")):
        slug = os.path.basename(path).replace("_decisions.json", "")
        for doc in json.load(open(path, encoding="utf-8")):
            title = (doc.get("decision_title") or "").lower()
            if "измен" in title and doc.get("type") == "imenovanje":
                bad.append((slug, doc.get("station_no"), doc.get("url")))
    assert not bad, bad[:5]

    print("regression checks OK")


if __name__ == "__main__":
    main()
