#!/usr/bin/env python3
"""Build a reusable SQLite database from map/data.json (all elections, cities).

Schema:
  elections, cities, municipalities, stations, lists, results, documents
plus convenience views. Re-runnable (drops and recreates everything).
"""
import json, os, re, sqlite3

from city_slugs import city_slug

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "map", "data.json")
DB = os.path.join(ROOT, "db", "izbori.db")
os.makedirs(os.path.dirname(DB), exist_ok=True)


def list_label(full):
    s = re.sub(r"^\s*\d+\.\s*", "", str(full)).strip()
    s = re.sub(r"^ИЗБОРН[АЕ]\s+ЛИСТ[АЕ]\s*", "", s, flags=re.I).strip()
    depth, cut = 0, len(s)
    for i, c in enumerate(s):
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth <= 0:
            if c in "-–—" and s[i-1] == " " and s[i+1] == " ":
                cut = i; break
            if c in ",;":
                cut = i; break
    out = re.sub(r"\s*\([^)]*$", "", s[:cut]).strip().strip('"„“”').strip(" ,-–—")
    return out or re.sub(r"^\d+\.\s*", "", str(full))


def main():
    d = json.load(open(DATA, encoding="utf-8"))
    meta, stations = d["meta"], d["stations"]
    elections = meta.get("elections", [])

    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript("""
    PRAGMA foreign_keys=ON;
    DROP VIEW  IF EXISTS v_station_winner;
    DROP VIEW  IF EXISTS v_city_list_totals;
    DROP VIEW  IF EXISTS v_city_totals;
    DROP VIEW  IF EXISTS v_municipality_totals;
    DROP TABLE IF EXISTS documents;
    DROP TABLE IF EXISTS results;
    DROP TABLE IF EXISTS stations;
    DROP TABLE IF EXISTS lists;
    DROP TABLE IF EXISTS municipalities;
    DROP TABLE IF EXISTS cities;
    DROP TABLE IF EXISTS elections;

    CREATE TABLE elections(
      id INTEGER PRIMARY KEY, slug TEXT UNIQUE, name TEXT, note TEXT);
    CREATE TABLE cities(
      id INTEGER PRIMARY KEY, name TEXT UNIQUE, slug TEXT UNIQUE, region TEXT);
    CREATE TABLE municipalities(
      id INTEGER PRIMARY KEY, city_id INT REFERENCES cities(id), name TEXT,
      UNIQUE(city_id,name));
    CREATE TABLE lists(
      id INTEGER PRIMARY KEY, election_id INT REFERENCES elections(id),
      number INT, name TEXT, short_name TEXT, UNIQUE(election_id,number));
    CREATE TABLE stations(
      id INTEGER PRIMARY KEY, election_id INT REFERENCES elections(id),
      city_id INT REFERENCES cities(id), municipality_id INT REFERENCES municipalities(id),
      number INT, name TEXT, place TEXT, address TEXT,
      lat REAL, lon REAL, location_source TEXT,
      registered INT, turnout INT, valid INT,
      UNIQUE(election_id, municipality_id, number));
    CREATE TABLE results(
      station_id INT REFERENCES stations(id), list_id INT REFERENCES lists(id),
      votes INT, percent REAL, PRIMARY KEY(station_id,list_id));
    CREATE TABLE documents(
      id INTEGER PRIMARY KEY, station_id INT REFERENCES stations(id), url TEXT);
    CREATE INDEX idx_stations_city ON stations(city_id);
    CREATE INDEX idx_stations_election ON stations(election_id);
    CREATE INDEX idx_results_station ON results(station_id);
    CREATE INDEX idx_results_list ON results(list_id);
    """)

    eid = {}
    for i, e in enumerate(elections):
        cur.execute("INSERT INTO elections(id,slug,name,note) VALUES(?,?,?,?)",
                    (i + 1, e["id"], e["name"], e.get("note", "")))
        eid[e["id"]] = i + 1

    slugs = meta.get("city_slugs", {})
    city_id = {}
    for name in slugs:
        cur.execute("INSERT INTO cities(name,slug,region) VALUES(?,?,?)",
                    (name, slugs.get(name) or city_slug(name), ""))
        city_id[name] = cur.lastrowid

    muni_id, list_id = {}, {}
    for s in stations:
        db_eid = eid.get(s["election"])
        cid = city_id[s["city"]]
        mkey = (cid, s["muni"])
        if mkey not in muni_id:
            cur.execute("INSERT INTO municipalities(city_id,name) VALUES(?,?)", mkey)
            muni_id[mkey] = cur.lastrowid
        mid = muni_id[mkey]
        cur.execute("""INSERT INTO stations(election_id,city_id,municipality_id,number,name,place,
                       address,lat,lon,location_source,registered,turnout,valid)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (db_eid, cid, mid, s["no"], s["name"], s.get("place") or "",
                     s.get("address") or "", s.get("lat"), s.get("lon"), s.get("loc_source") or "",
                     s.get("registered"), s.get("turnout"), s.get("valid")))
        sid = cur.lastrowid
        for r in s["results"]:
            lkey = (db_eid, r["n"])
            if lkey not in list_id:
                cur.execute("INSERT INTO lists(election_id,number,name,short_name) VALUES(?,?,?,?)",
                            (db_eid, r["n"], r["name"], list_label(r["name"])))
                list_id[lkey] = cur.lastrowid
            cur.execute("INSERT INTO results(station_id,list_id,votes,percent) VALUES(?,?,?,?)",
                        (sid, list_id[lkey], r.get("votes"), r.get("pct")))
        for u in s.get("docs", []):
            cur.execute("INSERT INTO documents(station_id,url) VALUES(?,?)", (sid, u))

    cur.executescript("""
    CREATE VIEW v_city_totals AS
      SELECT e.name AS election, c.id AS city_id, c.name AS city, c.slug, COUNT(s.id) AS stations,
             SUM(s.registered) AS registered, SUM(s.turnout) AS turnout, SUM(s.valid) AS valid,
             ROUND(100.0*SUM(s.turnout)/SUM(s.registered),1) AS turnout_pct
      FROM stations s JOIN cities c ON c.id=s.city_id JOIN elections e ON e.id=s.election_id
      GROUP BY s.election_id, c.id;
    CREATE VIEW v_municipality_totals AS
      SELECT e.name AS election, c.name AS city, m.name AS municipality, COUNT(s.id) AS stations,
             SUM(s.registered) AS registered, SUM(s.turnout) AS turnout,
             ROUND(100.0*SUM(s.turnout)/SUM(s.registered),1) AS turnout_pct
      FROM stations s JOIN municipalities m ON m.id=s.municipality_id
      JOIN cities c ON c.id=m.city_id JOIN elections e ON e.id=s.election_id
      GROUP BY s.election_id, m.id;
    CREATE VIEW v_station_winner AS
      SELECT s.id AS station_id, s.election_id, s.city_id, s.municipality_id, s.number, s.name,
             l.number AS winner_list_no, l.short_name AS winner_list, r.votes, r.percent
      FROM stations s
      JOIN results r ON r.station_id=s.id
      JOIN lists l ON l.id=r.list_id
      WHERE r.votes=(SELECT MAX(r2.votes) FROM results r2 WHERE r2.station_id=s.id);
    CREATE VIEW v_city_list_totals AS
      SELECT e.name AS election, c.name AS city, l.number AS list_no, l.short_name AS list,
             SUM(r.votes) AS votes,
             ROUND(100.0*SUM(r.votes)/SUM(SUM(r.votes)) OVER (PARTITION BY s.election_id, c.id),2) AS pct
      FROM results r JOIN stations s ON s.id=r.station_id
      JOIN cities c ON c.id=s.city_id JOIN lists l ON l.id=r.list_id
      JOIN elections e ON e.id=s.election_id
      GROUP BY s.election_id, c.id, l.id;
    """)
    con.commit()

    q = lambda sql: cur.execute(sql).fetchall()
    print("DB:", DB)
    for t in ("elections", "cities", "municipalities", "lists", "stations", "results", "documents"):
        print(f"  {t:16}", q(f"SELECT COUNT(*) FROM {t}")[0][0])
    print("  by election:", q("SELECT e.name, COUNT(s.id), SUM(s.registered) FROM elections e "
                             "LEFT JOIN stations s ON s.election_id=e.id GROUP BY e.id"))
    con.close()


if __name__ == "__main__":
    main()
