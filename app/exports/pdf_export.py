from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.assessment import summary
from app.services.photos import report_image


PHOTO_MAX_WIDTH = 3.3 * inch
PHOTO_MAX_HEIGHT = 2.6 * inch
NOTICE ="Decision support only. This report does not certify a building, replace licensed professional judgment, or prescribe a retrofit."


def pdf_text(value: object) -> str:
    text = str(value or "")
    replacements = {"\u2013": "-", "\u2014": "-", "\u2011": "-", "\u00a0": " ", "": "'", "²": "2", "³": "3"}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return escape(text)


def photo_cell(upload_root: Path | None, evidence, style) -> list:
    caption = Paragraph(pdf_text(evidence.caption or evidence.original_name), style)
    path = upload_root / str(evidence.assessment_id) / evidence.stored_name if upload_root else None
    try:
        data, width, height = report_image(path)
    except (OSError, TypeError, ValueError):
        return [Paragraph(pdf_text(f"[Photo unavailable: {evidence.original_name}]"), style), caption]
    scale = min(PHOTO_MAX_WIDTH / width, PHOTO_MAX_HEIGHT / height)
    return [Image(data, width=width * scale, height=height * scale), caption]


def photo_table(upload_root: Path | None, photos: list, style) -> Table | None:
    if not photos:
        return None
    cells = [photo_cell(upload_root, evidence, style) for evidence in photos]
    rows = [cells[index:index + 2] for index in range(0, len(cells), 2)]
    if len(rows[-1]) == 1:
        rows[-1].append("")
    return Table(rows, colWidths=[PHOTO_MAX_WIDTH + 0.2 * inch] * 2, hAlign="LEFT", style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))


def make_pdf(catalog: dict, assessment, upload_root: Path | None = None) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.5 * inch, leftMargin=0.5 * inch, topMargin=0.5 * inch, bottomMargin=0.55 * inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontSize=22, leading=27, textColor=colors.HexColor("#123a4a"), alignment=TA_CENTER, spaceAfter=14))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Heading2"], fontSize=13, leading=16, textColor=colors.HexColor("#123a4a"), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8.5, leading=11))
    styles.add(ParagraphStyle(name="Item", parent=styles["BodyText"], fontSize=8.5, leading=11))
    story = []
    story.append(Spacer(1, 0.7 * inch))
    story.append(Paragraph("MORGAN", styles["CoverTitle"]))
    story.append(Paragraph("ASCE 41-23 Tier 1 Assessment Package", styles["Title"]))
    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph(pdf_text(NOTICE), styles["BodyText"]))
    story.append(Spacer(1, 0.25 * inch))
    overview = [
        ["Project", pdf_text(assessment.project_name) or "-"],
        ["Building", pdf_text(assessment.building_name) or "-"],
        ["Project number", pdf_text(assessment.project_number) or "-"],
        ["Performance objective", pdf_text(assessment.performance_level) or "-"],
        ["Building type", pdf_text(assessment.building_type) or "-"],
        ["Seismicity", pdf_text(assessment.seismicity) or "-"],
        ["Status", pdf_text(assessment.status)],
    ]
    story.append(Table(overview, colWidths=[1.55 * inch, 5.2 * inch], style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b6c7cd")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef5f6")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ])))
    story.append(PageBreak())
    rollup = summary(catalog, assessment)
    counters = rollup["counters"]
    story.append(Paragraph("Assessment summary", styles["SectionTitle"]))
    summary_rows = [["Total", "Reviewed", "Compliant", "Noncompliant", "Unknown", "N/A", "Incomplete"], [str(counters["total"]), str(counters["reviewed"]), str(counters["C"]), str(counters["NC"]), str(counters["U"]), str(counters["N/A"]), str(counters["incomplete"])]]
    story.append(Table(summary_rows, colWidths=[0.95 * inch] * 7, style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b6c7cd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123a4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ])))
    if counters["incomplete"] or counters["NC"] or counters["U"]:
        story.append(Spacer(1, 0.14 * inch))
        story.append(Paragraph(pdf_text(f"Warning: {counters['incomplete']} incomplete, {counters['NC']} noncompliant, and {counters['U']} unknown items require attention."), styles["BodyText"]))
    if assessment.reviewer_notes:
        story.append(Paragraph("Reviewer notes", styles["SectionTitle"]))
        story.append(Paragraph(pdf_text(assessment.reviewer_notes), styles["BodyText"]))
    for form in sorted({row["form"]["form_id"]: row["form"] for row in rollup["rows"]}.values(), key=lambda item: item["form_id"]):
        story.append(PageBreak())
        story.append(Paragraph(pdf_text(form["title"]), styles["SectionTitle"]))
        rows_for_form = [row for row in rollup["rows"] if row["form"]["form_id"] == form["form_id"]]
        current_section = None
        for row in rows_for_form:
            if current_section != row["section"]["section_id"]:
                current_section = row["section"]["section_id"]
                story.append(Paragraph(pdf_text(row["section"]["title"]), styles["Heading3"]))
            response = row["response"]
            status = response.status if response and response.status else "-"
            body = f"<b>{pdf_text(status)} | {pdf_text(row['item']['statement'])}</b><br/>Tier 2: {pdf_text(row['item']['tier2_reference']) or '-'} &nbsp; Commentary: {pdf_text(row['item']['commentary_reference']) or '-'}"
            if response and response.comment:
                body += f"<br/><b>Comment:</b> {pdf_text(response.comment)}"
            if row["evidence"]:
                body += "<br/><b>Evidence:</b> " + ", ".join(pdf_text(e.original_name) for e in row["evidence"])
            story.append(Paragraph(body, styles["Item"]))
            photos = photo_table(upload_root, [e for e in row["evidence"] if e.is_image and e.include_in_report], styles["Small"])
            if photos is not None:
                story.append(Spacer(1, 0.05 * inch))
                story.append(photos)
            story.append(Spacer(1, 0.07 * inch))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#5b6b70"))
        canvas.drawString(0.5 * inch, 0.3 * inch, "MORGAN - decision support only")
        canvas.drawRightString(7.9 * inch, 0.3 * inch, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
