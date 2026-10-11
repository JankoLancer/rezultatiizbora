#!/usr/bin/env python3
"""Build map/data.json for all elections registered in elections.json.

The platform is election-agnostic. Each election in elections.json declares an
`id`, a display `name`, and a `source_prefix`; every directory
`<source_prefix><slug>/` that contains a `city.json` (written by the download /
geocoding pipeline) is picked up automatically.

Output: map/data.json
  {
    "meta": {
      "elections": [ {id,name,note,...}, ... ],
      "colors": {listNo: color},
      "city_slugs": {cityName: slug},
      "by_election": { electionId: {cities:[...], by_city:{...}, totals:{...}} }
    },
    "stations": [ {election, no, city, muni, ..., results, winner, runner, ...} ]
  }
"""
import csv, glob, json, os, re
from html import unescape
from urllib.parse import urljoin

from city_slugs import city_slug

ROOT = os.path.dirname(os.path.abspath(__file__))
RIK = "https://www.rik.parlament.gov.rs"
OUTDIR = os.path.join(ROOT, "map")
REGISTRY = os.path.join(ROOT, "elections.json")
os.makedirs(OUTDIR, exist_ok=True)

LIST_COLORS = {1: "#1a6fb5", 2: "#8856a7", 3: "#e6550d", 4: "#31a354", 5: "#bd9e00",
               6: "#6b6b6b", 7: "#d7301f", 8: "#7fa8c9"}
DEFAULT_COLOR = "#9aa5b1"


def _station_count(res):
    p = os.path.join(ROOT, res, "manifest.csv")
    if not os.path.exists(p):
        return 0
    with open(p, encoding="utf-8-sig") as fh:
        return max(0, sum(1 for _ in fh) - 1)


def discover_cities(prefix):
    """Cities for one election, discovered from <prefix>* dirs with city.json."""
    cities = []
    for d in sorted(glob.glob(os.path.join(ROOT, prefix + "*"))):
        cj = os.path.join(d, "city.json")
        if not os.path.exists(cj):
            continue
        c = json.load(open(cj, encoding="utf-8"))
        c["res"] = os.path.basename(d)
        cities.append(c)
    cities = [c for c in cities
              if os.path.isdir(os.path.join(ROOT, c["res"]))
              and os.path.exists(os.path.join(ROOT, c["geo"]))]
    cities.sort(key=lambda c: (-_station_count(c["res"]), c["name"]))
    return cities


def load_geo(city):
    data = json.load(open(os.path.join(ROOT, city["geo"]), encoding="utf-8"))
    if city["muni_from_manifest"]:
        return {(d["municipality"], d["no"]): d for d in data}
    return {d["no"]: d for d in data}


def build_election(elec, colors):
    """Return (cities, stations, by_city, totals) for one election."""
    cities = discover_cities(elec["source_prefix"])
    stations, by_city = [], {}
    reg_tot = turn_tot = valid_tot = n_tot = 0
    eid = elec["id"]
    for city in cities:
        geo = load_geo(city)
        man_path = os.path.join(ROOT, city["res"], "manifest.csv")
        reg = turn = n = 0
        for r in csv.DictReader(open(man_path, encoding="utf-8-sig")):
            rikname = r["station_name"].strip()
            no = int(rikname.split(" - ", 1)[0])
            muni = r.get("municipality", "") or city["default_muni"]
            g = geo.get((muni, no)) if city["muni_from_manifest"] else geo.get(no, {})
            g = g or {}
            payload = json.load(open(os.path.join(ROOT, city["res"], "json", f"{r['station_id']}.json"),
                                     encoding="utf-8"))
            ssn = payload["stat_sum_numbers"]
            registered = int(str(ssn["total_voters"]).replace(".", ""))
            turnout = int(str(ssn["available"]).replace(".", ""))
            results = sorted(
                [{"n": e["count_number"], "name": re.sub(r"\s+", " ", e["list_name"]).strip(),
                  "votes": int(str(e["won_number"]).replace(".", "").replace(",", "")),
                  "pct": e["won_percent"]}
                 for e in payload["table_data"]], key=lambda e: (-e["votes"], e["n"]))
            valid = sum(x["votes"] for x in results)
            winner, runner = results[0], results[1] if len(results) > 1 else results[0]
            colors.setdefault(winner["n"], LIST_COLORS.get(winner["n"], DEFAULT_COLOR))
            colors.setdefault(runner["n"], LIST_COLORS.get(runner["n"], DEFAULT_COLOR))
            docs = [urljoin(RIK, unescape(h)) for h in
                    re.findall(r'href=[\'"]([^\'"]+)[\'"]', payload.get("minute_from_election_station") or "")]
            reg += registered; turn += turnout; n += 1
            reg_tot += registered; turn_tot += turnout; valid_tot += valid; n_tot += 1
            stations.append({
                "election": eid, "no": no, "sid": r["station_id"],
                "city": city["name"], "muni": muni, "name": rikname,
                "place": g.get("name", "") or g.get("venue", ""),
                "address": g.get("address", ""),
                "lat": g.get("lat"), "lon": g.get("lon"),
                "display": g.get("display", ""),
                "loc_source": g.get("source", ""),
                "registered": registered, "turnout": turnout, "valid": valid,
                "results": results,
                "winner": {"n": winner["n"], "name": winner["name"], "votes": winner["votes"],
                           "pct": winner["pct"], "color": LIST_COLORS.get(winner["n"], DEFAULT_COLOR)},
                "runner": {"n": runner["n"], "name": runner["name"], "votes": runner["votes"],
                           "pct": runner["pct"], "color": LIST_COLORS.get(runner["n"], DEFAULT_COLOR)},
                "margin_votes": winner["votes"] - runner["votes"],
                "margin_pct": round(winner["pct"] - runner["pct"], 2),
                "docs": docs,
            })
        by_city[city["name"]] = {"stations": n, "registered": reg, "turnout": turn,
                                 "turnout_pct": round(turn / reg * 100, 1) if reg else 0}
    totals = {"stations": n_tot, "registered": reg_tot, "turnout": turn_tot, "valid": valid_tot,
              "turnout_pct": round(turn_tot / reg_tot * 100, 1) if reg_tot else 0}
    return cities, stations, by_city, totals


def main():
    registry = json.load(open(REGISTRY, encoding="utf-8"))
    elections = [e for e in registry["elections"] if e.get("active", True)]

    all_stations, by_election, city_slugs, colors = [], {}, {}, {}
    for elec in elections:
        cities, stations, by_city, totals = build_election(elec, colors)
        by_election[elec["id"]] = {"cities": [c["name"] for c in cities],
                                   "by_city": by_city, "totals": totals}
        for c in cities:
            city_slugs[c["name"]] = city_slug(c["name"])
        all_stations += stations
        print(f"[{elec['id']}] {elec['name']}: {totals['stations']} stations, "
              f"{len(cities)} cities, {totals['registered']} registered, {totals['turnout_pct']}% turnout")

    data = {
        "meta": {
            "elections": [{"id": e["id"], "name": e["name"], "note": e.get("note", "")} for e in elections],
            "colors": {str(k): v for k, v in colors.items()},
            "city_slugs": city_slugs,
            "by_election": by_election,
        },
        "stations": all_stations,
    }
    json.dump(data, open(os.path.join(OUTDIR, "data.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print("total stations:", len(all_stations))


if __name__ == "__main__":
    main()
