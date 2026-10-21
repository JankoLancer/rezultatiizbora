# Бирачки одбори — парламентарни избори 2026.

Алат за преузимање, OCR и анализу решења о именовању бирачких одбора са сајта
Републичке изборне комисије.

## Извор

- Сајт: <https://www.rik.parlament.gov.rs/dokumenta/41985>
- Врста документа: **4 — РЕШЕЊА О ИМЕНОВАЊУ БИРАЧКИХ ОДБОРА**
- Изборни круг: **680072 — Парламентарни 2026**
- Документи су PDF-ови (скенирани), па се текст извлачи Tesseract OCR-ом.

РИК API који страница користи:

```
GET /get-additional-documents
    ?page=1
    &filters[document-type]=4
    &filters[election-round]=680072
    &filters[municipality-id]=<id>
    &order=1&sort=1&election_type=2
```

`municipality-id` се добија преко:

```
GET /templates/election/getElectionStations.php?q=<назив>&electionId=680072
```

## Покретање

Зависности: Python 3, `requests`, `pdftoppm` (poppler-utils), `tesseract` са
језиком `srp` (`tesseract-ocr-srp`).

```bash
# 1) метаподаци + PDF-ови + OCR
python3 odbori/scrape_odbori.py "Град Крагујевац" --slug kragujevac --workers 4

# 2) парсирање OCR текста
python3 odbori/parse_odbori.py kragujevac

# 3) примена измена/допуна и агрегација
python3 odbori/build_odbori.py kragujevac
```

Резултат је `map/odbori.json`, који чита `map/odbori.html`.

## Шта се применом измена добија

За свако бирачко место и састав:

- основно решење (`imenovanje`) поставља почетни састав;
- допуне (`dopuna`) додају чланове/заменике;
- измене (`izmena`) замењују наведену особу (`уместо X ... именује Y`).

Редослед је хронолошки (по `datetime` из РИК-а). Ако се стара особа не пронађе,
покушава се приближно поклапање имена, затим јединствена улога/индекс; unresolved
случајеви се уписују у `problems` у излазном JSON-у.

## Структура

```
odbori/
├── scrape_odbori.py     # metadata → PDF → OCR
├── parse_odbori.py      # OCR → strukturirani podaci
├── build_odbori.py      # primena izmena → map/odbori.json
├── meta/<slug>.json     # RIK metadata (committed)
├── data/<slug>_decisions.json  # parsed decisions (committed)
├── data/<slug>_problems.json   # diagnostics (committed)
├── pdf/<slug>/          # raw PDFs (gitignored)
└── ocr/<slug>/          # OCR text (gitignored)
```

## Додавање новог града

1. Покрени `scrape_odbori.py` са називом општине/града sa RIK padajuće liste
   (нпр. `"Град Ниш"`, `"Општина Ада"`).
2. Покрени `parse_odbori.py <slug>` и прегледај `_problems.json`.
3. Покрени `build_odbori.py <slug>`.
4. У `map/odbori.html` додај град у `<select id="city">` и у `fetch` логику
   (тренутно је подржан један град; за више градова спојити JSON-ове).

## Ограничења

- PDF-ови су скенирани; OCR може погрешити у именима (посебно `ђ`, `ћ`, `љ`, `њ`).
- За 7 бирачких места у Крагујевцу (1, 3–8) у тренутку израде није било објављено
  решење за стални састав; проширени састав постоји за сва места.
- Правно релевантан податак је увек изворни PDF (линк је у подацима).
