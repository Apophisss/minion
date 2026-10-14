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
