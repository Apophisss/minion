from minion.agent.a11y import Element, compact, format_elements


def el(i, role, name, depth=0, x=0, y=0, **kw):
    return Element(i, role, name, depth, x, y, 20, 10, **kw)


def test_compact_drops_repeating_wrappers_and_twins():
    els = [
        el(1, "list item", "News"),
        el(2, "link", "News", 1),
        el(3, "heading", "Title"),
        el(4, "link", "Title", 1),
        el(5, "list item", "Two"),
        el(6, "link", "A", 1),
        el(7, "link", "B", 1),
        el(8, "menu", "File", 0, 10, 30),
        el(9, "menu", "File", 0, 14, 33),
    ]
    out = compact(els)
    lines = format_elements(out)
    assert lines[0].startswith('@1 link "News"')
    assert lines[1].startswith('@2 heading link "Title"')
    assert lines[2].startswith('@3 link "A"')  # a list item with several children is dropped
    assert lines[3].startswith('@4 link "B"')
    assert sum(1 for line in lines if '"File"' in line) == 1
    assert [e.id for e in out] == list(range(1, len(out) + 1))


def test_format_flags_and_text():
    out = format_elements(
        [el(1, "check box", "Remember me", states=["unchecked"]), el(2, "terminal", "Terminal", text="$ ls ⏎ a b")]
    )
    assert out[0] == '@1 check box "Remember me" [unchecked] (10,5)'
    assert out[1] == '@2 terminal "Terminal": $ ls ⏎ a b (10,5)'
