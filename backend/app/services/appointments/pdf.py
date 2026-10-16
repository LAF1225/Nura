"""Rendering a stored snapshot as a PDF (PRD 7, sections 26, 33, 59 and 63).

The contract is narrow on purpose: **in, a snapshot dict; out, bytes.** No
database session, no request, no clock. A report generated last month
re-renders to the same document today, because there is nothing else for it to
depend on (section 72's determinism criterion).

``fpdf2`` does the typesetting. It is pure Python with no system libraries
behind it, which matters for a project developed on Windows and deployed on
Linux, and its output is byte-identical for identical input once the creation
date is pinned -- which this module pins to the snapshot's own
``generated_at``. So "regenerate the PDF for report v1" produces the file that
was already sent, not a new one that merely says the same thing.

**The design is printable, not themed** (section 59). Black text on white, one
accent colour for headings, no background fills and no images. The app renders
the same snapshot in Light or Dark for reading on a phone; a document that comes
out of a surgery printer should look like a document.

**Text and the standard fonts.** With no font configured, headings and body are
set in the PDF standard Helvetica, whose encoding covers Latin-1 only. Anything
outside it -- a name in Arabic or Devanagari, an em dash, a curly quote -- has to
be dealt with rather than crashing a report somebody is about to hand over, so
``sanitise`` folds the punctuation this codebase actually uses down to its ASCII
equivalent and replaces anything else it cannot draw. That is a real limitation
and the fix is one setting: point ``report_font_path`` at a TrueType font and
every glyph in it renders, with no code change.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: A4 in millimetres, with margins wide enough to survive a printer's own.
PAGE_FORMAT = "A4"
MARGIN = 18.0
BOTTOM_MARGIN = 26.0

#: Brand dark teal, from the PRD 0 palette. Used for the title and the section
#: headings and nowhere else: one accent is a design, two is decoration.
ACCENT = (28, 96, 92)
BODY = (17, 17, 17)
MUTED = (90, 90, 90)
RULE = (200, 206, 205)

TITLE_SIZE = 17.0
HEADING_SIZE = 10.5
PATIENT_SIZE = 11.5
BODY_SIZE = 9.6
FOOTER_SIZE = 7.0

LINE_HEIGHT = 4.6
ITEM_INDENT = 4.5
BULLET_SIZE = 1.25

#: Punctuation this codebase uses that the PDF standard fonts cannot draw. The
#: replacements are chosen so a sentence still reads correctly rather than
#: merely not crashing.
SUBSTITUTIONS = {
    "—": "-",  # em dash
    "–": "-",  # en dash
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    "•": "-",
    " ": " ",  # non-breaking space
    "‐": "-",
    "‑": "-",
}

#: Stands in for a character neither the substitutions nor the font can handle.
#: A visible marker rather than a silent deletion: a doctor seeing "?" in a name
#: knows something is missing, where a gap looks like the name itself.
REPLACEMENT = "?"

#: What PDF metadata says. Deliberately no patient name and nothing medical: a
#: file's properties are visible wherever the file is, and the user did not
#: choose to publish them (PRD 7, sections 33 and 35).
PDF_TITLE = "Nura Health Summary"
PDF_AUTHOR = "Nura"
PDF_PRODUCER = "Nura"


@dataclass(frozen=True)
class RenderedReport:
    """A finished document."""

    content: bytes
    page_count: int

    @property
    def byte_size(self) -> int:
        return len(self.content)


def sanitise(text: str, *, unicode_font: bool) -> str:
    """Text the chosen font can actually draw.

    With a Unicode font configured, only the substitutions are applied -- they
    are typographic tidying, and a real em dash would render fine. Without one,
    every remaining character outside Latin-1 becomes ``REPLACEMENT``.
    """
    for source, target in SUBSTITUTIONS.items():
        text = text.replace(source, target)
    if unicode_font:
        return text
    return "".join(
        character if _drawable(character) else REPLACEMENT for character in text
    )


def _drawable(character: str) -> bool:
    try:
        character.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return True


class _ReportDocument(FPDF):
    """An A4 document with Nura's footer on every page.

    The footer carries the disclaimer, not just the page number. A report gets
    printed, separated and put in a file, and a page that has drifted away from
    its first sheet still has to say what it is (PRD 7, section 45).
    """

    def __init__(self, footer_lines: list[str], *, unicode_font: bool) -> None:
        super().__init__(orientation="P", unit="mm", format=PAGE_FORMAT)
        self.footer_lines = footer_lines
        self.unicode_font = unicode_font
        self.body_font = "Helvetica"
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(True, margin=BOTTOM_MARGIN)

    # `footer` is fpdf2's own hook name, called once per page.
    def footer(self) -> None:
        self.set_y(-BOTTOM_MARGIN + 6)
        self.set_draw_color(*RULE)
        self.set_line_width(0.2)
        self.line(MARGIN, self.get_y(), self.w - MARGIN, self.get_y())
        self.ln(1.6)

        self.set_font(self.body_font, "", FOOTER_SIZE)
        self.set_text_color(*MUTED)
        for line in self.footer_lines:
            self.multi_cell(0, 3.1, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        self.set_font(self.body_font, "", FOOTER_SIZE)
        self.cell(0, 3.1, f"Page {self.page_no()}", align="R")


class PdfReportService:
    """Snapshot in, document out (PRD 7, section 63).

    A class rather than a function only because it holds the font decision, which
    every draw call needs. It has no other state, reads nothing, and writes
    nothing: storing the result is ``reports.py``'s job.
    """

    def __init__(self, font_path: Path | None = None) -> None:
        self.font_path = font_path
        self.unicode_font = font_path is not None and font_path.is_file()
        if font_path is not None and not self.unicode_font:
            # Said once, plainly. A missing font file must not stop a report
            # being generated; it only limits which characters it can show.
            logger.warning(
                "reports: the configured PDF font could not be found; "
                "falling back to the standard fonts"
            )

    # --- text helpers -------------------------------------------------------

    def _clean(self, text: str) -> str:
        return sanitise(text, unicode_font=self.unicode_font)

    def _register_fonts(self, pdf: _ReportDocument) -> None:
        """Embeds the configured font, if there is one.

        A sibling file named ``<stem>-Bold<suffix>`` is used for the bold face.
        Without one, bold falls back to the regular face: a heading that is not
        bold is a cosmetic loss, where refusing to render is not.
        """
        if self.font_path is None or not self.unicode_font:
            return
        pdf.add_font("report", "", str(self.font_path))
        bold = self.font_path.with_name(
            f"{self.font_path.stem}-Bold{self.font_path.suffix}"
        )
        pdf.add_font("report", "B", str(bold if bold.is_file() else self.font_path))
        pdf.body_font = "report"

    # --- blocks -------------------------------------------------------------

    def _title(self, pdf: _ReportDocument, snapshot: dict[str, Any]) -> None:
        pdf.set_font(pdf.body_font, "B", TITLE_SIZE)
        pdf.set_text_color(*ACCENT)
        pdf.cell(
            0,
            9,
            self._clean(str(snapshot.get("title", PDF_TITLE))),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.set_draw_color(*ACCENT)
        pdf.set_line_width(0.5)
        pdf.line(MARGIN, pdf.get_y() + 0.5, pdf.w - MARGIN, pdf.get_y() + 0.5)
        pdf.ln(3.4)

    def _header(self, pdf: _ReportDocument, snapshot: dict[str, Any]) -> None:
        header = snapshot.get("header", {})

        pdf.set_font(pdf.body_font, "B", PATIENT_SIZE)
        pdf.set_text_color(*BODY)
        patient = str(header.get("patient", "")).strip()
        if patient:
            pdf.cell(
                0,
                5.6,
                self._clean(patient),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

        pdf.set_font(pdf.body_font, "", BODY_SIZE)
        pdf.set_text_color(*MUTED)
        for line in header.get("lines", []):
            pdf.multi_cell(
                0,
                LINE_HEIGHT,
                self._clean(str(line)),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

        note = snapshot.get("period", {}).get("note")
        if note:
            pdf.multi_cell(
                0,
                LINE_HEIGHT,
                self._clean(str(note)),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        pdf.ln(2.2)

    def _section(self, pdf: _ReportDocument, section: dict[str, Any]) -> None:
        heading = str(section.get("heading", "")).strip()
        if heading:
            pdf.ln(1.6)
            pdf.set_font(pdf.body_font, "B", HEADING_SIZE)
            pdf.set_text_color(*ACCENT)
            pdf.cell(
                0,
                5.2,
                self._clean(heading),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.set_draw_color(*RULE)
            pdf.set_line_width(0.2)
            pdf.line(MARGIN, pdf.get_y(), pdf.w - MARGIN, pdf.get_y())
            pdf.ln(1.4)

        for item in section.get("items", []):
            self._item(pdf, item)

    def _item(self, pdf: _ReportDocument, item: dict[str, Any]) -> None:
        title = item.get("title")
        lines = [str(line) for line in item.get("lines", [])]

        if title:
            pdf.set_font(pdf.body_font, "B", BODY_SIZE)
            pdf.set_text_color(*BODY)
            pdf.cell(
                0,
                LINE_HEIGHT,
                self._clean(str(title)),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        elif lines:
            # A bullet is drawn rather than typed: no standard-font glyph has to
            # exist for it, so it looks the same with or without an embedded
            # font.
            pdf.set_fill_color(*ACCENT)
            pdf.rect(
                MARGIN + 0.4,
                pdf.get_y() + (LINE_HEIGHT - BULLET_SIZE) / 2,
                BULLET_SIZE,
                BULLET_SIZE,
                style="F",
            )

        pdf.set_font(pdf.body_font, "", BODY_SIZE)
        pdf.set_text_color(*(BODY if title else MUTED))
        for line in lines:
            pdf.set_x(MARGIN + ITEM_INDENT)
            pdf.multi_cell(
                pdf.w - 2 * MARGIN - ITEM_INDENT,
                LINE_HEIGHT,
                self._clean(line),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        pdf.ln(0.9)

    # --- the document -------------------------------------------------------

    def render(self, snapshot: dict[str, Any]) -> RenderedReport:
        """The whole document.

        The summary occupies page 1 and continues onto page 2 only when the
        user's own selections do not fit at a readable size -- PRD 7 section 26
        rules out shrinking the text to force them in, and ``snapshot.build`` has
        already tightened what it can.

        The appendix, when it is on, always starts on a fresh page, so
        "the appendix begins on page 2" is true of every report that has one.
        """
        footer_lines = [
            self._clean(str(line)) for line in snapshot.get("footer_lines", [])
        ]
        pdf = _ReportDocument(footer_lines, unicode_font=self.unicode_font)
        self._register_fonts(pdf)

        pdf.set_title(PDF_TITLE)
        pdf.set_author(PDF_AUTHOR)
        pdf.set_producer(PDF_PRODUCER)
        pdf.set_lang("en")
        # Pinned to the snapshot's own moment, which is what makes the bytes a
        # function of the snapshot alone.
        generated_at = snapshot.get("generated_at")
        moment = _parse_moment(generated_at) if isinstance(generated_at, str) else None
        if moment is not None:
            pdf.set_creation_date(moment)

        pdf.add_page()
        self._title(pdf, snapshot)
        self._header(pdf, snapshot)

        for section in snapshot.get("summary_sections", []):
            self._section(pdf, section)

        appendix = snapshot.get("appendix_sections", [])
        if snapshot.get("include_appendix") and appendix:
            pdf.add_page()
            for section in appendix:
                self._section(pdf, section)

        content = bytes(pdf.output())
        logger.info("reports: rendered a report of %d pages", pdf.pages_count)
        return RenderedReport(content=content, page_count=pdf.pages_count)


def _parse_moment(value: str) -> datetime | None:
    """``generated_at`` as a datetime, or None if it is not one.

    Tolerant on purpose: a snapshot written by an older build must still render,
    and an unparseable date only costs the PDF its creation-date field -- which
    then falls back to the moment of rendering, so only that one field stops
    being reproducible.
    """
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def get_pdf_service() -> PdfReportService:
    """The service this deployment uses, with its font setting applied."""
    return PdfReportService(get_settings().report_font_file)
