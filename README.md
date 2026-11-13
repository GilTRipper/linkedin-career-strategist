# linkedin-career-strategist

Скилл для Claude: разбор CV и профиля LinkedIn под поиск рекрутеров, сверка с вакансией (включая право на работу и спонсорство визы), сопроводительные письма без шаблонных фраз, анализ компании, разбор аналитики постов LinkedIn и трекер откликов. Работает в Claude Code и в claude.ai.

## Что умеет

- **Разбор CV** — ATS-проверка PDF/DOCX, чек-лист рекрутера, правки «было → стало».
- **Разбор профиля LinkedIn** — заголовок, About, опыт, навыки, Open to Work.
- **Право на работу** — до сверки навыков: требования к стране проживания, спонсорство визы и релокация, местный язык, тип найма; если вакансия отсекает по стране — вердикт сразу.
- **Матчинг с вакансией** — покрытие навыков в процентах, матрица соответствия, вердикт «подаваться или нет».
- **Сопроводительные и сообщения** (LinkedIn, email, cover letter) с проверкой скриптом на шаблонность.
- **Досье на вакансию и компанию** — актуальность, детали вне объявления, риски, факты для письма.
- **Аналитика LinkedIn** — разбор выгрузок (общей и по посту): посты в одинаковом возрасте, просмотры профиля на 1000 показов, доля рекрутеров среди подписчиков и зрителей.
- **Поиск через рефералы** и трекер откликов: в системе пользователя или в CSV, если своей нет.

## Установка

### Claude Code — как плагин

```
/plugin marketplace add GilTRipper/linkedin-career-strategist
/plugin install linkedin-career-strategist@giltripper
```

### Claude Code — вручную

```
git clone https://github.com/GilTRipper/linkedin-career-strategist.git
cp -R linkedin-career-strategist/skills/linkedin-career-strategist ~/.claude/skills/
```

### claude.ai

Упакуйте папку скилла в zip и загрузите в настройках скиллов claude.ai:

```
cd skills && zip -r linkedin-career-strategist.zip linkedin-career-strategist
```

## Зависимости

Python 3.9+, `pdfplumber` (или `pypdf`) и `python-docx`; для разбора аналитики — `openpyxl`:

```
pip install pdfplumber python-docx openpyxl
```

Скрипты работают локально и ничего не отправляют в сеть.

## Состав

Скрипты, справочники и примеры запуска — в [skills/linkedin-career-strategist/README.md](skills/linkedin-career-strategist/README.md).

## Лицензия

[MIT](LICENSE)
