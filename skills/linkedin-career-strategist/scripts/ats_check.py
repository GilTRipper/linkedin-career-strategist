#!/usr/bin/env python3
"""Проверка CV на читаемость для ATS.

Использование:
  python ats_check.py CV.pdf|CV.docx [--dump extracted.txt] [--json]

Показывает текст так, как его увидит типичный парсер, и ищет то, что ломает разбор:
колонки, таблицы, картинки, текст в колонтитулах, нестандартные заголовки, нет контактов.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SECTION_HEADERS = {
    "experience": ["experience", "work experience", "professional experience", "employment", "опыт работы", "опыт"],
    "education": ["education", "образование"],
    "skills": ["skills", "technical skills", "навыки", "ключевые навыки", "технологии", "стек"],
    "summary": ["summary", "profile", "about", "о себе", "обо мне", "профиль"],
}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


class _Phone:
    """Телефон: 9+ цифр, не похоже на диапазон лет вроде 2020-2025."""
    def search(self, text):
        for m in PHONE_RE.finditer(text):
            digits = re.sub(r"\D", "", m.group())
            if len(digits) >= 9 and not re.fullmatch(r"(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}", m.group().strip()):
                return m
        return None


PHONE = _Phone()
LINKEDIN = re.compile(r"linkedin\.com/in/[\w-]+", re.I)
GITHUB = re.compile(r"github\.com/[\w-]+", re.I)
ODD_CHARS = re.compile(r"[-�ﬀ-ﬆ]")  # private use, replacement, ligatures


def detect_columns(words, page_width):
    """Эвристика: если начала строк кучкуются в две разнесённые группы на большинстве высот — это колонки."""
    # Строка «двухколоночная», если в ней есть большой горизонтальный разрыв,
    # а справа от разрыва не короткая дата, а несколько слов. Колонка — если правые
    # части многих строк начинаются примерно с одной x-координаты.
    if not words:
        return False
    rows = {}
    for w in words:
        rows.setdefault(round(w["top"] / 3), []).append(w)
    starts = []
    multi = 0
    for ws in rows.values():
        ws = sorted(ws, key=lambda w: w["x0"])
        if len(ws) < 2:
            continue
        multi += 1
        for a, b in zip(ws, ws[1:]):
            if b["x0"] - a["x1"] > page_width * 0.08 and b["x0"] > page_width * 0.3:
                right = [w for w in ws if w["x0"] >= b["x0"]]
                if len(right) >= 3:
                    starts.append(round(b["x0"] / 10))
                break
    if multi < 10 or len(starts) < 8:
        return False
    common = max(set(starts), key=starts.count)
    aligned = sum(1 for s in starts if abs(s - common) <= 1)
    return aligned >= 8 and aligned / multi > 0.25


def check_pdf(path):
    try:
        import pdfplumber
    except ImportError:
        sys.exit("Нужен pdfplumber: pip install pdfplumber")
    issues, info = [], {}
    texts = []
    with pdfplumber.open(path) as pdf:
        info["pages"] = len(pdf.pages)
        images = tables = 0
        columns_pages = []
        fonts = set()
        header_footer_contact = False
        for i, page in enumerate(pdf.pages, 1):
            t = page.extract_text() or ""
            texts.append(t)
            images += len(page.images)
            try:
                tables += len(page.find_tables())
            except Exception:
                pass
            words = page.extract_words(extra_attrs=["fontname", "size"])
            fonts.update(w.get("fontname", "") for w in words)
            if detect_columns(words, page.width):
                columns_pages.append(i)
            top = [w["text"] for w in words if w["top"] < page.height * 0.06]
            bottom = [w["text"] for w in words if w["bottom"] > page.height * 0.94]
            if EMAIL.search(" ".join(top + bottom)) or PHONE.search(" ".join(top + bottom)):
                header_footer_contact = True
        text = "\n".join(texts)
        info.update(images=images, tables=tables, fonts=len({f.split("+")[-1] for f in fonts if f}),
                    chars=len(text), columns_on_pages=columns_pages)

        if len(text.strip()) < 200:
            issues.append(("❌", "Текст почти не извлекается — вероятно, CV сохранён картинкой или сканом. ATS его не прочитает. Экспортируйте из редактора как текстовый PDF."))
        elif info["pages"] and len(text) / info["pages"] < 600:
            issues.append(("⚠️", "Мало текста на страницу — часть содержимого может быть в картинках или фигурах."))
        if columns_pages:
            issues.append(("⚠️", f"Похоже на многоколоночную вёрстку (стр. {', '.join(map(str, columns_pages))}). Часть ATS читает колонки построчно и перемешивает текст — сверьте извлечённый текст ниже."))
        if tables:
            issues.append(("⚠️", f"Найдено таблиц: {tables}. Таблицы часто разбираются неверно; лучше обычный текст со списками."))
        if images:
            issues.append(("⚠️", f"Найдено изображений: {images}. Иконки, шкалы навыков и логотипы ATS не читает — важный текст не должен быть в картинках."))
        if header_footer_contact:
            issues.append(("⚠️", "Контакты стоят в колонтитуле. Некоторые ATS колонтитулы пропускают — продублируйте контакты в основном тексте."))
        if info["fonts"] > 4:
            issues.append(("⚠️", f"Шрифтов: {info['fonts']}. Для читаемости хватит 1–2."))
        if info["pages"] > 2:
            issues.append(("⚠️", f"Страниц: {info['pages']}. Обычно достаточно 1–2."))
    return text, issues, info


def check_docx(path):
    try:
        import docx
    except ImportError:
        sys.exit("Нужен python-docx: pip install python-docx")
    d = docx.Document(str(path))
    issues, info = [], {}
    body = [p.text for p in d.paragraphs]
    tables = len(d.tables)
    for t in d.tables:
        for row in t.rows:
            body.append(" | ".join(c.text for c in row.cells))
    hf = []
    for s in d.sections:
        hf += [p.text for p in s.header.paragraphs] + [p.text for p in s.footer.paragraphs]
    xml = d.element.xml
    textboxes = xml.count("<w:txbxContent")
    images = xml.count("<pic:pic") + xml.count("<v:imagedata")
    text = "\n".join(body)
    info.update(tables=tables, textboxes=textboxes, images=images, chars=len(text))
    if tables:
        issues.append(("⚠️", f"Таблиц: {tables}. Если вёрстка держится на таблице, ATS может перемешать порядок."))
    if textboxes:
        issues.append(("❌", f"Текстовых полей (text box): {textboxes}. Их содержимое многие ATS не видят вообще — перенесите текст в обычные абзацы."))
    if images:
        issues.append(("⚠️", f"Изображений: {images}. Важная информация не должна быть в картинках."))
    hf_text = " ".join(hf)
    if EMAIL.search(hf_text) or PHONE.search(hf_text):
        issues.append(("⚠️", "Контакты стоят в колонтитуле — продублируйте их в основном тексте."))
    return text, issues, info


def common_checks(text, issues):
    low = text.lower()
    found_sections = {k: any(re.search(r"(^|\n)\s*" + re.escape(h) + r"\s*[:\n]", low) for h in hs)
                      for k, hs in SECTION_HEADERS.items()}
    for k in ("experience", "skills", "education"):
        if not found_sections[k]:
            issues.append(("⚠️", f"Не найден стандартный заголовок раздела «{k}». ATS ищут разделы по привычным названиям (Experience / Опыт работы, Skills / Навыки, Education / Образование)."))
    contacts = {"email": bool(EMAIL.search(text)), "phone": bool(PHONE.search(text)),
                "linkedin": bool(LINKEDIN.search(text)), "github": bool(GITHUB.search(text))}
    if not contacts["email"]:
        issues.append(("❌", "В тексте не найден email."))
    if not contacts["phone"]:
        issues.append(("⚠️", "В тексте не найден телефон."))
    if not contacts["linkedin"]:
        issues.append(("⚠️", "Нет ссылки на LinkedIn в виде текста (linkedin.com/in/...)."))
    odd = len(ODD_CHARS.findall(text))
    if odd:
        issues.append(("⚠️", f"Символов, которые парсер не распознал (иконки, лигатуры): {odd}. Проверьте, не пропали ли буквы в словах."))
    dates = re.findall(r"(?:19|20)\d{2}", text)
    if len(dates) < 2:
        issues.append(("⚠️", "Почти нет дат. ATS и рекрутеры считают стаж по датам — укажите месяц и год для каждой роли."))
    return found_sections, contacts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cv")
    ap.add_argument("--dump", help="куда сохранить извлечённый текст")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    p = Path(args.cv)
    if p.suffix.lower() == ".pdf":
        text, issues, info = check_pdf(p)
    elif p.suffix.lower() == ".docx":
        text, issues, info = check_docx(p)
    else:
        sys.exit("Поддерживаются .pdf и .docx")
    sections, contacts = common_checks(text, issues)
    if args.dump:
        Path(args.dump).write_text(text, encoding="utf-8")

    if args.json:
        print(json.dumps({"info": info, "sections": sections, "contacts": contacts,
                          "issues": [{"level": l, "text": t} for l, t in issues],
                          "extracted_text": text}, ensure_ascii=False, indent=2))
        return

    print("# Проверка CV на ATS\n")
    print("**Файл:** " + p.name + "  ")
    print("**Сводка:** " + ", ".join(f"{k}: {v}" for k, v in info.items()) + "\n")
    print("**Контакты:** " + ", ".join(f"{k} {'✅' if v else '❌'}" for k, v in contacts.items()))
    print("**Разделы:** " + ", ".join(f"{k} {'✅' if v else '❌'}" for k, v in sections.items()) + "\n")
    if issues:
        print("## Проблемы\n")
        for level, t in issues:
            print(f"- {level} {t}")
    else:
        print("✅ Явных проблем для ATS не найдено.")
    print("\n## Как ATS видит текст (первые 1500 символов)\n")
    print("```\n" + text[:1500] + ("\n…" if len(text) > 1500 else "") + "\n```")


if __name__ == "__main__":
    main()
