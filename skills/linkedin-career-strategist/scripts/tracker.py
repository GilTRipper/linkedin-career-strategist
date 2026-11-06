#!/usr/bin/env python3
"""Трекер откликов в CSV.

Использование:
  python tracker.py [--file job_tracker.csv] add --company X --role Y [--url U] [--channel C]
                    [--contact P] [--status S] [--next-step T] [--next-date YYYY-MM-DD] [--notes N]
  python tracker.py [--file ...] update ID [--status S] [--next-step T] [--next-date D] [--contact P] [--notes N]
  python tracker.py [--file ...] list [--status S] [--active]
  python tracker.py [--file ...] due [--days 0]      # что пора сделать (next_date наступила)
  python tracker.py [--file ...] stats

Статусы: target, contacted, referral, applied, screening, interview, offer, rejected, ghosted, withdrawn.
Каналы: referral, hiring_manager, recruiter, direct_apply, inbound.
Файл по умолчанию: ./job_tracker.csv (создаётся при первом add). Храните его в своей папке,
а не внутри папки скилла.
"""
import argparse
import csv
import datetime as dt
import sys
from collections import Counter
from pathlib import Path

FIELDS = ["id", "company", "role", "url", "channel", "contact", "status", "created",
          "last_update", "next_step", "next_date", "notes"]
STATUSES = ["target", "contacted", "referral", "applied", "screening", "interview",
            "offer", "rejected", "ghosted", "withdrawn"]
CLOSED = {"offer", "rejected", "ghosted", "withdrawn"}
CHANNELS = ["referral", "hiring_manager", "recruiter", "direct_apply", "inbound"]


def today():
    return dt.date.today().isoformat()


def load(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save(path, rows):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    tmp.replace(path)


def check_date(s):
    if s:
        try:
            dt.date.fromisoformat(s)
        except ValueError:
            sys.exit(f"Дата должна быть в формате YYYY-MM-DD: {s}")
    return s


def table(rows, cols=("id", "company", "role", "channel", "status", "next_step", "next_date")):
    if not rows:
        print("Пусто.")
        return
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for r in rows:
        print("| " + " | ".join((r.get(c) or "").replace("|", "/") for c in cols) + " |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="job_tracker.csv")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("--company", required=True)
    a.add_argument("--role", required=True)
    for k in ("url", "contact", "next-step", "notes"):
        a.add_argument("--" + k, default="")
    a.add_argument("--channel", choices=CHANNELS, default="direct_apply")
    a.add_argument("--status", choices=STATUSES, default="target")
    a.add_argument("--next-date", default="")

    u = sub.add_parser("update")
    u.add_argument("id")
    u.add_argument("--status", choices=STATUSES)
    u.add_argument("--channel", choices=CHANNELS)
    for k in ("next-step", "next-date", "contact", "url", "notes"):
        u.add_argument("--" + k)
    u.add_argument("--append-note", help="дописать заметку с датой, не стирая старые")

    l = sub.add_parser("list")
    l.add_argument("--status", choices=STATUSES)
    l.add_argument("--active", action="store_true", help="только незакрытые")

    d = sub.add_parser("due")
    d.add_argument("--days", type=int, default=0, help="показать то, что наступит в ближайшие N дней")

    sub.add_parser("stats")
    args = ap.parse_args()

    path = Path(args.file)
    rows = load(path)

    if args.cmd == "add":
        new_id = str(max([int(r["id"]) for r in rows if r.get("id", "").isdigit()] or [0]) + 1)
        r = {"id": new_id, "company": args.company, "role": args.role, "url": args.url,
             "channel": args.channel, "contact": args.contact, "status": args.status,
             "created": today(), "last_update": today(), "next_step": args.next_step,
             "next_date": check_date(args.next_date), "notes": args.notes}
        rows.append(r)
        save(path, rows)
        print(f"Добавлено #{new_id}: {args.company} — {args.role} ({path})")

    elif args.cmd == "update":
        r = next((x for x in rows if x["id"] == args.id), None)
        if not r:
            sys.exit(f"Нет записи #{args.id}")
        for k in ("status", "channel", "contact", "url", "notes"):
            v = getattr(args, k)
            if v is not None:
                r[k] = v
        if args.next_step is not None:
            r["next_step"] = args.next_step
        if args.next_date is not None:
            r["next_date"] = check_date(args.next_date)
        if args.append_note:
            r["notes"] = (r.get("notes", "") + f" [{today()}] {args.append_note}").strip()
        if r["status"] in CLOSED and args.next_date is None:
            r["next_date"] = ""
        r["last_update"] = today()
        save(path, rows)
        print(f"Обновлено #{args.id}: {r['company']} — статус {r['status']}")

    elif args.cmd == "list":
        sel = rows
        if args.status:
            sel = [r for r in sel if r["status"] == args.status]
        if args.active:
            sel = [r for r in sel if r["status"] not in CLOSED]
        table(sel)

    elif args.cmd == "due":
        limit = (dt.date.today() + dt.timedelta(days=args.days)).isoformat()
        sel = [r for r in rows if r.get("next_date") and r["next_date"] <= limit and r["status"] not in CLOSED]
        stale = [r for r in rows if r["status"] in {"contacted", "applied", "screening"} and not r.get("next_date")
                 and r.get("last_update") and (dt.date.today() - dt.date.fromisoformat(r["last_update"])).days >= 7]
        print("## Пора сделать\n")
        table(sorted(sel, key=lambda r: r["next_date"]))
        if stale:
            print("\n## Без движения 7+ дней и без следующего шага\n")
            table(stale, ("id", "company", "role", "status", "last_update"))

    elif args.cmd == "stats":
        if not rows:
            print("Пусто.")
            return
        st = Counter(r["status"] for r in rows)
        ch = Counter(r["channel"] for r in rows)
        print(f"Всего: {len(rows)} · активных: {sum(1 for r in rows if r['status'] not in CLOSED)}\n")
        print("По статусам: " + ", ".join(f"{s} {st[s]}" for s in STATUSES if st[s]))
        print("По каналам: " + ", ".join(f"{c} {n}" for c, n in ch.most_common()))
        progressed = {"screening", "interview", "offer"}
        print("\nКонверсия в скрининг и дальше по каналам:")
        for c, n in ch.most_common():
            k = sum(1 for r in rows if r["channel"] == c and r["status"] in progressed)
            print(f"- {c}: {k}/{n} ({round(100 * k / n)}%)")


if __name__ == "__main__":
    main()
