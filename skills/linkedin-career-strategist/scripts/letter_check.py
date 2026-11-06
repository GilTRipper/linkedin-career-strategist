#!/usr/bin/env python3
"""Проверка сопроводительного письма или сообщения на «шаблонность».

Использование:
  python letter_check.py LETTER [--type linkedin|email|cover] [--company NAME] [--vacancy FILE] [--json]

Ищет фразы из стоп-листа, проверяет длину под формат, однообразие предложений,
повторяющиеся начала, длинные тире, восклицания, эмодзи, конкретику (цифры, детали вакансии).
"""
import argparse
import json
import re
import statistics

from _textio import read_text, references_dir

LIMITS = {  # (единица, минимум, максимум)
    "linkedin": ("chars", 300, 600),
    "email": ("words", 120, 200),
    "cover": ("words", 150, 250),
}
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
TRIAD = re.compile(r"\b[\w-]+, [\w-]+,? (?:and|и) [\w-]+\b", re.I)
GENERIC_WORDS = {
    "experience", "team", "company", "position", "opportunity", "skills", "working", "would",
    "about", "their", "which", "where", "there", "these", "those", "other", "being", "years",
    "опыт", "команда", "компания", "позиция", "вакансия", "работа", "работы", "которые", "также",
}


def load_stop_phrases():
    res = []
    for raw in (references_dir() / "stop_phrases.txt").read_text(encoding="utf-8").splitlines():
        s = raw.strip().lower()
        if s and not s.startswith("#"):
            res.append(s)
    return res


def sentences(text):
    parts = re.split(r"(?<=[.!?…])\s+|\n{2,}", text.strip())
    return [p.strip() for p in parts if len(p.strip().split()) >= 2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("letter")
    ap.add_argument("--type", choices=LIMITS, default="cover")
    ap.add_argument("--company")
    ap.add_argument("--vacancy")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = read_text(args.letter)
    low = text.lower()
    issues = []

    hits = []
    for ph in load_stop_phrases():
        for m in re.finditer(re.escape(ph), low):
            s = max(0, m.start() - 30)
            hits.append({"phrase": ph, "context": "…" + text[s:m.end() + 30].replace("\n", " ") + "…"})
    if hits:
        issues.append(("❌", f"Фраз из стоп-листа: {len(hits)}. Замените конкретикой."))

    unit, lo, hi = LIMITS[args.type]
    words = len(re.findall(r"\w+", text))
    size = len(text) if unit == "chars" else words
    unit_ru = "символов" if unit == "chars" else "слов"
    if size > hi:
        issues.append(("⚠️", f"Длина {size} {unit_ru} — длиннее нормы для формата «{args.type}» ({lo}–{hi}). Сократите."))
    elif size < lo:
        issues.append(("⚠️", f"Длина {size} {unit_ru} — короче нормы ({lo}–{hi}). Возможно, не хватает истории с результатом."))

    sents = sentences(text)
    lens = [len(s.split()) for s in sents]
    stdev = round(statistics.pstdev(lens), 1) if len(lens) > 1 else 0
    if len(lens) >= 4 and stdev < 4:
        issues.append(("⚠️", f"Предложения почти одной длины (разброс {stdev} слов). Живой текст чередует короткие и длинные."))
    long_s = [s for s, n in zip(sents, lens) if n > 30]
    if long_s:
        issues.append(("⚠️", f"Очень длинных предложений (>30 слов): {len(long_s)}. Разбейте."))

    starts = {}
    for s in sents:
        w = re.findall(r"\w+", s.lower())
        if w:
            starts[w[0]] = starts.get(w[0], 0) + 1
    repeated = {w: n for w, n in starts.items() if n >= 3}
    if repeated:
        issues.append(("⚠️", "Однообразные начала предложений: " + ", ".join(f"«{w}» ×{n}" for w, n in repeated.items()) + "."))

    dashes = text.count("—")
    if dashes > 1:
        issues.append(("⚠️", f"Длинных тире: {dashes}. Частые «—» — заметный признак ИИ-текста; замените на точки или запятые."))
    if "!" in text:
        issues.append(("⚠️", f"Восклицательных знаков: {text.count('!')}. В деловом письме лучше без них."))
    if EMOJI.search(text):
        issues.append(("⚠️", "Есть эмодзи — в письме работодателю лучше убрать."))
    triads = TRIAD.findall(text)
    if len(triads) >= 2:
        issues.append(("⚠️", f"Перечислений «A, B и C»: {len(triads)}. Тройки ради ритма звучат шаблонно."))

    has_number = bool(re.search(r"\d", text))
    if not has_number:
        issues.append(("❌", "Нет ни одной цифры. Добавьте измеримый результат."))

    company_ok = None
    if args.company:
        company_ok = args.company.lower() in low
        if not company_ok:
            issues.append(("⚠️", f"Компания «{args.company}» в тексте не упомянута."))

    shared = []
    if args.vacancy:
        vac = read_text(args.vacancy).lower()
        vac_terms = {w for w in re.findall(r"[\w+#.-]{5,}", vac) if w not in GENERIC_WORDS}
        shared = sorted({w for w in re.findall(r"[\w+#.-]{5,}", low)} & vac_terms)
        if len(shared) < 3:
            issues.append(("⚠️", "Почти нет деталей из вакансии. Письмо можно отправить в любую компанию — добавьте 1–2 конкретики о них."))

    result = {
        "type": args.type, "size": size, "unit": unit, "limits": [lo, hi],
        "sentences": len(sents), "sentence_len_stdev": stdev, "has_number": has_number,
        "company_mentioned": company_ok, "shared_terms_with_vacancy": shared[:20],
        "stop_phrase_hits": hits, "issues": [{"level": l, "text": t} for l, t in issues],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("# Проверка письма\n")
    print(f"Формат: **{args.type}** · длина: **{size} {unit_ru}** (норма {lo}–{hi}) · предложений: {len(sents)} · разброс длины: {stdev}\n")
    if hits:
        print("## Фразы из стоп-листа\n")
        for h in hits:
            print(f"- **{h['phrase']}** — {h['context']}")
        print()
    if issues:
        print("## Замечания\n")
        for l, t in issues:
            print(f"- {l} {t}")
    else:
        print("✅ Явных признаков шаблона не найдено.")
    if shared:
        print("\nОбщие с вакансией термины: " + ", ".join(shared[:20]))


if __name__ == "__main__":
    main()
