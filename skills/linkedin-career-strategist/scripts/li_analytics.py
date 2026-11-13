#!/usr/bin/env python3
"""Разбор выгрузок аналитики LinkedIn (.xlsx): таблица по постам, итоги периода и кто смотрит.

Использование:
  python li_analytics.py EXPORT.xlsx [EXPORT2.xlsx ...] [--as-of YYYY-MM-DD] [--json]

Понимает два вида выгрузок:
  - общую (аналитика → «Контент» → Export): листы с итогами периода, по дням, по постам, подписчиками
    и демографией;
  - по одному посту (аналитика поста → Export): пары «показатель — значение» и демография зрителей.
Несколько файлов можно передать сразу: один и тот же пост в разных выгрузках покажет рост.

Листы и колонки ищутся по заголовкам, а не по позиции. Названия сверены с русской выгрузкой (ноябрь 2026);
английские синонимы — по документации и не сверены с реальным файлом. Формат выгрузки LinkedIn меняется:
если нужные колонки не найдены, скрипт печатает, что увидел, и завершается с ошибкой, а не угадывает.

--as-of — дата выгрузки (по умолчанию сегодня): от неё считается возраст поста. Сравнивать посты имеет смысл
только в одинаковом возрасте.
Нужен openpyxl: pip install openpyxl
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

# Синонимы заголовков: нормализованный текст (нижний регистр, без лишних пробелов) -> поле.
POST_COLUMNS = {
    "url": ["url-адрес публикации", "post url"],
    "date": ["дата размещения публикации", "дата размещения", "post publish date", "post date"],
    "time": ["время размещения публикации", "post publish time"],
    "type": ["тип публикации", "post type"],
    "impressions": ["показы", "impressions"],
    "impr_in": ["показы (в сети контактов)", "impressions (in network)"],
    "impr_out": ["показы (за пределами сети контактов)", "impressions (out of network)"],
    "reach": ["охваченные участники", "members reached"],
    "views": ["просмотры", "просмотры видео", "video views", "views"],
    "watch": ["время просмотра", "watch time"],
    "avg_watch": ["средн. время просмотра", "среднее время просмотра", "average watch time"],
    "followers": ["новые отслеживающие", "отслеживающие, полученные из этой публикации",
                  "new followers", "followers gained from this post"],
    "profile": ["просмотревшие профиль участники", "участники, просмотревшие ваш профиль из этой публикации",
                "profile viewers", "profile viewers from this post"],
    "reactions": ["реакции", "reactions"],
    "comments": ["комментарии", "comments"],
    "reposts": ["репосты", "reposts"],
    "saves": ["сохранения", "saves"],
    "sends": ["отправки", "отправки в linkedin", "sends", "sends on linkedin"],
    "link_clicks": ["переходы по ссылкам", "взаимодействия со ссылками", "link clicks", "link engagements"],
    "premium_button": ["взаимодействия с настраиваемой кнопкой", "взаимодействия с настраиваемой кнопкой premium",
                       "premium custom button interactions"],
}
SYN = {s: field for field, syns in POST_COLUMNS.items() for s in syns}
ENGAGEMENT_FIELDS = ("reactions", "comments", "reposts", "saves", "sends")

DEMO_HEADERS = {"основные демографические данные", "категория", "top demographics", "category"}
DEMO_CATEGORIES = {
    "job_title": ["должность", "job title"],
    "seniority": ["должностной уровень", "seniority"],
    "industry": ["отрасль", "industry"],
    "location": ["регион", "location"],
    "company": ["компания", "company"],
    "company_size": ["размер компании", "company size"],
}
DEMO_SYN = {s: k for k, syns in DEMO_CATEGORIES.items() for s in syns}

# Кто считается рекрутером или HR — по должности и отрасли. Регулярки на RU и EN.
RECRUITER_TITLE = re.compile(r"найм|подбор|рекрут|recruit|talent acquisition|sourc", re.IGNORECASE)
HR_TITLE = re.compile(r"кадр|\bhr\b|human resources|people partner|people operations", re.IGNORECASE)
RECRUITING_INDUSTRY = re.compile(r"подбор персонала|кадров|staffing|recruit|human resources", re.IGNORECASE)


def norm(v):
    return re.sub(r"\s+", " ", str(v)).strip().lower() if v is not None else ""


def num(v):
    """Число из ячейки: 227, '227', '1 160', '48 %'. Пусто -> None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).replace(" ", " ").replace(" ", "").replace("%", "").replace(",", ".")
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return None


def pct(v):
    """Доля в процентах: '48 %' -> 48.0, '< 1 проц.' / '<1%' -> 0.5 (помечается как «<1»)."""
    if v is None or v == "":
        return None
    s = norm(v)
    if s.startswith("<"):
        return 0.5
    m = re.search(r"[\d.,]+", s)
    if not m:
        return None
    x = float(m.group(0).replace(",", "."))
    # openpyxl отдаёт процентные ячейки долей (0.48), текстовые — строкой «48 %»
    return x * 100 if isinstance(v, float) and x <= 1 and "%" not in str(v) else x


def seconds(v):
    """'15 мин. 23 сек.' / '1 ч. 8 мин.' / '10 сек.' / '1h 8m' -> секунды."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return v
    s = norm(v)
    total, matched = 0, False
    for amount, unit in re.findall(r"(\d+)\s*(ч|h|мин|m|сек|с|s)\b\.?", s):
        matched = True
        total += int(amount) * {"ч": 3600, "h": 3600, "мин": 60, "m": 60}.get(unit, 1)
    return total if matched else None


def parse_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = norm(v)
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)  # формат английской выгрузки не сверен: считаем M/D/Y
    if m:
        return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def post_id(url):
    m = re.search(r"(?:ugcPost|activity|share)[-:](\d{10,})", url or "")
    return m.group(1) if m else (url or "")


def load_rows(path):
    try:
        import openpyxl
    except ImportError:
        sys.exit("Нужен openpyxl: pip install openpyxl")
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # выгрузки LinkedIn без стилей: openpyxl предупреждает
        wb = openpyxl.load_workbook(path, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c not in (None, "") for c in r)]
        sheets.append((ws.title, rows))
    return sheets


def post_from_row(header_fields, row):
    post = {}
    for idx, field in header_fields.items():
        post[field] = row[idx] if idx < len(row) else None
    return post


def find_posts_table(rows):
    """Таблица постов: строка-заголовок, где есть URL и показы; дальше строки со ссылками."""
    for i, row in enumerate(rows):
        fields = {j: SYN[norm(c)] for j, c in enumerate(row) if norm(c) in SYN}
        values = list(fields.values())
        # «Популярные публикации» — две таблицы рядом (URL | дата | взаимодействия || URL | дата | показы):
        # повтор колонок означает, что это не таблица постов с полным набором метрик.
        if len(values) != len(set(values)):
            continue
        if {"url", "impressions", "reactions"} <= set(values):
            unknown = [str(c) for j, c in enumerate(row) if c not in (None, "") and j not in fields]
            posts = []
            for r in rows[i + 1:]:
                cells = [c for c in r]
                url_idx = next(j for j, f in fields.items() if f == "url")
                if url_idx < len(cells) and "linkedin.com" in str(cells[url_idx] or ""):
                    posts.append(post_from_row(fields, cells))
                elif posts:
                    break
            return posts, unknown
    return None, None


def find_single_post(rows):
    """Выгрузка одного поста: пары «показатель | значение» в первых двух колонках."""
    kv = {}
    for r in rows:
        key = norm(r[0]) if r else ""
        if key in SYN and len(r) > 1:
            kv.setdefault(SYN[key], r[1])
    if "url" in kv and "impressions" in kv:
        return kv
    return None


def find_demographics(rows):
    out = {}
    started = False
    for r in rows:
        first = norm(r[0]) if r else ""
        if first in DEMO_HEADERS:
            started = True
            continue
        if started and first in DEMO_SYN and len(r) >= 3:
            out.setdefault(DEMO_SYN[first], []).append({"value": str(r[1]), "pct": pct(r[2]),
                                                          "raw": str(r[2]).strip()})
    return out


def find_period(rows):
    """Итоги периода (общая выгрузка): строка с диапазоном дат, показы, охват."""
    res = {}
    for r in rows:
        key = norm(r[0]) if r else ""
        val = r[1] if len(r) > 1 else None
        if val is not None and re.search(r"\d{2}\.\d{2}\.\d{4}\s*[–-]\s*\d{2}\.\d{2}\.\d{4}|\d+/\d+/\d{4}\s*[–-]", str(val)):
            res["period"] = str(val).strip()
        elif key in SYN and SYN[key] in ("impressions", "reach"):
            res[SYN[key]] = num(val)
    # Без диапазона дат это не итоги периода (у выгрузки одного поста те же «Показы»).
    return res if "period" in res and "impressions" in res else None


def find_daily(rows):
    """По дням: заголовок «Дата | Показы | Взаимодействия»."""
    for i, r in enumerate(rows):
        hdr = [norm(c) for c in r]
        if hdr and hdr[0] in ("дата", "date") and len(hdr) >= 3 and hdr[1] in SYN and SYN[hdr[1]] == "impressions":
            days = []
            for rr in rows[i + 1:]:
                d = parse_date(rr[0])
                if not d:
                    break
                days.append({"date": d.isoformat(), "impressions": num(rr[1]), "engagements": num(rr[2])})
            return days
    return None


def find_followers(rows):
    """Подписчики: «Общее количество отслеживающих на DATE | N» и новые по дням."""
    total, new = None, []
    for i, r in enumerate(rows):
        key = norm(r[0]) if r else ""
        if key.startswith(("общее количество отслеживающих", "total followers")):
            total = num(r[1]) if len(r) > 1 else None
        d = parse_date(r[0]) if r else None
        if d and len(r) > 1 and num(r[1]) is not None and (len(r) == 2 or all(c in (None, "") for c in r[2:])):
            new.append({"date": d.isoformat(), "new": num(r[1])})
    return {"total": total, "new": new} if total is not None else None


def demo_kind(sheet_title, file_kind):
    t = norm(sheet_title)
    if file_kind == "single":
        return "viewers"
    if "аудитор" in t or "audience" in t or "follower" in t:
        return "followers"
    if "контент" in t or "content" in t:
        return "viewers"
    return "unknown:" + sheet_title


def summarize_demo(demo):
    def share(rows, rx):
        hits = [r for r in rows if rx.search(r["value"])]
        return round(sum(r["pct"] or 0 for r in hits), 1), [f"{r['value']} {r['raw']}" for r in hits]
    titles = demo.get("job_title", [])
    rec, rec_rows = share(titles, RECRUITER_TITLE)
    hr, hr_rows = share(titles, HR_TITLE)
    ind, ind_rows = share(demo.get("industry", []), RECRUITING_INDUSTRY)
    top = {k: [f"{r['value']} {r['raw']}" for r in demo.get(k, [])[:3]] for k in ("job_title", "location", "industry")}
    return {"has_job_titles": bool(titles), "recruiters_by_title_pct": rec, "recruiter_titles": rec_rows,
            "hr_by_title_pct": hr, "hr_titles": hr_rows, "recruiting_industry_pct": ind,
            "recruiting_industries": ind_rows, "top": top}


def period_end(period):
    """Последняя дата диапазона «06.11.2026 – 12.11.2026» — обычно это и есть дата выгрузки."""
    dates = re.findall(r"\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}/\d{1,2}/\d{4}", period or "")
    return parse_date(dates[-1]) if dates else None


def analyze_file(path, as_of=None, fallback=None):
    """as_of — явная дата выгрузки (FILE@YYYY-MM-DD); иначе конец периода из файла; иначе --as-of/сегодня."""
    sheets = load_rows(path)
    out = {"file": Path(path).name, "kind": None, "posts": [], "period": None, "daily": None,
           "followers": None, "demographics": {}, "unknown_columns": []}
    for title, rows in sheets:
        posts, unknown = find_posts_table(rows)
        if posts is not None:
            out["kind"] = "aggregate"
            out["posts"].extend(posts)
            out["unknown_columns"].extend(unknown)
            continue
        single = find_single_post(rows)
        if single:
            out["kind"] = out["kind"] or "single"
            out["posts"].append(single)
        for finder, key in ((find_period, "period"), (find_daily, "daily"), (find_followers, "followers")):
            if out[key] is None:
                res = finder(rows)
                if res:
                    out[key] = res
    for title, rows in sheets:
        demo = find_demographics(rows)
        if demo:
            out["demographics"][demo_kind(title, out["kind"])] = summarize_demo(demo)

    if not out["posts"]:
        lines = [f"Не нашёл таблицу постов в {path}. Что в файле:"]
        for title, rows in sheets:
            lines.append(f"  лист «{title}»: " + " | ".join(str(c) for c in (rows[0] if rows else []) if c is not None))
        lines.append("Формат выгрузки, видимо, изменился: добавь заголовки в POST_COLUMNS, не угадывай.")
        sys.exit("\n".join(lines))

    end = period_end(out["period"]["period"]) if out["period"] else None
    if as_of:
        out["as_of"], out["as_of_source"] = as_of, "указана для файла"
    elif end:
        out["as_of"], out["as_of_source"] = end, "конец периода в файле"
    else:
        out["as_of"], out["as_of_source"] = fallback, "--as-of или сегодня"
    as_of = out["as_of"]

    for p in out["posts"]:
        d = parse_date(p.get("date"))
        p["date"] = d.isoformat() if d else None
        p["age_days"] = (as_of - d).days if d else None
        for f in ("impressions", "reach", "views", "followers", "profile", "link_clicks") + ENGAGEMENT_FIELDS:
            p[f] = num(p.get(f))
        p["impr_out_pct"] = pct(p.get("impr_out"))
        p["avg_watch_s"] = seconds(p.get("avg_watch"))
        p["id"] = post_id(p.get("url"))
        imp = p["impressions"] or 0
        eng = sum(p[f] or 0 for f in ENGAGEMENT_FIELDS)
        p["engagement_pct"] = round(100 * eng / imp, 1) if imp else None
        p["profile_per_1k"] = round(1000 * (p["profile"] or 0) / imp, 1) if imp else None
        p["source"] = out["file"]
    return out


def fmt1(v, suffix=""):
    """Доли и отношения — всегда с одним знаком: 7.0%, а не 7%."""
    return "—" if v is None else f"{v:.1f}{suffix}"


def fmt(v, suffix=""):
    if v is None:
        return "—"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{v}{suffix}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="FILE.xlsx или FILE.xlsx@YYYY-MM-DD (дата выгрузки этого файла)")
    ap.add_argument("--as-of", help="дата выгрузки по умолчанию, YYYY-MM-DD (иначе сегодня)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    fallback = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()

    results = []
    for arg in args.files:
        m = re.match(r"^(.*)@(\d{4}-\d{2}-\d{2})$", arg)
        path, explicit = (m.group(1), dt.date.fromisoformat(m.group(2))) if m else (arg, None)
        results.append(analyze_file(path, explicit, fallback))
    posts = sorted((p for r in results for p in r["posts"]),
                   key=lambda p: (p["date"] or "", p["id"], p["source"]))

    if args.json:
        print(json.dumps({"files": results}, ensure_ascii=False, indent=2, default=str))
        return

    print("# Аналитика LinkedIn\n")
    for r in results:
        period = f", период {r['period']['period']}" if r["period"] and r["period"].get("period") else ""
        kind = {"aggregate": "общая выгрузка", "single": "выгрузка одного поста"}.get(r["kind"], r["kind"])
        print(f"- {r['file']}: {kind}{period}; возраст постов — на {r['as_of'].isoformat()} ({r['as_of_source']})")
    print("\nСравнивай посты в одинаковом возрасте.\n")

    print("## Посты\n")
    print("| Опубликован | Возраст, дн | Показы | Вне сети | Охват | Просмотры профиля | На 1000 показов | "
          "Подписчики | Реакции | Комм. | Репосты | Сохр. | Отпр. | Вовлечённость | Ср. просмотр | Файл |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for p in posts:
        print(f"| {fmt(p['date'])} | {fmt(p['age_days'])} | {fmt(p['impressions'])} | {fmt(p['impr_out_pct'], '%')} | "
              f"{fmt(p['reach'])} | {fmt(p['profile'])} | {fmt1(p['profile_per_1k'])} | {fmt(p['followers'])} | "
              f"{fmt(p['reactions'])} | {fmt(p['comments'])} | {fmt(p['reposts'])} | {fmt(p['saves'])} | "
              f"{fmt(p['sends'])} | {fmt1(p['engagement_pct'], '%')} | {fmt(p['avg_watch_s'], ' с')} | {p['source']} |")
    print("\n_Вовлечённость = (реакции + комментарии + репосты + сохранения + отправки) / показы. "
          "«На 1000 показов» — просмотры профиля: главная метрика, если цель — рекрутеры._\n")

    for r in results:
        if r["period"] or r["daily"] or r["followers"]:
            print(f"## Период — {r['file']}\n")
            if r["period"]:
                print(f"- Показы: {fmt(r['period'].get('impressions'))}, охват: {fmt(r['period'].get('reach'))}")
            if r["daily"]:
                peak = max(r["daily"], key=lambda d: d["impressions"] or 0)
                print(f"- По дням: пик {peak['date']} — {fmt(peak['impressions'])} показов; "
                      + ", ".join(f"{d['date'][5:]}: {fmt(d['impressions'])}" for d in r["daily"]))
            if r["followers"]:
                new = sum(d["new"] or 0 for d in r["followers"]["new"])
                print(f"- Подписчики: всего {fmt(r['followers']['total'])}, новых за период {new}")
            print()

    any_demo = [(r["file"], k, v) for r in results for k, v in r["demographics"].items()]
    if any_demo:
        print("## Кто смотрит\n")
        print("| Файл | Чья демография | Рекрутеры (должность) | HR (должность) | Рекрутинг (отрасль) | "
              "Топ должностей | Топ регионов |")
        print("|---|---|---|---|---|---|---|")
        labels = {"followers": "подписчики", "viewers": "зрители постов"}
        for file, kind, s in any_demo:
            rec = fmt(s["recruiters_by_title_pct"], "%") if s["has_job_titles"] else "нет должностей в выгрузке"
            hr = fmt(s["hr_by_title_pct"], "%") if s["has_job_titles"] else "—"
            print(f"| {file} | {labels.get(kind, kind)} | {rec} | {hr} | {fmt(s['recruiting_industry_pct'], '%')} | "
                  f"{'; '.join(s['top']['job_title']) or '—'} | {'; '.join(s['top']['location']) or '—'} |")
        print("\n_В выгрузке только верхние строки каждой категории, поэтому доли — нижняя граница. "
              "«<1%» считается как 0,5%._\n")

    unknown = sorted({c for r in results for c in r["unknown_columns"]})
    if unknown:
        print("Колонки, которые скрипт не знает (не учтены): " + ", ".join(unknown))


if __name__ == "__main__":
    main()
