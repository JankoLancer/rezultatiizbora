#!/usr/bin/env python3
"""Shared city/municipality slug helper (Serbian Cyrillic -> Latin)."""
import re

# explicit slugs for the cities already integrated (kept stable)
OVERRIDES = {
    "Крагујевац": "kragujevac", "Ниш": "nis", "Нови Сад": "novisad",
    "Суботица": "subotica", "Београд": "beograd", "Јагодина": "jagodina",
    "Чачак": "cacak", "Краљево": "kraljevo", "Крушевац": "krusevac",
    "Лесковац": "leskovac", "Врање": "vranje", "Ваљево": "valjevo",
    "Шабац": "sabac", "Нови Пазар": "novipazar", "Лозница": "loznica",
    "Ужице": "uzice", "Пирот": "pirot", "Смедерево": "smederevo",
    "Сомбор": "sombor", "Панчево": "pancevo", "Зрењанин": "zrenjanin",
    "Зајечар": "zajecar", "Пожаревац": "pozarevac", "Кикинда": "kikinda",
    "Сремска Митровица": "sremskamitrovica", "Вршац": "vrsac", "Бор": "bor",
}

_TR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "dj", "е": "e",
    "ж": "z", "з": "z", "и": "i", "ј": "j", "к": "k", "л": "l", "љ": "lj",
    "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "ћ": "c", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "c",
    "џ": "dz", "ш": "s",
}


def _translit(name):
    out = []
    for ch in name:
        low = ch.lower()
        if low in _TR:
            t = _TR[low]
            out.append(t.upper() if ch.isupper() and len(t) == 1 else t)
        elif ch.isalnum():
            out.append(ch.lower())
    s = "".join(out)
    return re.sub(r"[^a-z0-9]+", "", s.lower()) or "muni"


def city_slug(name):
    name = (name or "").strip()
    return OVERRIDES.get(name, _translit(name))
