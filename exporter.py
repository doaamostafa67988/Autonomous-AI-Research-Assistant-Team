"""
exporter.py — Export the final report to Markdown or PDF.
"""

import re
from pathlib import Path

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors


def _strip_markdown(text: str) -> str:
    text = re.sub(r"#{1,6}\s*", "",       text)          # headings
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)         # bold
    text = re.sub(r"\*(.+?)\*",    r"\1", text)          # italic
    text = re.sub(r"`(.+?)`",      r"\1", text)          # code
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)      # links
    text = re.sub(r"<.+?>",        "",    text)           # html tags
    return text.strip()


class Exporter:
    def to_markdown(self, report: str, output_path: str | None = None) -> str:
        if output_path:
            Path(output_path).write_text(report, encoding="utf-8")
        return report

    def to_pdf(self, report: str, output_path: str = "report.pdf") -> str:
        styles = getSampleStyleSheet()

        h1_style = ParagraphStyle(
            "H1", parent=styles["Heading1"],
            textColor=colors.HexColor("#1a1a2e"), spaceAfter=8,
        )
        h2_style = ParagraphStyle(
            "H2", parent=styles["Heading2"],
            textColor=colors.HexColor("#1f3c88"), spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "Body", parent=styles["Normal"],
            leading=16, spaceAfter=4,
        )

        doc   = SimpleDocTemplate(
            output_path,
            rightMargin=inch, leftMargin=inch,
            topMargin=inch,   bottomMargin=inch,
        )
        story = []

        for line in report.split("\n"):
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 6))
                continue
            clean = _strip_markdown(stripped)
            if line.startswith("# "):
                story.append(Paragraph(clean, h1_style))
            elif line.startswith("## "):
                story.append(Paragraph(clean, h2_style))
            else:
                story.append(Paragraph(clean, body_style))

        doc.build(story)
        return output_path
