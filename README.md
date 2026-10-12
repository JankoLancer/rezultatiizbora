# Резултати избора у Србији — по бирачким местима

Скуп података и интерактивна мапа резултата избора по бирачким местима.
Тренутно садржи **парламентарне изборе 2023**: **8.273 бирачка места** (169
градова/јединица, 192 општине — укључујући Косово, затворе и иностранство), са
филтрирањем по **изборима**, граду/општини и опционо по градској општини.

Додавање нових избора своди се на један унос у `elections.json` + преузимање
података (види „Како додати нове изборе").

## Јавно доступно

Сајт је јавно доступан на **https://rezultatiizbora.rs**.

## Како отворити мапу локално

- **Преко сервера (препоручено):**
  ```bash
  python3 -m http.server 8000 --directory map
  # затим отвори http://localhost:8000/
  ```
  (Мапа учитава `data.json` преко `fetch`-а, па мора са сервера — не дво-кликом.)
- **Делинк** садржи и изборе и град: `…#parl2023/beograd`, `…#parl2023/nis`
  (ради и `?city=nis`); `…#parl2023/sve` приказује **све градове и општине**
  (цела Србија). URL се сам мења.
- Интернет је потребан само за плочице базне карте (OSM) и Leaflet са CDN-а.

## База података (SQLite)

Сви подаци су у једној релационој бази:

```bash
python3 build_db.py        # → db/izbori.db
```

Шема (табеле):
- `elections` (избори), `cities` (градови), `municipalities` (градске општине),
- `lists` (изборне листе, са кратким именом),
- `stations` (бирачка места: `number, name, place, address, lat, lon,
  location_source, registered, turnout, valid`),
- `results` (`station_id, list_id, votes, percent`) — **расподела гласова по
  сваком месту**,
- `documents` (линкови ка PDF записницима).

Погодни view-ови: `v_station_winner` (победник по месту),
`v_city_list_totals` (укупно по листи и граду), `v_city_totals` (укупно по
граду) и `v_municipality_totals` (укупно по градској општини).

Пример упита:
```sql
-- расподела гласова на једном месту
SELECT l.number, l.short_name, r.votes, r.percent
FROM results r JOIN lists l ON l.id=r.list_id
JOIN stations s ON s.id=r.station_id
WHERE s.number=42 AND s.municipality_id=(
  SELECT id FROM municipalities WHERE name='Град Београд')
ORDER BY r.votes DESC;

-- укупно по листи у граду
SELECT * FROM v_city_list_totals WHERE city='Београд' ORDER BY votes DESC;

-- број бирачких места и излазност по граду
SELECT c.name, COUNT(*) stations, SUM(s.registered) registered,
       ROUND(100.0*SUM(s.turnout)/SUM(s.registered),1) turnout_pct
FROM stations s JOIN cities c ON c.id=s.city_id GROUP BY c.id;
```

## Шта мапа приказује

- **Филтер по изборима** (горе лево): избор чији се резултати приказују.
- **Претрага града/општине**: ради и на **ћирилици и на латиници**
  (нпр. „Крагујевац" или „Kragujevac"), са предлозима — брз избор града или градске општине.
- **Филтер по граду/општини**: статистика, листе и легенда се мењају у складу
  са избором.
- **Филтер по општини**: појављује се кад изабрана јединица има више градских
  општина (Београд 17, Ниш 5).
- **Круг = једно бирачко место.** Боја = победничка листа. Величина = разлика
  између првог и другог (подразумевано у процентима; може у гласовима).
- **Клик на круг** отвара детаље: победник, другопласирани, разлика, излазност,
  број уписаних/изашлих/важећих гласова, листе и линк(ове) на PDF записник.
- **Све изборне листе** (у горњем левом панелу, са скролом): укупан број гласова
  по листи за изабрану јединицу.

## Структура

```
izbori_vizualizacija/
├── elections.json             # регистар избора (id, name, source_prefix)
├── download_rik_generic.py    # преузимање резултата и записника (регион + општине)
├── build_data.py              # спаја локације + резултате → map/data.json
├── build_db.py                # изградња SQLite базе → db/izbori.db
├── city_slugs.py              # генерисање URL slug-ова
├── deploy/                    # Dockerfile, Caddyfile, prepare_map.sh
├── db/izbori.db               # релациона база
├── geo/                       # скрипте и геокодирани подаци по јединици
│   ├── pipeline_opstina.py    # pipeline: преузимање → адресе → геокодирање
│   ├── opstina_docs.py        # парсирање .doc/.docx решења о гласачким местима
│   ├── geocode_locations.py   # геокодирање (Nominatim, кроз limiter)
│   ├── ratelimit.py           # глобални Nominatim лимитер (+ circuit-breaker)
│   ├── <slug>_stations_geo.json        # lat/lon по месту
│   └── <slug>_stations_locations.json  # адресе по месту
├── rik_<godina>_<slug>/       # сирови подаци (json/, documents/, manifest.csv, city.json)
└── map/
    ├── index.html             # интерактивна мапа (Leaflet)
    ├── data.json              # подаци за мапу (fetch; у gitu као .gz)
    └── robots.txt
```

## Порекло података

- **Резултати:** РИК, званична страница резултата
  (`rik.parlament.gov.rs/542645/rezultati/`) преко endpoint-а
  `/get-elections/`, `/get-regions/`, `/get-municipalities/`,
  `/get-election-stations/`, `/get_results/`.
- **Локације бирачких места:** тачне локације за изборе 2023. нису објављене,
  па су за места коришћени подаци из званичних решења о гласачким местима за
  **републички референдум 2022** (исти скуп места и општина, са изменама), а за
  град Крагујевац званична одлука за 2023. Геокодирање: OpenStreetMap / Nominatim.

## Како додати нове изборе

Платформа је вишеизборна. Нови избори се додају без измена у коду:

1. Упиши избор у `elections.json`:
   ```json
   { "elections": [
     { "id": "parl2026", "name": "Парламентарни 2026",
       "note": "Република Србија · ...", "source_prefix": "rik_2026_", "active": true }
   ] }
   ```
2. Преузми резултате и записнике у директоријуме `rik_2026_<slug>/`
   (`download_rik_generic.py` + по потреби `geo/run_opstina_group.py`).
3. Геокодирај бирачка места (исти pipeline → `geo/<slug>_stations_geo.json`) и
   напиши `rik_2026_<slug>/city.json` за сваку јединицу.
4. Покрени `python3 build_data.py && python3 build_db.py` — избор се сам појави
   у падајућем менију („Избори") и у табели `elections`.

`build_data.py` аутоматски открива јединице преко `source_prefix`, па су
измене у коду непотребне.

## Лиценца

Код: MIT (`LICENSE`). Подаци: званични подаци Републичке изборне комисије;
плочице © OpenStreetMap.
