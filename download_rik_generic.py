#!/usr/bin/env python3
"""
Generic RIK downloader for one election round and a set of municipalities.

Usage:
  python3 download_rik_generic.py <out_dir> <election_round> <region> <name:value> [<name:value> ...]

Example (grad Niš = 5 city municipalities, parliamentary 2023, region 4):
  python3 download_rik_generic.py rik_2023_nis 341140 4 \
      Medijana:136 "Niska Banja:140" Palilula:137 Pantelej:139 "Crveni krst:138"
"""
import csv, json, os, re, sys, time
from html import unescape
from urllib.parse import quote, urljoin
import requests

BASE = "https://www.rik.parlament.gov.rs"
RESULTS_PAGE = f"{BASE}/542645/rezultati/"
ELECTION_TYPE = 2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": RESULTS_PAGE,
}
session = requests.Session()
session.headers.update(HEADERS)


def post(path, data):
    url = urljoin(BASE, path)
    for attempt in range(1, 5):
        try:
            r = session.post(url, data=data, timeout=60)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            if attempt == 4:
                raise
            time.sleep(2 * attempt)


def sanitize(name):
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return re.sub(r"\s+", " ", name).strip() or "file"


def main():
    out_dir, election_round, region = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    munis = [(a.split(":")[0], int(a.split(":")[1])) for a in sys.argv[4:]]
    json_dir = os.path.join(out_dir, "json")
    doc_dir = os.path.join(out_dir, "documents")
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(doc_dir, exist_ok=True)

    session.get(RESULTS_PAGE, timeout=60)

    manifest, total_files = [], 0
    all_stations = []
    for muni_name, muni_val in munis:
        stations = post("/get-election-stations/", {
            "election_type": ELECTION_TYPE, "election_round": election_round,
            "election_region": region, "election_municipality": muni_val}).json()["election_stations"]
        stations = {int(k): v for k, v in stations.items()}
        all_stations.append((muni_name, muni_val, stations))
        print(f"[{muni_name}] {len(stations)} stations")

    done = 0
    grand = sum(len(s) for _, _, s in all_stations)
    for muni_name, muni_val, stations in all_stations:
        for sid, sname in sorted(stations.items()):
            done += 1
            resp = post("/get_results/", {
                "should_update_pies": 1, "type": ELECTION_TYPE, "election_round": election_round,
                "region": region, "municipality": muni_val, "election_station": sid})
            try:
                payload = resp.json()
            except ValueError:
                print(f"  ! non-JSON for {sid}")
                continue
            with open(os.path.join(json_dir, f"{sid}.json"), "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)

            n_files = 0
            for link in re.findall(r'href=[\'"]([^\'"]+)[\'"]',
                                   payload.get("minute_from_election_station") or ""):
                link = unescape(link).strip()
                if not link:
                    continue
                abs_url = "https:" + link if link.startswith("//") else (
                    link if link.startswith("http") else urljoin(BASE, link))
                raw = os.path.basename(link.split("?")[0])
                dest = os.path.join(doc_dir, f"{sid}_{sanitize(raw)}")
                if os.path.exists(dest) and os.path.getsize(dest) > 0:
                    n_files += 1
                    continue
                safe = quote(abs_url, safe=":/?&=#%+@,;()[]{}!$'~")
                for attempt in range(1, 5):
                    try:
                        with session.get(safe, timeout=120, stream=True) as r:
                            r.raise_for_status()
                            with open(dest, "wb") as fh:
                                for chunk in r.iter_content(65536):
                                    fh.write(chunk)
                        n_files += 1
                        break
                    except requests.RequestException as exc:
                        if attempt == 4:
                            print(f"    ! {raw}: {exc}")
                        else:
                            time.sleep(2 * attempt)
            total_files += n_files
            ssn = payload.get("stat_sum_numbers", {})
            manifest.append({"station_id": sid, "municipality": muni_name,
                             "station_name": sname, "documents": n_files,
                             "total_voters": ssn.get("total_voters"),
                             "processed_stations": ssn.get("processed_stations")})
            if done % 20 == 0 or done == grand:
                print(f"  {done}/{grand} ...")
            time.sleep(0.2)

    with open(os.path.join(out_dir, "manifest.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0].keys()))
        w.writeheader(); w.writerows(manifest)

    rows = []
    for m in manifest:
        p = json.load(open(os.path.join(json_dir, f"{m['station_id']}.json"), encoding="utf-8"))
        for e in p.get("table_data", []):
            rows.append({"municipality": m["municipality"], "station_id": m["station_id"],
                         "station_name": m["station_name"], "list_number": e.get("count_number"),
                         "list_name": e.get("list_name"), "votes": e.get("won_number"),
                         "percent": e.get("won_percent")})
    with open(os.path.join(out_dir, "votes_by_station.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["municipality", "station_id", "station_name",
                                           "list_number", "list_name", "votes", "percent"])
        w.writeheader(); w.writerows(rows)

    print(f"\nDone. {len(manifest)} stations, {total_files} documents -> {out_dir}")


if __name__ == "__main__":
    main()
