# linkedin-career-strategist

Скилл для Claude: разбор CV и профиля LinkedIn, сверка с вакансией (включая право на работу и спонсорство визы), сопроводительные письма без шаблонных фраз, анализ компании, разбор аналитики постов LinkedIn и трекер откликов.

## Состав

```
SKILL.md                         инструкции и режимы работы
scripts/
  ats_check.py                   читаемость CV для ATS (PDF, DOCX)
  keyword_match.py               покрытие навыков вакансии в CV/профиле
  letter_check.py                проверка письма на шаблонность
  work_auth_check.py             право на работу, спонсорство, релокация, язык в вакансии
  li_analytics.py                разбор выгрузок аналитики LinkedIn (.xlsx)
  tracker.py                     трекер откликов в CSV
  _textio.py                     общее чтение txt/md/pdf/docx
references/
  skills_dictionary.txt          словарь навыков и синонимов (дополняйте)
  stop_phrases.txt               стоп-лист фраз EN/RU (дополняйте)
  letter_templates.md            каркасы писем и сообщений
```

## Зависимости

Python 3.9+, `pdfplumber` (или `pypdf`) и `python-docx`; для `li_analytics.py` — `openpyxl`:

```
pip install pdfplumber python-docx openpyxl
```

## Примеры

```
python3 scripts/ats_check.py cv.pdf --dump cv_as_ats_sees.txt
python3 scripts/keyword_match.py vacancy.txt cv.pdf linkedin_profile.pdf
python3 scripts/letter_check.py letter.txt --type email --company Acme --vacancy vacancy.txt
python3 scripts/work_auth_check.py vacancy.txt
python3 scripts/li_analytics.py AggregateAnalytics.xlsx SinglePostAnalytics.xlsx@2026-11-12
python3 scripts/tracker.py --file ~/job_tracker.csv add --company Acme --role "Senior Backend" --channel referral
python3 scripts/tracker.py --file ~/job_tracker.csv due
```

Скрипты работают локально и ничего не отправляют в сеть.
