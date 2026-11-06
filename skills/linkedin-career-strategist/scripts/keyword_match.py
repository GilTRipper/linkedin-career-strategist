#!/usr/bin/env python3
"""Сверка ключевых слов вакансии с CV и/или профилем LinkedIn.

Использование:
  python keyword_match.py VACANCY CANDIDATE [CANDIDATE ...] [--json]

VACANCY и CANDIDATE — файлы .txt/.md/.pdf/.docx (текст вакансии, CV, экспорт профиля).
Результат детерминирован: один и тот же вход всегда даёт один и тот же отчёт.
"""
import argparse
import json
import re
from collections import Counter

from _textio import read_text, references_dir

NICE_MARKERS = [
    "nice to have", "nice-to-have", "would be a plus", "is a plus", "a plus", "bonus",
    "preferred", "desirable", "будет плюсом", "плюсом", "желательно", "преимуществом",
    "будет преимуществом",
]
MUST_MARKERS = [
    "requirements", "must have", "must-have", "you have", "what we expect", "qualifications",
    "what you bring", "you will need", "требования", "мы ожидаем", "ожидаем", "обязательно",
    "что нужно", "мы ждём", "мы ждем", "необходимо",
]
OTHER_MARKERS = [
    "responsibilities", "what you will do", "about us", "we offer", "benefits", "обязанности",
    "задачи", "о нас", "мы предлагаем", "условия",
]

STOP_TOKENS = {
    "we", "you", "our", "the", "and", "or", "for", "with", "team", "experience", "years",
    "strong", "good", "knowledge", "understanding", "ability", "work", "working", "will",
    "join", "help", "build", "about", "what", "who", "why", "how", "us", "this", "they",
    "senior", "middle", "junior", "lead", "remote", "office", "hybrid", "full", "time",
    "salary", "benefits", "english", "русский", "company", "product", "role", "position",
    "a", "an", "in", "on", "of", "to", "is", "are", "be", "as", "at", "by", "it", "if",
    "nice", "plus", "must", "have", "requirements", "responsibilities", "bonus", "preferred",
}


def load_dictionary():
    entries = []
    for raw in (references_dir() / "skills_dictionary.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, aliases = line.split(":", 1)
        patterns = []
        for a in [x.strip() for x in aliases.split(",") if x.strip()]:
            case_sensitive = a.startswith("=")
            a = a.lstrip("=")
            pat = r"(?<![\w.+#-])" + re.escape(a).replace(r"\ ", r"[\s-]+") + r"(?![\w+#])"
            patterns.append(re.compile(pat, 0 if case_sensitive else re.IGNORECASE))
        entries.append((name.strip(), patterns))
    return entries


def found(entry_patterns, text):
    return any(p.search(text) for p in entry_patterns)


def classify_lines(vacancy):
    """Возвращает список (section, line); section in {must, nice, other}."""
    section = "must"
    out = []
    for line in vacancy.splitlines():
        low = line.strip().lower()
        if not low:
            continue
        is_heading = len(low) < 80
        if is_heading and any(m in low for m in OTHER_MARKERS) and not any(m in low for m in MUST_MARKERS):
            section = "other"
            continue
        if is_heading and any(m in low for m in NICE_MARKERS) and len(low) < 40:
            section = "nice"
            continue
        if is_heading and any(m in low for m in MUST_MARKERS):
            section = "must"
            continue
        line_section = "nice" if any(m in low for m in NICE_MARKERS) else section
        out.append((line_section, line))
    return out


def unknown_terms(vacancy, known_hit_spans_text, candidate):
    tokens = re.findall(r"(?<![\w])[A-Za-z][A-Za-z0-9.+#/-]{1,}(?![\w])", vacancy)
    cnt = Counter()
    for t in tokens:
        t = t.strip(".-/")
        if len(t) < 2 or t.lower() in STOP_TOKENS:
            continue
        looks_tech = (t[0].isupper() and not t.isupper() and len(t) > 2) or t.isupper() or any(c in t for c in ".+#") or any(c.isdigit() for c in t)
        if looks_tech and t.lower() not in known_hit_spans_text:
            cnt[t] += 1
    res = []
    for term, n in cnt.most_common(25):
        in_cv = re.search(r"(?<![\w])" + re.escape(term) + r"(?![\w])", candidate, re.IGNORECASE) is not None
        res.append({"term": term, "mentions": n, "in_candidate": in_cv})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vacancy")
    ap.add_argument("candidate", nargs="+")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    vacancy = read_text(args.vacancy)
    candidate = "\n".join(read_text(c) for c in args.candidate)
    dictionary = load_dictionary()
    lines = classify_lines(vacancy)

    req = {}  # name -> section (must wins over nice, nice over other)
    rank = {"must": 0, "nice": 1, "other": 2}
    for section, line in lines:
        for name, pats in dictionary:
            if found(pats, line):
                if name not in req or rank[section] < rank[req[name]]:
                    req[name] = section

    groups = {"must": [], "nice": [], "other": []}
    for name in sorted(req):
        groups[req[name]].append({"skill": name, "in_candidate": found(dict(dictionary)[name], candidate)})

    def pct(items):
        return round(100 * sum(i["in_candidate"] for i in items) / len(items)) if items else None

    must_p, nice_p = pct(groups["must"]), pct(groups["nice"])
    if must_p is not None and nice_p is not None:
        overall = round(0.75 * must_p + 0.25 * nice_p)
    else:
        overall = must_p if must_p is not None else nice_p

    known_text = " ".join(req).lower() + " " + " ".join(
        a for _, pats in dictionary for a in [p.pattern.lower() for p in pats])
    unk = unknown_terms(vacancy, known_text, candidate)

    result = {
        "coverage_must_pct": must_p,
        "coverage_nice_pct": nice_p,
        "coverage_overall_pct": overall,
        "must": groups["must"], "nice": groups["nice"], "mentioned_elsewhere": groups["other"],
        "missing_must": [i["skill"] for i in groups["must"] if not i["in_candidate"]],
        "missing_nice": [i["skill"] for i in groups["nice"] if not i["in_candidate"]],
        "unknown_terms_to_review": unk,
        "note": "Секции must/nice определены по заголовкам вакансии эвристически; если в вакансии нет заголовков, всё считается обязательным.",
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    def fmt(v):
        return "—" if v is None else f"{v}%"

    print("# Сверка ключевых слов\n")
    print(f"Покрытие обязательных: **{fmt(must_p)}** · желательных: **{fmt(nice_p)}** · итог: **{fmt(overall)}**\n")
    for key, title in (("must", "Обязательные"), ("nice", "Желательные"), ("other", "Упомянуты в других разделах")):
        if groups[key]:
            print(f"## {title}\n")
            print("| Навык | В CV/профиле |\n|---|---|")
            for i in groups[key]:
                print(f"| {i['skill']} | {'✅' if i['in_candidate'] else '❌'} |")
            print()
    if result["missing_must"]:
        print("**Не хватает обязательных:** " + ", ".join(result["missing_must"]) + "\n")
    if unk:
        print("## Термины вне словаря — проверь вручную\n")
        print("| Термин | Упоминаний в вакансии | В CV/профиле |\n|---|---|---|")
        for u in unk:
            print(f"| {u['term']} | {u['mentions']} | {'✅' if u['in_candidate'] else '❌'} |")
        print()
    print("_" + result["note"] + "_")


if __name__ == "__main__":
    main()
