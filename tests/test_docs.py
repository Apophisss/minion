"""Reading documents as text inside a desktop (minion-read), with small hand-built files."""

import zipfile

import pytest

from minion.agent import docs

CT = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
REL = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'


def make_zip(path, parts: dict) -> str:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return str(path)


def test_docx_headings_lists_and_tables(tmp_path):
    body = (
        f"<w:document {W}><w:body>"
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Quarterly report</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>Sales grew</w:t></w:r><w:r><w:tab/><w:t>12%</w:t></w:r></w:p>"
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/></w:numPr></w:pPr><w:r><w:t>First point</w:t></w:r></w:p>'
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Item</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Price</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>Coffee</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>3.5</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "</w:body></w:document>"
    )
    path = make_zip(tmp_path / "r.docx", {"[Content_Types].xml": CT, "word/document.xml": body})
    text, kind = docs.read(path)
    assert kind == "Word document"
    assert "# Quarterly report" in text and "Sales grew\t12%" in text and "- First point" in text
    assert "| Item | Price |" in text and "| Coffee | 3.5 |" in text


def test_xlsx_values_shared_strings_and_formulas(tmp_path):
    parts = {
        "[Content_Types].xml": CT,
        "xl/workbook.xml": f'<workbook {S} {R}><sheets><sheet name="Budget" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships {REL}><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="ws"/></Relationships>',
        "xl/sharedStrings.xml": f"<sst {S}><si><t>Item</t></si><si><t>Total</t></si></sst>",
        "xl/worksheets/sheet1.xml": (
            f"<worksheet {S}><sheetData>"
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>3.5</v></c></row>'
            '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><f>SUM(B1:B1)</f><v>3.5</v></c>'
            '<c r="C2" t="e"><f>1/0</f><v>#DIV/0!</v></c></row>'
            "</sheetData></worksheet>"
        ),
    }
    text, _ = docs.read(make_zip(tmp_path / "b.xlsx", parts))
    assert "## Sheet: Budget" in text
    assert "A1: Item  B1: 3.5" in text and "A2: Total  B2: 3.5  C2: #DIV/0!" in text
    assert "Formulas: B2 =SUM(B1:B1); C2 =1/0" in text


def test_pptx_slides_in_order(tmp_path):
    A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    P = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'

    def slide(*lines):
        paras = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in lines)
        return f"<p:sld {A} {P}><p:cSld><p:spTree><p:sp><p:txBody>{paras}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"

    parts = {
        "[Content_Types].xml": CT,
        "ppt/presentation.xml": f'<p:presentation {P} {R}><p:sldIdLst><p:sldId id="256" r:id="rId2"/><p:sldId id="257" r:id="rId1"/></p:sldIdLst></p:presentation>',
        "ppt/_rels/presentation.xml.rels": f'<Relationships {REL}><Relationship Id="rId1" Target="slides/slide1.xml" Type="s"/><Relationship Id="rId2" Target="slides/slide2.xml" Type="s"/></Relationships>',
        "ppt/slides/slide1.xml": slide("Thanks"),
        "ppt/slides/slide2.xml": slide("Minion", "Desktops for agents"),
    }
    text, _ = docs.read(make_zip(tmp_path / "d.pptx", parts))
    assert text.index("## Slide 1\nMinion\nDesktops for agents") < text.index("## Slide 2\nThanks")


def test_opendocument_text_and_sheet(tmp_path):
    ns = (
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"'
    )
    odt = (
        f"<office:document-content {ns}><office:body><office:text>"
        '<text:h text:outline-level="2">Plan</text:h><text:p>Ship<text:s text:c="2"/>it</text:p>'
        "<text:list><text:list-item><text:p>One</text:p></text:list-item></text:list>"
        "</office:text></office:body></office:document-content>"
    )
    text, kind = docs.read(make_zip(tmp_path / "p.odt", {"mimetype": "x", "content.xml": odt}))
    assert kind == "OpenDocument text" and "## Plan" in text and "Ship  it" in text and "- One" in text
    ods = (
        f"<office:document-content {ns}><office:body><office:spreadsheet>"
        '<table:table table:name="Data"><table:table-row>'
        '<table:table-cell table:number-columns-repeated="2"/>'
        "<table:table-cell><text:p>x</text:p></table:table-cell></table:table-row>"
        '<table:table-row table:number-rows-repeated="1048000"><table:table-cell table:number-columns-repeated="16384"/></table:table-row>'
        '<table:table-row><table:table-cell table:formula="of:=1+1"><text:p>2</text:p></table:table-cell></table:table-row>'
        "</table:table></office:spreadsheet></office:body></office:document-content>"
    )
    text, _ = docs.read(make_zip(tmp_path / "s.ods", {"mimetype": "x", "content.xml": ods}))
    assert "## Sheet: Data" in text and "C1: x" in text and "A1048002: 2 (=1+1)" in text


def test_html_epub_text_and_errors(tmp_path):
    page = tmp_path / "a.html"
    page.write_text(
        "<html><head><style>p{}</style><script>x=1</script></head><body><h1>Title</h1><p>Hello <b>world</b></p><ul><li>a</li></ul></body></html>"
    )
    text, _ = docs.read(str(page))
    assert "# Title" in text and "Hello world" in text and "- a" in text and "x=1" not in text
    container = '<container><rootfiles><rootfile full-path="OEBPS/c.opf"/></rootfiles></container>'
    opf = (
        '<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="c1" href="one.xhtml"/></manifest>'
        '<spine><itemref idref="c1"/></spine></package>'
    )
    book = make_zip(
        tmp_path / "b.epub",
        {
            "META-INF/container.xml": container,
            "OEBPS/c.opf": opf,
            "OEBPS/one.xhtml": "<html><body><p>Chapter one</p></body></html>",
        },
    )
    assert "Chapter one" in docs.read(book)[0]
    note = tmp_path / "n.md"
    note.write_text("# Notes\n\n\n\nkeep")
    assert docs.read(str(note)) == ("# Notes\n\n\n\nkeep", "text")  # text files stay exact
    with pytest.raises(docs.DocError, match="no such file"):
        docs.read(str(tmp_path / "missing.docx"))
    with pytest.raises(docs.DocError, match="not a valid Word document"):
        docs.read(make_zip(tmp_path / "bad.docx", {"x": "y"}))
    blob = tmp_path / "x.bin"
    blob.write_bytes(b"\x00\x01binary")
    with pytest.raises(docs.DocError, match="binary file"):
        docs.read(str(blob))


def test_convert_images_and_markdown_without_pandoc(tmp_path, monkeypatch):
    from PIL import Image

    Image.new("RGB", (4, 4), "red").save(tmp_path / "dot.png")
    out = docs.convert(str(tmp_path / "dot.png"), "jpeg")
    assert out.endswith("dot.jpg") and Image.open(out).format == "JPEG"
    page = tmp_path / "p.html"
    page.write_text("<h1>Hi</h1><p>there</p>")
    monkeypatch.setattr(docs.shutil, "which", lambda name: None)
    md = docs.convert(str(page), "markdown", str(tmp_path / "out"))
    assert open(md).read().startswith("# Hi")
    with pytest.raises(docs.DocError, match="LibreOffice"):
        docs.convert(str(page), "docx")
