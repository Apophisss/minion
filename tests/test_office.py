"""What agents doing OSWorld's office tasks (LibreOffice Calc, Writer, Impress) ran into: each test pins one fix."""

import os
import zipfile

from minion.agent import a11y, docs, perceive, server
from minion.agent.a11y import Element
from minion.agent.server import CELL_REF, _reads_as, parse_step

CT = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
REL = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
P = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'


def make_zip(path, parts: dict) -> str:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return str(path)


def el(role, name, x=100, y=100, w=80, h=20, **kw):
    return Element(0, role, name, 0, x, y, w, h, **kw)


# -- typing ---------------------------------------------------------------------------------------
def test_typed_text_keeps_the_spaces_at_its_ends():
    # "type , " typed one character, and "health. " lost its space: the next words ran together
    assert parse_step("type health. ")[1]["text"] == "health. "
    assert parse_step("type , ")[1]["text"] == ", "
    assert parse_step('type " two  "')[1]["text"] == " two  "  # quoted: exactly what is inside
    assert parse_step("type hello\\n")[1]["text"] == "hello\n"


def test_the_cli_passes_act_steps_with_their_ends(monkeypatch):
    from minion import cli

    seen = []
    monkeypatch.setattr(cli, "act_and_print", lambda args, *steps, observe=None: seen.extend(steps) or 0)
    args = type("A", (), {"steps": ["type end ", "  key Tab"], "observe": None})()
    cli.cmd_act(args)
    assert seen == ["type end ", "key Tab"]


# -- spreadsheets ---------------------------------------------------------------------------------
def test_cell_and_range_references_are_targets_in_calc():
    for ref in ("B8", "C2:C29", "$A$1", "$C$2:$C$29", "Sheet2.A1", "AB12"):
        assert CELL_REF.fullmatch(ref), ref
    for text in ("Save", "OK", "Total 2", "A0", "B", "12", "Page 1", "1.5 Lines"):
        assert not CELL_REF.fullmatch(text), text


def test_a_cell_reference_needs_calcs_window():
    agent = server.Agent.__new__(server.Agent)

    class Wins:
        def __init__(self, title):
            self.title = title

        def focused(self):
            return type("W", (), {"title": self.title})()

    agent.windows = Wins("budget.xlsx — LibreOffice Calc")
    assert agent._calc_ref("C2:C29") == "C2:C29"
    assert agent._calc_ref("Save") is None
    agent.windows = Wins("Untitled 1 — LibreOffice Writer")
    assert agent._calc_ref("B8") is None  # (a button named B8 elsewhere stays a button)


def test_the_name_box_read_off_the_screen_is_a_cell_reference():
    # OCR reads the Name Box's "A1" as "Al"
    assert perceive._cell_ref("Al") == "A1"
    assert perceive._cell_ref("BlO") == "B10"
    assert perceive._cell_ref("c2:cl0") == "C2:C10"
    assert perceive._cell_ref("Formulas") == "Formulas"


def test_a_formula_cut_by_libreoffice_says_so():
    class Cell:
        def get_attributes_as_array(self):
            return ["Formula:SUM(B3\\", "colindextext:D"]  # (LibreOffice loses what follows an escaped ":")

    assert a11y._formula(Cell()) == "=SUM(B3…"


def test_where_a_sheets_data_ends_below_the_view(monkeypatch):
    rows = {r: f"v{r}" for r in range(0, 29)}  # rows 1 to 29 have data; the view stops at row 25

    class Table:
        @staticmethod
        def get_accessible_at(table, r, c):
            return ("cell", r, c)

    monkeypatch.setattr(a11y, "Atspi", type("Atspi", (), {"Table": Table}))
    monkeypatch.setattr(a11y, "_interfaces", lambda node: {"Text"})
    monkeypatch.setattr(a11y, "_text", lambda node, n: rows.get(node[1], ""))
    import time

    assert a11y._data_below(object(), 24, [0, 1], time.monotonic() + 5) == 28  # (0-based: row 29)
    assert a11y._data_below(object(), 28, [0], time.monotonic() + 5) == 28  # nothing more


def test_a_sheet_with_dates_says_how_they_are_listed():
    assert a11y._TYPED_DATE.match("06/01/2022")
    assert not a11y._TYPED_DATE.match("6/1/2022")


# -- dropdowns ------------------------------------------------------------------------------------
def test_an_option_is_picked_by_its_whole_name_then_its_start():
    items = [el("list item", n) for n in ("Single", "1.15 Lines", "1.5 Lines", "Double", "Leading")]
    assert a11y.best_option(items, "Double").name == "Double"
    assert a11y.best_option(items, "1.5").name == "1.5 Lines"
    assert a11y.best_option(items, "lines") is None  # (three contain it: none is meant)
    assert a11y.best_option(items, "Triple") is None


def test_what_a_dropdown_shows_is_compared_loosely():
    assert _reads_as("1.5 Lines", "1.5 Lines") and _reads_as("Double", "double")
    assert _reads_as("15 Lines", "1.5 Lines")  # (OCR drops a dot)
    assert not _reads_as("Leading", "Double")


# -- what a look says -----------------------------------------------------------------------------
def test_ocr_of_the_title_bar_is_dropped():
    win = type("W", (), {"title": "H2O_Factsheet.docx — LibreOffice Writer", "y": 0})()
    line = type("L", (), {"text": "H20_Factsheet.docx — LibreOffice Writer", "center": (300, 12)})()
    assert perceive._title_echo(line, win)
    body = type("L", (), {"text": "H2O_Factsheet", "center": (300, 400)})()
    assert not perceive._title_echo(body, win)  # (the same words in the document stay)


def test_the_window_list_says_where_the_document_is(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    perceive._DOC_PATHS.clear()
    (tmp_path / "Desktop").mkdir()
    (tmp_path / "Desktop" / "31_2.pptx").write_text("x")
    (tmp_path / "Desktop" / ".~lock.31_2.pptx#").write_text("lock")
    win = type("W", (), {"app": "libreoffice-impress", "title": "31_2.pptx — LibreOffice Impress"})()
    assert perceive._doc_path(win) == "~/Desktop/31_2.pptx"
    other = type("W", (), {"app": "firefox", "title": "31_2.pptx — Mozilla Firefox"})()
    assert perceive._doc_path(other) == ""


# -- reading documents ----------------------------------------------------------------------------
def pptx(tmp_path, slide_xml, rels="", notes=None):
    parts = {
        "[Content_Types].xml": CT,
        "ppt/presentation.xml": f'<p:presentation {P} {R}><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>'
        '<p:sldSz cx="9144000" cy="6858000"/></p:presentation>',
        "ppt/_rels/presentation.xml.rels": f'<Relationships {REL}><Relationship Id="rId1" Target="slides/slide1.xml" Type="s"/></Relationships>',
        "ppt/slides/slide1.xml": slide_xml,
        "ppt/slides/_rels/slide1.xml.rels": f"<Relationships {REL}>{rels}</Relationships>",
    }
    if notes:
        parts["ppt/notesSlides/notesSlide1.xml"] = (
            f'<p:notes {A} {P}><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="N"/><p:cNvSpPr/><p:nvPr>'
            f'<p:ph type="body"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>{notes}</a:t></a:r></a:p></p:txBody></p:sp>'
            "</p:spTree></p:cSld></p:notes>"
        )
    return make_zip(tmp_path / "s.pptx", parts)


def test_a_slides_tables_media_and_notes_are_read(tmp_path):
    slide = (
        f"<p:sld {A} {P} {R}><p:cSld><p:spTree>"
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>Features</a:t></a:r></a:p></p:txBody></p:sp>'
        '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="3" name="Table 3"/></p:nvGraphicFramePr>'
        "<a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>Fast</a:t></a:r></a:p></a:txBody></a:tc>"
        "<a:tc><a:txBody><a:p/></a:txBody></a:tc></a:tr><a:tr><a:tc/><a:tc/></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
        '<p:pic><p:nvPicPr><p:cNvPr id="4" name="Baseball"/><p:cNvPicPr/><p:nvPr><a:audioFile r:link="rId2"/></p:nvPr></p:nvPicPr></p:pic>'
        "</p:spTree></p:cSld></p:sld>"
    )
    rels = (
        '<Relationship Id="rId2" Target="../media/media2.mp3" Type="audio"/>'
        '<Relationship Id="rId3" Target="../notesSlides/notesSlide1.xml" Type="notesSlide"/>'
    )
    text, _ = docs.read(pptx(tmp_path, slide, rels, notes="Should You Consider Studying Abroad?"))
    assert "## Slide 1\nFeatures" in text
    assert '[table "Table 3": 2 rows x 2 columns]' in text and "| Fast |  |" in text
    assert '[audio media2.mp3 "Baseball"]' in text
    assert "Notes: Should You Consider Studying Abroad?" in text


def test_details_give_a_slides_background_and_each_shapes_box_bullets_and_fonts(tmp_path):
    slide = (
        f'<p:sld {A} {P}><p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="0000FF"/></a:solidFill></p:bgPr></p:bg><p:spTree>'
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Picture 7"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="720000" y="360000"/>'
        '<a:ext cx="7603200" cy="7200000"/></a:xfrm></p:spPr><p:txBody>'
        '<a:p><a:pPr marL="457200" indent="0"><a:buNone/></a:pPr><a:r><a:rPr sz="4000" b="1"/><a:t>Our Founder</a:t></a:r></a:p>'
        "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
    )
    text, _ = docs.read(pptx(tmp_path, slide), details=True)
    assert "Slides are 25.40 x 19.05 cm" in text
    assert "Background: #0000FF (solid)" in text
    assert '[shape "Picture 7" at 2.00, 1.00 cm, 21.12 x 20.00 cm]' in text
    assert "Our Founder  (no bullet, indent 1.27 cm, 40 pt, bold)" in text


def test_a_sheets_fills_hidden_rows_merges_and_zoom_are_read(tmp_path):
    parts = {
        "[Content_Types].xml": CT,
        "xl/workbook.xml": f'<workbook {S} {R}><sheets><sheet name="Cal" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships {REL}><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="ws"/></Relationships>',
        "xl/styles.xml": (
            f'<styleSheet {S}><numFmts><numFmt numFmtId="164" formatCode="0.00"/></numFmts>'
            '<fonts><font/></fonts><fills><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFFF0000"/></patternFill></fill></fills>'
            '<cellXfs><xf fillId="0"/><xf fillId="2"/><xf fillId="0" numFmtId="164"/></cellXfs></styleSheet>'
        ),
        "xl/worksheets/sheet1.xml": (
            f'<worksheet {S}><sheetViews><sheetView zoomScale="150"/></sheetViews><sheetData>'
            '<row r="1"><c r="A1" s="1"><v>1</v></c><c r="B1" s="2"><v>2.5</v></c></row>'
            '<row r="2" hidden="1"><c r="A2"><v>3</v></c></row>'
            '</sheetData><mergeCells><mergeCell ref="C1:D1"/></mergeCells></worksheet>'
        ),
    }
    path = make_zip(tmp_path / "c.xlsx", parts)
    text, _ = docs.read(path)
    assert "Fill #FF0000: A1" in text and "Hidden rows: 2" in text and "Merged: C1:D1" in text and "Zoom: 150%" in text
    assert "Format 0.00" not in text
    assert "Format 0.00: B1" in docs.read(path, details=True)[0]


def test_details_give_a_paragraphs_spacing_and_its_runs_formatting(tmp_path):
    body = (
        f"<w:document {W}><w:body>"
        '<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:line="480" w:lineRule="auto"/></w:pPr>'
        '<w:r><w:t>H</w:t></w:r><w:r><w:rPr><w:vertAlign w:val="subscript"/></w:rPr><w:t>2</w:t></w:r><w:r><w:t>O</w:t></w:r></w:p>'
        "</w:body></w:document>"
    )
    path = make_zip(tmp_path / "h.docx", {"[Content_Types].xml": CT, "word/document.xml": body})
    plain = docs.read(path)[0]
    assert plain.strip() == "H2O"
    text = docs.read(path, details=True)[0]
    assert "¶1: center, line spacing 2" in text
    assert "¶1 runs: 'H' · '2' (subscript) · 'O'" in text


def test_tiny_pictures_are_not_given_to_tesseract():
    # "Error in pixSauvolaBinarizeTiled: whsize must be >= 2" lost the OCR of a whole dialog
    from PIL import Image

    from minion.agent import ocr

    assert list(ocr._read_lines(Image.new("RGB", (5, 40), "white"), ["eng"], 5.0)) == []
    assert os.path.exists(ocr.__file__)


def test_a_saved_document_says_which_format_it_holds(tmp_path):
    # agents spent a step on `file` after every ctrl+s to make sure LibreOffice hadn't kept its own format
    xlsx = make_zip(tmp_path / "a.xlsx", {"[Content_Types].xml": CT, "xl/workbook.xml": "<workbook/>"})
    assert server._office_kind(xlsx) == ", Excel format"
    odf = make_zip(tmp_path / "b.xlsx", {"mimetype": "application/vnd.oasis.opendocument.spreadsheet"})
    assert server._office_kind(odf) == ", but it holds OpenDocument, not Excel"
    (tmp_path / "c.docx").write_text("half-written")
    assert server._office_kind(str(tmp_path / "c.docx")) == ", not a valid document yet"
    assert server._office_kind(str(tmp_path / "notes.txt")) == ""


def test_a_cells_spaces_show_when_they_are_part_of_it():
    # "  MiniONs   IN blACK " came out as "MiniONs IN blACK": the very thing the task was to clean up
    cells = [
        el("sheet", "Sheet1", text="visible A1:C3"),
        el("cell", "B2", text="  MiniONs   IN blACK "),
        el("cell", "C2", text="Clean"),
    ]
    cells[1].depth = cells[2].depth = 1
    assert a11y.format_elements(cells)[1].endswith('B2 "  MiniONs   IN blACK " · @0 C2 Clean')


def test_a_click_can_be_optional_and_hold_keys():
    # a "Keep current format?" dialog that may never come must not fail the batch that saved the file
    assert parse_step("click? 'Use Excel 2007-365!'") == ("click", {"target": "Use Excel 2007-365!", "optional": True})
    assert parse_step("ctrl+click @12") == ("click", {"target": "@12", "modifiers": ["ctrl"]})
    assert parse_step("ctrl+shift+click 100,200")[1]["modifiers"] == ["ctrl", "shift"]
