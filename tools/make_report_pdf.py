# tools/make_report_pdf.py
"""Сборка ОТЧЁТ.md в PDF в стиле референса (титул + колонтитул, таблицы).

Запуск: python tools/make_report_pdf.py  →  ОТЧЁТ.pdf в корне.
Шрифты: Arial (Windows), кириллица из коробки.
"""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, NextPageTemplate,
                                PageTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ОТЧЁТ.md"
OUT = ROOT / "ОТЧЁТ.pdf"

for name, path in [("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"),
                   ("Arial-Italic", "ariali.ttf"), ("Arial-BoldItalic", "arialbi.ttf")]:
    p = Path(r"C:/Windows/Fonts") / path
    if p.exists():
        pdfmetrics.registerFont(TTFont(name, str(p)))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold",
                              italic="Arial-Italic", boldItalic="Arial-BoldItalic")

NAVY = colors.HexColor("#1a2e4f")
ACCENT = colors.HexColor("#2f6fd0")
LIGHT = colors.HexColor("#eef2f8")
GRAY = colors.HexColor("#555555")

BODY = ParagraphStyle("body", fontName="Arial", fontSize=9.5, leading=13.5, spaceAfter=4)
H1 = ParagraphStyle("h1", fontName="Arial-Bold", fontSize=15, leading=19, textColor=NAVY,
                    spaceBefore=14, spaceAfter=6)
H2 = ParagraphStyle("h2", fontName="Arial-Bold", fontSize=12, leading=15, textColor=ACCENT,
                    spaceBefore=12, spaceAfter=4)
BOLD = ParagraphStyle("bold", parent=BODY, fontName="Arial-Bold")
LI = ParagraphStyle("li", parent=BODY, leftIndent=10, bulletIndent=2)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.5, leading=11.5, spaceAfter=0)
CELLH = ParagraphStyle("cellh", parent=CELL, fontName="Arial-Bold", textColor=colors.white)
TITLE = ParagraphStyle("title", fontName="Arial-Bold", fontSize=24, leading=29,
                       textColor=NAVY, alignment=TA_CENTER, spaceAfter=10)
SUBTITLE = ParagraphStyle("subtitle", fontName="Arial", fontSize=12, leading=17,
                          textColor=GRAY, alignment=TA_CENTER, spaceAfter=6)
META = ParagraphStyle("meta", parent=BODY, fontSize=9, textColor=GRAY)

FOOTER = "Деньги под защитой · Changellenge × ВТБ"


def esc(s: str) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r'<font face="Arial" color="#2f6fd0">\1</font>', s)
    return s


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 7.5)
    canvas.setFillColor(GRAY)
    canvas.drawString(18 * mm, 285 * mm, FOOTER.upper())
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, 283 * mm, 192 * mm, 283 * mm)
    canvas.drawRightString(192 * mm, 10 * mm, f"{FOOTER} · {doc.page}")
    canvas.restoreState()


def title_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 250 * mm, 210 * mm, 47 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Arial-Bold", 13)
    canvas.drawString(18 * mm, 278 * mm, "КЕЙС-ЧЕМПИОНАТ CHANGELLENGE × ВТБ · «ДЕНЬГИ ПОД ЗАЩИТОЙ»")
    canvas.setFont("Arial", 9.5)
    canvas.drawString(18 * mm, 269 * mm, "Многоуровневое противодействие мошенничеству в переводах СБП/ДБО")
    canvas.setFont("Arial", 8)
    canvas.setFillColor(GRAY)
    canvas.drawRightString(192 * mm, 10 * mm, f"{FOOTER} · {doc.page}")
    canvas.restoreState()


def md_table(lines: list[str]) -> Table:
    rows = [[Paragraph(esc(c.strip()), CELLH) for c in lines[0].strip("|").split("|")]]
    for ln in lines[2:]:
        rows.append([Paragraph(esc(c.strip()), CELL) for c in ln.strip("|").split("|")])
    ncols = len(rows[0])
    width = 174 * mm
    t = Table(rows, colWidths=[width / ncols] * ncols, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d2e0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build_story(md: str) -> list:
    story = []
    lines = md.splitlines()
    i, first_h1_done, in_title = 0, False, True
    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            story.append(md_table(tbl))
            story.append(Spacer(1, 5))
            continue
        if ln.startswith("# "):
            if first_h1_done:
                story.append(Paragraph(esc(ln[2:]), H1))
            else:
                story.append(Spacer(1, 75 * mm))
                story.append(Paragraph(esc(ln[2:]), TITLE))
                first_h1_done = True
            i += 1
            continue
        if ln.startswith("## "):
            story.append(Paragraph(esc(ln[3:]).upper(), H1))
            i += 1
            continue
        if ln.startswith("### "):
            story.append(Paragraph(esc(ln[4:]), H2))
            i += 1
            continue
        if ln.strip() == "---":
            in_title = False
            story.append(Spacer(1, 6))
            i += 1
            continue
        if ln.lstrip().startswith(("- ", "* ")):
            text = ln.lstrip()[2:]
            if in_title:
                story.append(Paragraph(esc(text), META))
            else:
                story.append(Paragraph("• " + esc(text), LI))
            i += 1
            continue
        if re.match(r"^\d+\.\s", ln.lstrip()):
            story.append(Paragraph(esc(ln.strip()), LI))
            i += 1
            continue
        if ln.startswith("**") and ln.endswith("**") and len(ln) > 4:
            if in_title:
                story.append(Paragraph(esc(ln.strip("*")), SUBTITLE))
            else:
                story.append(Paragraph(esc(ln), BOLD))
            i += 1
            continue
        story.append(Paragraph(esc(ln), BODY))
        i += 1
    return story


def main() -> None:
    doc = BaseDocTemplate(str(OUT), pagesize=A4,
                          leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=20 * mm, bottomMargin=16 * mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([
        PageTemplate(id="title", frames=[frame], onPage=title_footer),
        PageTemplate(id="main", frames=[frame], onPage=header_footer),
    ])
    story = build_story(SRC.read_text(encoding="utf-8"))
    cut = next(idx for idx, f in enumerate(story) if isinstance(f, Paragraph)
               and f.style is H1)
    story = [NextPageTemplate("main")] + story[:cut] + [PageBreak()] + story[cut:]
    doc.build(story)
    print("OK ->", OUT)


if __name__ == "__main__":
    main()
