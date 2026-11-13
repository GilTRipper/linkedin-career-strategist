#!/usr/bin/env python3
"""Право на работу: ищет в тексте вакансии требования к стране проживания, разрешению на работу,
спонсорству визы, релокации и местному языку.

Использование:
  python work_auth_check.py VACANCY [--json]

VACANCY — файл .txt/.md/.pdf/.docx с текстом вакансии (EN или RU).
Это измерение, а не вердикт: скрипт находит фразы и показывает их в контексте. Проходит ли кандидат,
решается по его гражданству, стране проживания и готовности к переезду (Шаг 0 в SKILL.md).
Шаблоны — эвристика: пропущенное требование допиши в CATEGORIES, ложное срабатывание видно по контексту.
"""
import argparse
import json
import re

from _textio import read_text

LANGS_EN = (
    "German|Polish|Dutch|French|Spanish|Portuguese|Italian|Czech|Slovak|Lithuanian|Latvian|Estonian|Greek|"
    "Arabic|Hebrew|Swedish|Danish|Norwegian|Finnish|Hungarian|Romanian|Bulgarian|Croatian|Serbian|Georgian|"
    "Japanese|Korean|Mandarin|Chinese|Turkish|Ukrainian|Russian"
)
LANGS_RU = (
    "немецк|польск|нидерландск|голландск|французск|испанск|португальск|итальянск|чешск|литовск|латышск|"
    "эстонск|греческ|арабск|иврит|шведск|финск|венгерск|румынск|сербск|грузинск|японск|турецк"
)

# (ключ, заголовок, шаблоны). Порядок категорий = порядок в отчёте.
CATEGORIES = [
    ("residency", "Требование проживания или локации", [
        r"\bmust (?:currently )?(?:be|reside|live) (?:based |located |living |residing )?in\b",
        r"\b(?:candidates?|applicants?|you) (?:must|should|need to|are required to) (?:be )?(?:based|located|resid\w*|liv\w*) in\b",
        r"\b(?:only|exclusively) (?:open|available|hiring|accepting)\b[^.\n]{0,40}\b(?:candidates?|applicants?|residents?|people|in|from)\b",
        r"\b(?:open|available) (?:only )?to (?:candidates?|applicants?|residents?)\b[^.\n]{0,30}\b(?:in|of|from|based)\b",
        r"\b(?:EU|EEA|UK|US|USA|Canada|LATAM|EMEA|APAC)[- ](?:based|only)\b",
        r"\bremote\b[^.\n]{0,15}\b(?:within|in|across|from)\b (?:the )?(?:EU|EEA|Europe|European Union|UK|United Kingdom|US|USA|United States|Canada|LATAM|EMEA)\b",
        r"\b(?:reside|live|located) in (?:one of )?the following (?:countries|states|locations)\b",
        r"\bresidents? of\b[^.\n]{0,30}\bonly\b",
        r"только (?:для )?(?:кандидатов|резидентов|граждан)\b",
        r"(?:находиться|проживать|жить|быть) (?:в|на территории)\b[^.\n]{0,25}(?:обязательн|только|необходим)",
        r"(?:обязательн\w*|необходим\w*|только) (?:проживание|нахождение|находиться|проживать)\b",
        r"без релокации",
    ]),
    ("work_auth", "Право на работу и документы", [
        r"\bright to work\b",
        r"\b(?:legally )?(?:authori[sz]ed|eligible|entitled|permitted) to work\b",
        r"\bwork(?:ing)? (?:authori[sz]ation|permit|eligibility)\b",
        r"\b(?:EU|EEA|US|UK|Swiss|Canadian) (?:citizen(?:ship)?s?|passport|national(?:ity|s)?)\b",
        r"\bcitizens? only\b",
        r"\b(?:security|government) clearance\b",
        r"\bpermanent resident\b",
        r"разрешени\w+ на работу",
        r"гражданств\w+ (?:РФ|России|РБ|Беларуси|ЕС|страны)",
        r"\bВНЖ\b|вид\w* на жительство",
    ]),
    ("sponsor_no", "Спонсорства или релокации нет", [
        r"\b(?:no|not|unable to|cannot|can't|can ?not|won't|will not|do not|don't|does not|doesn't|are not able to|is not able to)\b (?:currently |presently |at this time )?(?:\w+ ){0,3}?(?:sponsor\w*|visa support|relocation)\b",
        r"\bwithout (?:the need for |requiring )?(?:visa |work )?sponsorship\b",
        r"\b(?:visa |work )?sponsorship (?:is |will )?(?:not|n't) (?:be )?(?:available|offered|provided|possible|supported)\b",
        r"\bno (?:visa |work )?(?:sponsorship|relocation)\b",
        r"\brelocation (?:is |will )?(?:not|n't) (?:be )?(?:available|offered|provided|supported|covered)\b",
        r"\bnow or in the future\b",
        r"без (?:визовой поддержки|спонсорства)",
        r"(?:релокаци\w+|переезд\w*|визов\w+ поддержк\w+) не (?:предоставля\w+|предусмотрен\w*|оплачива\w+|оформля\w+)",
    ]),
    ("sponsor_yes", "Спонсорство или релокация есть", [
        r"\bvisa sponsorship\b",
        r"\bsponsorship (?:is )?(?:available|provided|offered|possible)\b",
        r"\b(?:we|will|can|able to|happy to|we'll|we can|we will)\b (?:\w+ ){0,2}?sponsor\b",
        r"\brelocation (?:package|support|assistance|bonus|budget|help|allowance|is (?:available|provided|offered|covered))\b",
        r"\b(?:help|support|assist)(?:s|ing)? (?:you )?(?:with |in )?(?:your |the )?relocat\w*",
        r"\b(?:EU )?Blue Card\b",
        r"\bvisa (?:support|assistance)\b",
        r"\bwork permit (?:support|assistance|sponsorship)\b",
        r"\brelocate (?:you )?to\b",
        r"визов\w+ поддержк\w+",
        r"(?:помо\w+|поддерж\w+|оплачива\w+|компенсир\w+) (?:\w+ )?(?:с |в )?(?:переезд\w*|релокаци\w+|оформлени\w+ виз\w*)",
        r"релокаци\w+ (?:в|на)\b",
    ]),
    ("language", "Местный язык", [
        r"\b(?:fluent|fluency|native|business|professional|working|good|strong|excellent|proficient|proficiency)\b[^.\n]{0,25}\b(?:" + LANGS_EN + r")\b",
        r"\b(?:" + LANGS_EN + r")\b[^.\n]{0,25}\b(?:required|mandatory|a must|must|fluent|native|C1|C2|B2|B1|level|speaking|skills|proficiency|is a plus|a plus|nice to have|preferred|advantage|bonus)\b",
        r"\bDeutschkenntnisse\b|\bfließend\w* Deutsch\b|\bDeutsch\b[^.\n]{0,15}\b(?:C1|B2|fließend|verhandlungssicher)\b",
        r"\bjęzyk\w* polsk\w*\b|\bpolski\w*\b[^.\n]{0,15}\b(?:B2|C1|biegł\w*)\b",
        r"(?:знание|владение)\b[^.\n]{0,20}(?:" + LANGS_RU + r")\w*",
    ]),
    ("contract", "Тип найма (контракт, B2B, EOR)", [
        r"\bB2B\b",
        r"\b(?:independent )?contractor\b",
        r"\bfreelanc\w*\b",
        r"\b(?:EOR|employer of record)\b",
        r"\b(?:Deel|Oyster|Remote\.com|Rippling)\b",
        r"\bИП\b|самозанят\w+|договор\w* ГПХ|\bГПХ\b",
    ]),
    ("format", "Формат и часовой пояс", [
        r"\b(?:fully |100% |full[- ])?remote\b",
        r"\bhybrid\b",
        r"\bon-?site\b|\bin[- ]office\b|\boffice[- ]based\b",
        r"\b(?:CET|CEST|EST|EDT|PST|PDT|GMT|BST|UTC|ET|PT)\b[^.\n]{0,25}\b(?:hours|time ?zone|overlap)\b",
        r"\btime ?zones?\b[^.\n]{0,30}\b(?:overlap|within|±|\+/-|hours)\b",
        r"удал[её]нн\w*|гибрид\w*|в офисе|офис в\b",
        r"(?m)^\s*(?:location|locations|локация|местоположение|город)\s*:.*$",  # шапка вакансии
    ]),
]

# Отрицания перед «спонсорство есть»: «we do not offer visa sponsorship» матчится и как yes, и как no.
NEG_BEFORE = re.compile(
    r"\b(?:no|not|unable|cannot|can't|without|don't|doesn't|won't|isn't|aren't|never)\b|(?:^|\s)(?:не|без|нет)\s",
    re.IGNORECASE)
NEG_AFTER = re.compile(
    r"^\W{0,3}(?:is |are |will )?(?:not|n't|unavailable)\b|^\W{0,3}не (?:предоставля|предусмотрен|оплачива)",
    re.IGNORECASE)
# Пометка «желательно» для языка: «German is a plus» — не требование.
NICE = re.compile(r"\b(?:plus|nice to have|nice-to-have|bonus|advantage|preferred|desirable)\b|плюсом|желательн|преимуществ",
                  re.IGNORECASE)

COMPILED = [(key, title, [re.compile(p, re.IGNORECASE) for p in pats]) for key, title, pats in CATEGORIES]
MAX_SHOWN = 8  # в текстовом отчёте; «remote» в длинной вакансии встречается десятки раз


def sentence_bounds(text, start, end):
    """Границы предложения вокруг совпадения: от последнего . ! ? или перевода строки до следующего."""
    left = max(text.rfind(ch, 0, start) for ch in ".!?\n")
    right_candidates = [i for i in (text.find(ch, end) for ch in ".!?\n") if i != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return left + 1, right


def context(text, start, end, s_start, s_end, limit=240):
    """Предложение с совпадением; длинное — обрезается до окна вокруг совпадения."""
    a, b = s_start, min(len(text), s_end + 1)
    if b - a > limit:
        a, b = max(s_start, start - limit // 2), min(b, end + limit // 2)
    snippet = re.sub(r"\s+", " ", text[a:b]).strip()
    return ("…" if a > s_start else "") + snippet + ("…" if b < s_end else "")


def scan(text):
    found = {key: [] for key, _, _ in COMPILED}
    seen = set()  # (категория, начало предложения): одно предложение — одна находка в категории
    for key, _, pats in COMPILED:
        for pat in pats:
            for m in pat.finditer(text):
                s_start, s_end = sentence_bounds(text, m.start(), m.end())
                target = key
                note = ""
                if key == "sponsor_yes":
                    before = text[max(s_start, m.start() - 60):m.start()]
                    after = text[m.end():min(s_end, m.end() + 30)]
                    if NEG_BEFORE.search(before) or NEG_AFTER.search(after):
                        target = "sponsor_no"
                        note = "с отрицанием"
                if key == "language" and NICE.search(text[s_start:s_end]):
                    note = "желательно, не требование"
                if (target, s_start) in seen:
                    continue
                seen.add((target, s_start))
                found[target].append({
                    "match": m.group(0),
                    "line": text.count("\n", 0, m.start()) + 1,
                    "context": context(text, m.start(), m.end(), s_start, s_end),
                    "note": note,
                })
    for items in found.values():
        items.sort(key=lambda i: i["line"])
    return found


def hint(found):
    """Подсказка, на что смотреть. Не вердикт: решение зависит от того, кто кандидат."""
    lang_required = [i for i in found["language"] if not i["note"]]
    restrictive = found["residency"] or found["work_auth"] or found["sponsor_no"] or lang_required
    if restrictive and not found["sponsor_yes"]:
        return ("Есть ограничения (проживание, право на работу, язык или «без спонсорства») и нет упоминаний "
                "спонсорства или релокации. Сверь с гражданством и страной кандидата до разбора навыков.")
    if restrictive and found["sponsor_yes"]:
        return ("Есть и ограничения, и упоминания спонсорства или релокации — прочитай контекст: часто это "
                "«спонсорство только для части стран» или «релокация в офис X».")
    if found["sponsor_yes"]:
        return "Спонсорство или релокация упомянуты, ограничений не найдено."
    return ("Явных требований к проживанию и спонсорству не найдено. Это не значит, что их нет: "
            "первым вопросом рекрутеру — как они оформляют кандидата из его страны.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vacancy")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = read_text(args.vacancy)
    found = scan(text)
    result = {
        "counts": {key: len(found[key]) for key, _, _ in COMPILED},
        "findings": found,
        "hint": hint(found),
        "note": "Эвристика по шаблонам фраз: это измерение, а не вердикт. Сверяйся с контекстом.",
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("# Право на работу: сигналы в вакансии\n")
    print("| Категория | Найдено |\n|---|---|")
    for key, title, _ in COMPILED:
        print(f"| {title} | {len(found[key]) or '—'} |")
    print()
    for key, title, _ in COMPILED:
        if not found[key]:
            continue
        print(f"## {title}\n")
        shown = found[key][:MAX_SHOWN]
        for i in shown:
            note = f" _({i['note']})_" if i["note"] else ""
            print(f"- строка {i['line']}: «{i['context']}»{note}")
        if len(found[key]) > MAX_SHOWN:
            print(f"- …и ещё {len(found[key]) - MAX_SHOWN} (полный список — с --json)")
        print()
    print(f"**Подсказка:** {result['hint']}\n")
    print("_" + result["note"] + "_")


if __name__ == "__main__":
    main()
