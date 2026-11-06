"""Общие функции: чтение текста из txt/md/pdf/docx."""
from pathlib import Path
import sys


def read_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        sys.exit(f"Файл не найден: {path}")
    suf = p.suffix.lower()
    if suf == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(p) as pdf:
                return "\n".join((page.extract_text() or "") for page in pdf.pages)
        except ImportError:
            try:
                from pypdf import PdfReader
                return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
            except ImportError:
                sys.exit("Нужен pdfplumber или pypdf: pip install pdfplumber")
    if suf == ".docx":
        try:
            import docx
        except ImportError:
            sys.exit("Нужен python-docx: pip install python-docx")
        d = docx.Document(str(p))
        parts = [para.text for para in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    return p.read_text(encoding="utf-8", errors="replace")


def references_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "references"
