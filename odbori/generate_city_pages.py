#!/usr/bin/env python3
"""Generate static, indexable city pages for the 2026 committee data.

Output:
  map/biracki-odbori/index.html          — hub with all cities
  map/biracki-odbori/<slug>.html         — one page per city
  map/sitemap.xml                        — updated with all pages
"""
import glob
import html
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "map")
OUT = os.path.join(MAP, "biracki-odbori")
DATA = os.path.join(MAP, "odbori.json")
BASE = "https://rezultatiizbora.rs"
AS_OF = "2026-10-22"

# Keep in sync with COALITIONS in map/odbori.html.
COALITIONS = [
    {
        "key": "evropska_srbija",
        "name": "Европска Србија — ССП + СРЦЕ",
        "short": "SSP+SRCE",
        "color": "#bd9e00",
        "members": ["ssp", "srce"],
    },
    {
        "key": "faktor_stabilnosti",
        "name": "Фактор стабилности — СПС + ЈС + СДПС",
        "short": "SPS+JS+SDPS",
        "color": "#e6550d",
        "members": ["sps", "js", "sdps"],
    },
]
GROUP_OF = {m: g["key"] for g in COALITIONS for m in g["members"]}


def group_key(k):
    return GROUP_OF.get(k, k)

TR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "dj", "е": "e",
    "ж": "z", "з": "z", "и": "i", "ј": "j", "к": "k", "л": "l", "љ": "lj",
    "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "ћ": "c", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "c",
    "џ": "dz", "ш": "s",
}


def latin(s):
    out = []
    for ch in s or "":
        low = ch.lower()
        if low in TR:
            t = TR[low]
            if ch.isupper():
                t = t[0].upper() + t[1:]
            out.append(t)
        elif ch.isalnum() or ch in " -/":
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def esc(s):
    return html.escape(str(s or ""), quote=True)


def pct(a, b):
    return round(1000 * a / b) / 10 if b else 0


def list_map(meta):
    lm = {l["key"]: l for l in meta.get("lists", [])}
    for g in COALITIONS:
        lm[g["key"]] = g
    return lm


def city_stats(stations):
    agg = defaultdict(lambda: {
        "ms": 0, "ds": 0, "mp": 0, "dp": 0, "stations": set(),
    })
    pub_s = pub_p = pub_union = 0
    for s in stations:
        has_s = bool(s["committees"]["stalni"]["total"])
        has_p = bool(s["committees"]["prosireni"]["total"])
        if has_s:
            pub_s += 1
        if has_p:
            pub_p += 1
        if has_s or has_p:
            pub_union += 1
        for comp, mk, dk in (("stalni", "ms", "ds"), ("prosireni", "mp", "dp")):
            for p in s["committees"][comp]["members"]:
                v = agg[group_key(p["list"])]
                if p.get("deputy"):
                    v[dk] += 1
                else:
                    v[mk] += 1
                    v["stations"].add(s["no"])
    return agg, pub_s, pub_p, pub_union


CSS = """
:root{--bg:#0f172a;--panel:#111c34;--panel2:#17233f;--ink:#e9eef7;--muted:#93a3bd;--line:#26344f;--accent:#38bdf8}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif;line-height:1.6}
a{color:var(--accent)}.wrap{max-width:1200px;margin:0 auto;padding:24px 20px 60px}
.back{display:inline-block;margin-bottom:10px;font-size:13px;text-decoration:none}
h1{margin:0 0 6px;font-size:28px;line-height:1.2}h2{font-size:18px;margin:26px 0 8px}
.lead{color:#c7d3e6;font-size:14.5px;margin:0 0 14px;max-width:900px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 18px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:10px 12px}
.kpi .k{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}.kpi .v{font-size:21px;font-weight:700}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:11px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:12.5px;white-space:nowrap}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}th{background:var(--panel2);font-size:11.5px;color:#c7d3e6}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}tr:last-child td{border-bottom:0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:-1px}
.chip{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:1px 5px;margin:1px 3px 1px 0;background:var(--panel2);font-size:10.5px}
.note{color:var(--muted);font-size:12px;margin:8px 0 0}.muted{color:var(--muted)}
.footer{margin-top:28px;color:var(--muted);font-size:12px;line-height:1.6}
details{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:8px 11px;margin:6px 0}
summary{cursor:pointer;font-weight:600}
.citygrid{display:grid;grid-template-columns:repeat(3,1fr);gap:5px 14px;font-size:13px}
.citygrid a{text-decoration:none}.citygrid a:hover{text-decoration:underline}
.region{margin:14px 0 4px;font-weight:700;color:#c7d3e6}
@media(max-width:800px){.kpis{grid-template-columns:repeat(2,1fr)}.citygrid{grid-template-columns:1fr}}
"""


GA = """<script async src="https://www.googletagmanager.com/gtag/js?id=G-1D190SES3N"></script>
<script>
window.dataLayer=window.dataLayer||[];
function gtag(){dataLayer.push(arguments);}
gtag('js',new Date());
gtag('config','G-1D190SES3N',{anonymize_ip:true,allow_google_signals:false,allow_ad_personalization_signals:false});
</script>"""


def head(title, desc, canonical, schema):
    return f"""<!DOCTYPE html>
<html lang="sr">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}" />
<meta name="robots" content="index, follow, max-image-preview:large" />
<meta name="keywords" content="{esc(title)}, birački odbori, kontrolori, izbori 2026, {esc(title.split('—')[-1].split('|')[0].strip())}" />
<link rel="canonical" href="{esc(canonical)}" />
<link rel="icon" href="../favicon.svg" type="image/svg+xml" />
<meta property="og:type" content="website" />
<meta property="og:locale" content="sr_RS" />
<meta property="og:site_name" content="Rezultati izbora — Srbija" />
<meta property="og:title" content="{esc(title)}" />
<meta property="og:description" content="{esc(desc)}" />
<meta property="og:url" content="{esc(canonical)}" />
<meta property="og:image" content="{BASE}/og.png" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{esc(title)}" />
<meta name="twitter:description" content="{esc(desc)}" />
{GA}
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<style>{CSS}</style>
</head>
<body><div class="wrap">"""


def footer():
    return f"""<div class="footer">
<p><strong>Izvor:</strong> <a href="https://www.rik.parlament.gov.rs/dokumenta/41985" target="_blank" rel="noopener">Republička izborna komisija</a> — javno objavljena rešenja o imenovanju biračkih odbora.
Ovo je nezvanična analiza; imena su izvučena OCR-om i mogu sadržati greške. Merodavan je izvorni PDF.</p>
<p><a href="../odbori.html">Interaktivna analiza svih gradova</a> · <a href="./">Svi gradovi</a> · <a href="../podaci.html">Podaci i metodologija</a> · <a href="../izbori2026.html">Izbori 2026</a> · <a href="../o-sajtu.html">O sajtu i pravna napomena</a></p>
<p>Ažurirano: {AS_OF}.</p>
</div></div></body></html>"""


def city_page(city, stations, meta, lm):
    slug = city["slug"]
    name = city["name"]
    lat = latin(name)
    agg, pub_s, pub_p, pub_union = city_stats(stations)
    controllers = sum(v["mp"] for v in agg.values())
    deputies = sum(v["dp"] for v in agg.values())
    rows = []
    for k, v in agg.items():
        info = lm.get(k, {"name": k, "short": k, "color": "#9aa5b1"})
        union = len(v["stations"])
        zero = max(0, pub_union - union)
        cov = min(100, pct(union, pub_union))
        rows.append((v["ms"] + v["mp"], info, v, union, zero, cov))
    rows.sort(key=lambda x: (-x[0], x[1]["name"]))

    summary_rows = "".join(
        f"<tr><td><span class='dot' style='background:{esc(info['color'])}'></span>"
        f"<strong>{esc(info['short'])}</strong> <span class='muted'>{esc(info['name'])}</span></td>"
        f"<td class='num'>{v['ms']}</td><td class='num'>{v['ds']}</td>"
        f"<td class='num'>{v['mp']}</td><td class='num'>{v['dp']}</td>"
        f"<td class='num'><strong>{v['ms']+v['mp']}</strong></td>"
        f"<td class='num'>{union}</td><td class='num'>{zero}</td><td class='num'>{cov}%</td></tr>"
        for _, info, v, union, zero, cov in rows
    ) or "<tr><td colspan='9' class='muted'>Nema podataka.</td></tr>"

    station_rows = []
    for s in stations:
        counts = defaultdict(int)
        for comp in ("stalni", "prosireni"):
            for p in s["committees"][comp]["members"]:
                if not p.get("deputy"):
                    counts[group_key(p["list"])] += 1
        chips = " ".join(
            f"<span class='chip'>{esc(lm.get(k, {'short': k}).get('short', k))} {n}</span>"
            for k, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        ) or "<span class='muted'>—</span>"
        station_rows.append(
            f"<tr><td class='num'>{s['no']}</td><td>{esc(s.get('name') or s.get('title') or '')}</td>"
            f"<td class='num'>{s['committees']['stalni']['total']}</td>"
            f"<td class='num'>{s['committees']['prosireni']['total']}</td><td>{chips}</td></tr>"
        )

    missing_p = city.get("missing_permanent_nos") or []
    missing_e = city.get("missing_expanded_nos") or []
    missing_bits = []
    if missing_p:
        missing_bits.append(f"stalni sastav — {len(missing_p)} mesta ({', '.join(map(str, missing_p[:20]))}{'…' if len(missing_p)>20 else ''})")
    if missing_e:
        missing_bits.append(f"prošireni sastav — {len(missing_e)} mesta ({', '.join(map(str, missing_e[:20]))}{'…' if len(missing_e)>20 else ''})")
    missing_html = ("Nedostaju podaci za: " + "; ".join(missing_bits)) if missing_bits else "Svi objavljeni sastavi su obrađeni."

    canonical = f"{BASE}/biracki-odbori/{slug}.html"
    title = f"Birački odbori 2026 — {lat}"
    desc = (f"Birački odbori 2026 — {lat}: {len(stations)} mesta, "
            f"{pub_s} sa stalnim i {pub_p} sa proširenim sastavom. Članovi, zamenici i pokrivenost po listama.")
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Dataset",
                "name": f"Birački odbori 2026 — {name}",
                "description": desc,
                "url": canonical,
                "inLanguage": "sr",
                "isAccessibleForFree": True,
                "spatialCoverage": {"@type": "Place", "name": name},
                "temporalCoverage": "2026-10-25",
                "dateModified": AS_OF,
                "creator": {"@type": "Organization", "name": "Rezultati izbora — Srbija", "url": BASE + "/"},
                "variableMeasured": ["članovi", "zamenici", "kontrolori", "pokrivenost po listama"],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Početna", "item": BASE + "/"},
                    {"@type": "ListItem", "position": 2, "name": "Izbori 2026", "item": BASE + "/izbori2026.html"},
                    {"@type": "ListItem", "position": 3, "name": "Birački odbori", "item": BASE + "/odbori.html"},
                    {"@type": "ListItem", "position": 4, "name": name, "item": canonical},
                ],
            },
        ],
    }
    body = head(title, desc, canonical, schema)
    body += f"""<a class="back" href="./">← Svi gradovi</a> · <a class="back" href="../izbori2026.html">Izbori 2026</a>
<h1>Birački odbori 2026 — {esc(name)} <span class="muted">({esc(lat)})</span></h1>
<p class="lead">Pregled imenovanja u biračke odbore za parlamentarne izbore 2026. za
<strong>{esc(name)}</strong> (<em>{esc(lat)}</em>). Prikazani su članovi, zamenici i
kontrolori po izbornim listama, sa pokrivenošću po objavljenim biračkim mestima.</p>
<div class="kpis">
<div class="kpi"><div class="k">Biračka mesta</div><div class="v">{len(stations)}</div></div>
<div class="kpi"><div class="k">Stalni sastav</div><div class="v">{pub_s}</div></div>
<div class="kpi"><div class="k">Prošireni sastav</div><div class="v">{pub_p}</div></div>
<div class="kpi"><div class="k">Kontrolori</div><div class="v">{controllers}</div></div>
</div>
<h2>Članovi i pokrivenost po listama</h2>
<p class="note">Pokrivenost = broj objavljenih mesta gde lista ima bar jednog člana / broj objavljenih mesta
za prikaz. Za prikaz oba sastava, imenilac su mesta gde je objavljen bar jedan sastav (stalni ili
prošireni; ovde {pub_union}). Kolona „Bez“ je broj objavljenih mesta bez člana te liste. Zato kombinovana pokrivenost
može biti niža od pokrivenosti samo proširenog sastava.</p>
<p class="note">Koalicione liste su grupisane: Evropska Srbija (SSP + SRCE) i Faktor stabilnosti
(SPS + JS + SDPS). CSV i JSON zadržavaju izvorne oznake listi.</p>
<div class="tablewrap"><table>
<thead><tr><th>Lista / grupa</th><th class="num">Stalni član.</th><th class="num">Stalni zam.</th>
<th class="num">Prošireni član.</th><th class="num">Prošireni zam.</th><th class="num">Ukupno članova</th>
<th class="num" title="Jedinstvena mesta gde lista ima člana u stalnom ili proširenom sastavu">Mesta</th><th class="num" title="Objavljena mesta (bar jedan sastav) bez člana liste">Bez</th><th class="num">Pokrivenost</th></tr></thead>
<tbody>{summary_rows}</tbody></table></div>
<p class="note">Ukupno kontrolora u proširenom sastavu: <strong>{controllers}</strong>;
zamenika: <strong>{deputies}</strong>.</p>
<h2>Biračka mesta i liste</h2>
<p class="note">Brojevi u koloni „Liste“ su broj članova te liste na tom mestu (bez zamenika).</p>
<div class="tablewrap"><table>
<thead><tr><th class="num">BM</th><th>Biračko mesto</th><th class="num">Stalni</th><th class="num">Prošireni</th><th>Liste</th></tr></thead>
<tbody>{''.join(station_rows)}</tbody></table></div>
<h2>Nedostajuća mesta</h2>
<p>{esc(missing_html)}</p>
<h2>Interaktivni prikaz</h2>
<p><a href="../odbori.html#city={esc(slug)}">Otvori interaktivnu analizu za {esc(name)}</a> — filtriranje po listama,
matrica mesto × lista, pretraga imena i prikaz mesta na kojima nedostaju kontrolori ili stalni sastav.</p>
"""
    body += footer()
    return body


def hub_page(data):
    meta = data["meta"]
    cities = meta["cities"]
    summary = data["summary"]
    lm = list_map(meta)
    controllers = sum(r["members"] for r in summary["by_list"]["prosireni"])
    published_union = sum(1 for x in data["stations"] if x["committees"]["stalni"]["total"] or x["committees"]["prosireni"]["total"])
    published_union_label = f"{published_union:,}".replace(",", ".")
    groups = defaultdict(list)
    for c in cities:
        groups[c.get("region_name") or "Ostalo"].append(c)
    chunks = []
    for region in sorted(groups):
        chunks.append(f"<div class='region'>{esc(region)}</div><div class='citygrid'>")
        for c in sorted(groups[region], key=lambda x: x["name"]):
            chunks.append(
                f"<a href='{esc(c['slug'])}.html'>{esc(c['name'])}</a> "
                f"<span class='muted'>({esc(latin(c['name']))}, {c.get('stations_total') or 0} м.)</span>"
            )
        chunks.append("</div>")
    city_html = "".join(chunks)
    canonical = BASE + "/biracki-odbori/"
    title = "Birački odbori 2026 — svi gradovi i opštine"
    desc = (f"Statički pregled biračkih odbora 2026 za sve gradove i opštine: "
            f"{summary['stations_total']} biračkih mesta, {controllers} kontrolora i pokrivenost po izbornim listama.")
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "CollectionPage", "name": title, "url": canonical, "inLanguage": "sr",
             "description": desc, "dateModified": AS_OF},
            {"@type": "ItemList", "name": "Gradovi i opštine — birački odbori 2026",
             "numberOfItems": len(cities),
             "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": c["name"],
                 "url": f"{BASE}/biracki-odbori/{c['slug']}.html"}
                for i, c in enumerate(sorted(cities, key=lambda x: x["name"]))
             ]},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Početna", "item": BASE + "/"},
                {"@type": "ListItem", "position": 2, "name": "Izbori 2026", "item": BASE + "/izbori2026.html"},
                {"@type": "ListItem", "position": 3, "name": "Birački odbori", "item": BASE + "/odbori.html"},
                {"@type": "ListItem", "position": 4, "name": "Svi gradovi", "item": canonical},
            ]},
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": "Koliko gradova i opština je obrađeno?",
                 "acceptedAnswer": {"@type": "Answer", "text": f"Obrađeno je {len(cities)} gradova i opština i {summary['stations_total']} biračkih mesta."}},
                {"@type": "Question", "name": "Koliko ima kontrolora u proširenom sastavu?",
                 "acceptedAnswer": {"@type": "Answer", "text": f"U proširenom sastavu prikazano je {controllers} članova (kontrolora) i zamenika po listama."}},
                {"@type": "Question", "name": "Kako se računa pokrivenost?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Pokrivenost je broj objavljenih biračkih mesta gde lista ima bar jednog člana, podeljen brojem objavljenih mesta za taj prikaz. Za oba sastava, imenilac su mesta gde je objavljen bar jedan sastav."}},
            ]},
        ],
    }
    body = head(title, desc, canonical, schema)
    body += f"""<a class="back" href="../odbori.html">← Interaktivna analiza</a> · <a class="back" href="../izbori2026.html">Izbori 2026</a>
<h1>Birački odbori 2026 — svi gradovi i opštine</h1>
<p class="lead">Statički pregled imenovanja u biračke odbore za parlamentarne izbore 2026.
Za svaki grad i opštinu prikazani su članovi, zamenici, kontrolori i pokrivenost po izbornim listama.
Ovo je pregled bez učitavanja velikog JSON fajla; interaktivna analiza je dostupna na
<a href="../odbori.html">odbori.html</a> i uključuje prikaz mesta na kojima listama nedostaju
kontrolori ili stalni sastav.</p>
<div class="kpis">
<div class="kpi"><div class="k">Gradova / opština</div><div class="v">{len(cities)}</div></div>
<div class="kpi"><div class="k">Biračkih mesta</div><div class="v">{summary['stations_total']}</div></div>
<div class="kpi"><div class="k">Stalni sastav</div><div class="v">{summary['stations_stalni']}</div></div>
<div class="kpi"><div class="k">Kontrolori</div><div class="v">{controllers}</div></div>
</div>
<h2>Gradovi i opštine</h2>
{city_html}
<h2>Kako se računa pokrivenost</h2>
<p>Pokrivenost liste je broj <strong>objavljenih biračkih mesta</strong> na kojima lista ima bar
jednog člana, podeljen brojem objavljenih mesta za taj prikaz. Za pojedinačan sastav, imenilac
su mesta gde je taj sastav objavljen; za oba sastava, imenilac su mesta gde je objavljen bar
jedan sastav (stalni ili prošireni; na nivou Srbije {published_union_label}). Mesta bez ijednog objavljenog sastava ne ulaze u pokrivenost.
Zato kombinovana pokrivenost može biti niža od pokrivenosti samo proširenog sastava.</p>
<p><strong>Grupisanje koalicija.</strong> U tabelama su grupisane Evropska Srbija
(SSP + SRCE) i Faktor stabilnosti (SPS + JS + SDPS). CSV i JSON zadržavaju izvorne
<code>list_key</code> oznake; grupisanje je samo prikaz.</p>
<h2>Najčešća pitanja</h2>
<details><summary>Šta je razlika između stalnog i proširenog sastava?</summary>
<p>Stalni sastav čine predsednik, zamenik predsednika, dva člana i dva zamenika članova.
Prošireni sastav čine član i zamenik člana koje predlaže svaka izborna lista; takve članove
najčešće zovemo kontrolorima.</p></details>
<details><summary>Zašto neki grad ima manje objavljenih mesta?</summary>
<p>RIK objavljuje rešenja postepeno. Ako za neko mesto nema rešenja za stalni ili prošireni
sastav, ono je označeno kao nedostajuće i biće dopunjeno u sledećem pregledu.</p></details>
"""
    body += footer().replace("../odbori.html", "../odbori.html")
    return body


def update_sitemap(cities, asof):
    path = os.path.join(MAP, "sitemap.xml")
    existing = open(path, encoding="utf-8").read()
    # remove old generated city entries and hub if present
    existing = re.sub(r"\s*<url>\s*<loc>https://rezultatiizbora\.rs/(?:biracki-odbori/[^<]*|podaci\.html)</loc>.*?</url>", "", existing, flags=re.S)
    urls = [
        ("https://rezultatiizbora.rs/biracki-odbori/", "0.8"),
        ("https://rezultatiizbora.rs/podaci.html", "0.8"),
    ] + [(f"https://rezultatiizbora.rs/biracki-odbori/{c['slug']}.html", "0.6") for c in cities]
    add = "".join(
        f"""  <url>
    <loc>{u}</loc>
    <lastmod>{asof}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>{p}</priority>
  </url>
"""
        for u, p in urls
    )
    existing = existing.replace("</urlset>", add + "</urlset>")
    open(path, "w", encoding="utf-8").write(existing)


def main():
    global AS_OF
    data = json.load(open(DATA, encoding="utf-8"))
    AS_OF = (data["meta"].get("data_as_of") or AS_OF)[:10]
    meta = data["meta"]
    stations = data["stations"]
    by_city = defaultdict(list)
    for s in stations:
        by_city[s["city_slug"]].append(s)
    os.makedirs(OUT, exist_ok=True)
    lm = list_map(meta)
    for c in meta["cities"]:
        slug = c["slug"]
        page = city_page(c, by_city.get(slug, []), meta, lm)
        open(os.path.join(OUT, slug + ".html"), "w", encoding="utf-8").write(page)
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(hub_page(data))
    update_sitemap(meta["cities"], AS_OF)
    print(f"wrote {len(meta['cities'])} city pages + hub")


if __name__ == "__main__":
    main()
