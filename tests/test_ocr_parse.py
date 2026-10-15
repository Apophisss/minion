from minion.agent.ocr import parse_tsv

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"


def row(block, line, word, left, top, w, h, conf, text):
    return f"5\t1\t{block}\t1\t{line}\t{word}\t{left}\t{top}\t{w}\t{h}\t{conf}\t{text}"


def test_groups_words_into_lines_and_scales_back():
    tsv = "\n".join(
        [
            HEADER,
            row(1, 1, 1, 20, 40, 60, 20, 95, "Save"),
            row(1, 1, 2, 90, 40, 40, 20, 90, "As"),
            row(1, 1, 3, 600, 40, 80, 20, 91, "Cancel"),  # far away: separate line
            row(2, 1, 1, 20, 100, 50, 20, 10, "junk"),  # low confidence: dropped
        ]
    )
    lines = parse_tsv(tsv, scale=2.0, offset=(100, 200))
    texts = [ln.text for ln in lines]
    assert texts == ["Save As", "Cancel"]
    save = lines[0]
    assert (save.x, save.y) == (110, 220)  # 20/2 + 100, 40/2 + 200
    assert save.w == 55  # (130 - 20) / 2
    assert len(save.words) == 2


def test_right_to_left_lines_keep_tesseracts_reading_order():
    # Tesseract lists words in reading order: Hebrew from the right, an English run inside it left to right.
    tsv = "\n".join(
        [
            HEADER,
            row(1, 1, 1, 540, 0, 80, 40, 90, "מבוא"),
            row(1, 1, 2, 360, 0, 160, 40, 90, "למנהיגות"),
            row(1, 1, 3, 330, 16, 16, 6, 90, "–"),  # a dash is small: it must not split the title
            row(1, 1, 4, 0, 0, 140, 40, 90, "Mozilla\u200f"),  # with a stray direction mark
            row(1, 1, 5, 160, 0, 140, 40, 90, "Firefox"),
            row(2, 1, 1, 900, 100, 120, 40, 90, "שמור"),  # two buttons far apart on one line: two lines,
            row(2, 1, 2, 100, 100, 120, 40, 90, "ביטול"),  # the right one first
        ]
    )
    lines = parse_tsv(tsv, scale=2.0)
    assert [ln.text for ln in lines] == ["מבוא למנהיגות – Mozilla Firefox", "שמור", "ביטול"]
    assert lines.words == 7 and lines.conf == 90


def test_wrong_language_reads_with_low_confidence():
    tsv = "\n".join([HEADER] + [row(1, 1, i, 50 * i, 0, 40, 20, conf, "Nin") for i, conf in enumerate([20, 30, 45, 0])])
    lines = parse_tsv(tsv)
    assert lines.words == 4 and lines.conf == (20 + 30 + 45 + 0) / 4  # every word counts, kept (>= 35) or not
    assert [ln.text for ln in lines] == ["Nin"]


def test_languages_follow_the_scripts_on_screen():
    from minion.agent.ocr import langs_for

    assert langs_for("מבוא למנהיגות קק״ס — Mozilla Firefox") == ["heb", "eng"]
    assert langs_for("Untitled 1 — LibreOffice Calc") == ["eng"]
    assert langs_for("Привет, мир") == ["rus", "eng"]
    assert langs_for("こんにちは世界") == ["jpn", "eng"]  # kana: Japanese, not Chinese
    assert langs_for("你好世界") == ["chi_sim", "eng"]
    assert langs_for("مرحبا بالعالم") == ["ara", "eng"]
    assert langs_for("a ש b") == ["eng"]  # one stray letter is not a language


def test_blind_spots_are_detailed_parts_no_accessible_text_covers():
    from PIL import Image, ImageDraw

    from minion.agent.ocr import blind_spots

    img = Image.new("RGB", (640, 400), "white")
    d = ImageDraw.Draw(img)
    for y in range(20, 60, 10):  # a toolbar whose buttons accessibility reads
        d.text((20, y), "File Edit View Help Tools", fill="black")
    line = "Lorem ipsum dolor sit amet, consectetur adipiscing elit"
    for y in range(140, 360, 14):  # a picture of text: no accessible element covers it
        d.text((100, y), line, fill="black")
    x0, y0, x1, _ = d.textbbox((100, 140), line)
    y1 = d.textbbox((100, 350), line)[3]
    toolbar = [(1000, 2000, 640, 70)]  # screen coordinates, like the window's origin
    spots = blind_spots(img, toolbar, origin=(1000, 2000))
    assert len(spots) == 1
    x, y, w, h = spots[0]
    x, y = x - 1000, y - 2000  # back to window coordinates: the region holds the text, give or take a cell
    assert x <= x0 < x + 32 and x + w - 32 < x1 <= x + w and y <= y0 < y + 32 and y + h - 32 < y1 <= y + h
    assert blind_spots(img, [(0, 0, 640, 400)]) == []  # all of it is covered
    assert blind_spots(Image.new("RGB", (640, 400), "white"), []) == []  # nothing to read


def test_missing_language_data_is_installed_once(monkeypatch):
    from minion.agent import catalog, ocr

    have = {"eng", "osd"}
    calls = []

    def install(packages, timeout=0):
        calls.append(packages)
        have.update(p.removeprefix("tesseract-ocr-").replace("-", "_") for p in packages)
        return 1.0, "log"

    monkeypatch.setattr(ocr, "_installed", None)
    monkeypatch.setattr(ocr, "_failed", set())
    monkeypatch.setattr(ocr, "installed", lambda: set(have))
    monkeypatch.setattr(catalog, "install", install)
    assert ocr.ensure(["heb", "eng"]) == (["heb", "eng"], "installed Hebrew OCR")
    assert ocr.ensure(["heb", "eng"]) == (["heb", "eng"], "")  # already there
    assert calls == [["tesseract-ocr-heb"]]

    def offline(packages, timeout=0):
        raise catalog.InstallError("this desktop has no internet access")

    monkeypatch.setattr(catalog, "install", offline)
    langs, note = ocr.ensure(["chi_sim", "eng"])
    assert langs == ["eng"] and "no Chinese OCR" in note  # reads what it can
    assert ocr.ensure(["chi_sim", "eng"]) == (["eng"], "")  # and doesn't try again


def test_script_detection_names_the_language(monkeypatch):
    import subprocess

    from PIL import Image

    from minion.agent import ocr

    monkeypatch.setattr(ocr, "installed", lambda: {"eng", "osd"})

    def osd(script, conf):
        out = f"Page number: 0\nOrientation in degrees: 0\nScript: {script}\nScript confidence: {conf}\n"
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, out, "")

    img = Image.new("RGB", (200, 100), "white")
    monkeypatch.setattr(ocr.subprocess, "run", osd("Hebrew", 3.2))
    assert ocr.detect(img) == ["heb", "eng"]
    monkeypatch.setattr(ocr.subprocess, "run", osd("Latin", 9.0))
    assert ocr.detect(img) == ["eng"]
    monkeypatch.setattr(ocr.subprocess, "run", osd("Arabic", 0.0))
    assert ocr.detect(img) == ["ara", "eng"]  # a guess, even unsure: read() keeps it only if it reads better
    monkeypatch.setattr(
        ocr.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "Too few characters")
    )
    assert ocr.detect(img) == ["eng"]


def test_page_text_keeps_lines_and_paragraphs():
    from minion.agent.ocr import tsv_text

    tsv = "\n".join(
        [
            HEADER,
            "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t90\tמהי",
            "5\t1\t1\t1\t1\t2\t0\t0\t10\t10\t90\tמנהיגות?‏",
            "5\t1\t1\t2\t1\t1\t0\t0\t10\t10\t90\tמנהיגות",
            "5\t1\t1\t2\t1\t2\t0\t0\t10\t10\t12\tהיא",  # every word counts in page text, sure or not
            "5\t1\t1\t2\t2\t1\t0\t0\t10\t10\t90\tתהליך.",
        ]
    )
    assert tsv_text(tsv) == "מהי מנהיגות?\n\nמנהיגות היא\nתהליך."


def test_light_text_on_colour_gets_its_own_pass(monkeypatch):
    from PIL import Image

    from minion.agent import ocr

    assert ocr._colourful(Image.new("RGB", (200, 100), "white")) == 0
    assert ocr._colourful(Image.new("RGB", (200, 100), (230, 120, 40))) > 0.9  # an orange box
    found = parse_tsv("\n".join([HEADER, row(1, 1, 1, 100, 100, 200, 40, 90, "קבלת")]))
    second = "\n".join(
        [
            HEADER,
            row(1, 1, 1, 100, 100, 200, 40, 88, "קבלת"),  # already read: same place
            row(2, 1, 1, 100, 300, 300, 40, 91, "מוטיבציה"),  # white on orange: new
            row(3, 1, 1, 100, 500, 200, 40, 30, "ההודוחה"),  # unsure: noise
        ]
    )
    monkeypatch.setattr(ocr, "_tesseract", lambda *a, **k: second)
    extra = ocr._light_text(Image.new("RGB", (400, 300), (230, 120, 40)), "heb+eng", 1.0, found, 10)
    assert [ln.text for ln in extra] == ["קבלת", "מוטיבציה"]  # the unsure one is dropped
    merged = ocr._merge(found, extra, better=True)
    assert [ln.text for ln in merged] == ["קבלת", "מוטיבציה"]  # read twice: once

    junk = parse_tsv("\n".join([HEADER, row(1, 1, 1, 100, 100, 200, 40, 52, "SIVI")]))  # a box read badly
    better = parse_tsv("\n".join([HEADER, row(1, 1, 1, 96, 98, 210, 42, 93, "Goal")]))
    assert [ln.text for ln in ocr._merge(junk, list(better), better=True)] == ["Goal"]


def test_big_text_on_one_row_reads_right_to_left():
    from minion.agent.ocr import Line, Lines, _sort_lines

    # Two halves of a large Hebrew title, a few pixels apart vertically, then a smaller line below.
    lines = Lines(
        [
            Line("- מבוא למנהיגות", 200, 356, 450, 52, 90),
            Line("פתיחת ציר", 700, 350, 350, 52, 90),
            Line('מחזור י"ח', 560, 450, 140, 30, 90),
        ]
    )
    assert [ln.text for ln in _sort_lines(lines)] == ["פתיחת ציר", "- מבוא למנהיגות", 'מחזור י"ח']


def test_a_browser_page_is_below_its_address_bar():
    from types import SimpleNamespace as El

    from minion.agent.perceive import _below_toolbar, _inside

    window = (0, 0, 1280, 770)
    bar = El(role="address bar", x=253, y=56, w=740, h=17)
    assert _below_toolbar([bar, El(role="button", x=0, y=700, w=50, h=20)], window) == (0, 81, 1280, 689)
    assert _below_toolbar([El(role="button", x=0, y=0, w=50, h=20)], window) == window  # not a browser
    assert _inside((1186, 122), [(1108, 103, 156, 40)]) and not _inside((640, 380), [(1108, 103, 156, 40)])


def test_known_text_is_painted_over_and_plain_margins_trimmed():
    from PIL import Image, ImageDraw

    from minion.agent.ocr import mask, trim

    page = Image.new("RGB", (400, 300), "white")
    d = ImageDraw.Draw(page)
    d.text((10, 10), "A heading accessibility reads", fill="black")
    d.rectangle([50, 100, 349, 249], fill=(79, 70, 229))  # a picture on the page
    d.text((60, 110), "Q3 review", fill="white")
    clean = mask(page, [(1010, 2005, 300, 20)], origin=(1000, 2000))  # the heading's box, in screen coordinates
    assert clean.getpixel((15, 12)) == (255, 255, 255) and clean.getpixel((60, 120)) != (255, 255, 255)
    tight, (dx, dy) = trim(clean)
    assert (dx, dy) == (50, 100) and tight.size == (300, 150)  # just the picture, to its edge
    full = Image.new("RGB", (400, 300), (79, 70, 229))
    assert trim(full) == (full, (0, 0))  # nothing plain to cut


def test_overlapping_blind_spots_become_one():
    from PIL import Image, ImageDraw

    from minion.agent.ocr import blind_spots

    img = Image.new("RGB", (640, 400), "white")
    d = ImageDraw.Draw(img)
    for y in range(40, 380, 14):  # an L of text: a column on the left and a row along the bottom...
        d.text((40, y), "Lorem", fill="black")
    for x in range(40, 600, 60):
        d.text((x, 360), "ipsum", fill="black")
    for y in range(40, 200, 14):  # ...around a block of its own, far enough not to touch it
        d.text((300, y), "dolor sit amet", fill="black")
    spots = blind_spots(img, [])
    assert len(spots) == 1 and spots[0][2] >= 540 and spots[0][3] >= 320  # one box, not two overlapping ones
