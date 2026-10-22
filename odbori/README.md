# Бирачки одбори — парламентарни избори 2026.

Алат за преузимање, OCR и анализу решења о именовању бирачких одбора са сајта
Републичке изборне комисије, за све градове и општине.

## Извор

- Сајт: <https://www.rik.parlament.gov.rs/dokumenta/41985>
- Врста документа: **4 — РЕШЕЊА О ИМЕНОВАЊУ БИРАЧКИХ ОДБОРА**
- Изборни круг: **680072 — Парламентарни 2026**
- Документи су углавном скенирани PDF-ови; текст се извлачи Tesseract OCR-ом
  (прва страна, 150 dpi; друга страна само ако је потребна).

## Цевовод

```bash
# 0) једанпут: списак свих општина + метаподаци о документима
python3 odbori/discover_municipalities.py --metadata --workers 6

# 1) обрада у 6 балансираних бачева (може паралелно, сваки са 1 OCR радником)
python3 odbori/run_batch.py --batch 1/6 --download-workers 2 --ocr-workers 1
# ... 2/6 ... 6/6

# 2) након промене парсера/мапирања листа: поново парсирај и изгради
python3 odbori/rebuild_all.py --parse --build --workers 4

# 3) споји све градове у map/odbori.json и map/odbori.csv
python3 odbori/merge_odbori.py
```

За један град:

```bash
python3 odbori/scrape_odbori.py --slug nis --id <RIK id> --name "Град Ниш" \
  --download-workers 4 --ocr-workers 2 --dpi 150
python3 odbori/parse_odbori.py nis
python3 odbori/build_odbori.py nis
```

`municipalities_2026.json` садржи `id`, `slug`, регион, број бирачких места,
број докумената и датуме (`fetched_at`, `last_fetched_at`, `last_built_at`).

## Ажурирање за два дана

```bash
# поново провери све општине; постојећи PDF-ови и OCR текст се прескачу,
# скидају се и OCR-ују само нови документи
python3 odbori/run_batch.py --recheck --download-workers 4 --ocr-workers 4

# само општине којима још недостаје стални/проширени састав или имају грешку
python3 odbori/run_batch.py --recheck --only-missing --download-workers 4 --ocr-workers 4

python3 odbori/rebuild_all.py --parse --build --workers 4
python3 odbori/merge_odbori.py
```

`--only-missing` користи статусе из `odbori/work/status/<slug>.json`
(`missing_permanent`, `missing_expanded`, `state=error`). Без њега се
проверавају сви градови и хватају и нови документи у већ комплетним градовима.

## Шта се применом измена добија

За свако бирачко место и састав:

- основно решење (`imenovanje`) поставља почетни састав;
- допуне (`dopuna`) додају чланове/заменике;
- измене (`izmena`) замењују наведену особу (`уместо X ... именује Y`);
- исправке (`ispravka`) мењају име/податак у постојећем решењу;
- административне измене назива/адресе бирачког места се игноришу.

Редослед је хронолошки (по `datetime` из РИК-а). Ако се стара особа не пронађе,
покушава се приближно поклапање имена, затим јединствена улога/индекс.

## Структура

```
odbori/
├── discover_municipalities.py  # registar opština + metadata
├── scrape_odbori.py            # metadata → PDF → OCR
├── parse_odbori.py             # OCR → strukturirani podaci
├── build_odbori.py             # primena izmena → po gradu
├── merge_odbori.py             # svi gradovi → map/odbori.json/.csv
├── run_batch.py                # batch obrada / recheck
├── rebuild_all.py              # re-parse + rebuild bez OCR-a
├── audit_lists.py              # izveštaj nemapiranih predlagača
├── municipalities_2026.json    # committed: status svih opština
├── meta/<slug>.json            # RIK metadata (local)
├── data/<slug>_decisions.json  # parsed decisions (local)
├── data/<slug>_odbori.json     # finalni podaci za grad (local)
├── data/<slug>_people.csv      # ljudi za grad (local)
├── work/status/<slug>.json     # status obrade (local)
├── pdf/<slug>/                 # raw PDFs (gitignored)
└── ocr/<slug>/                 # OCR text (gitignored)
```

У git се држе скрипте, `municipalities_2026.json` и финални
`map/odbori.json.gz` / `map/odbori.csv.gz`. Сирови PDF-ови, OCR и међуфајлови
нису у гиту.

## Ограничења

- PDF-ови су скенирани; OCR може погрешити у именима (посебно `ђ`, `ћ`, `љ`, `њ`).
- За део бирачких места у неким општинама РИК још није објавио решења за један
  или оба састава. Та места се памте у статусу и допуњују у следећем прегледу.
- Правно релевантан податак је увек изворни PDF (линк је у подацима и на сајту).
