"""see(changes=true): diffs stay small and honest."""

from types import SimpleNamespace

from minion.agent.a11y import Element
from minion.agent.perceive import Perception


def view(elements, t=0.0):
    win = SimpleNamespace(id="0x1", title="App", focused=True)
    v = Perception._view([win], win, elements, [])
    v["time"] = t
    return v


def el(i, name, y, text="", role="push button"):
    return Element(id=i, role=role, name=name, depth=0, x=10, y=y, w=50, h=20, text=text)


def test_moves_are_not_changes():
    before = [el(i, f"Item {i}", 20 * i) for i in range(1, 11)]
    after = [el(i, f"Item {i}", 20 * i + 200) for i in range(1, 11)]  # scrolled: same elements, new places
    d = Perception._diff(view(before), view(after, 1.0))
    assert "full" not in d and d["moved"] == 10 and d["changed"] == 0
    assert "10 moved" in d["text"] and "only positions changed" in d["text"]


def test_many_removals_are_summarized():
    before = [el(i, f"Menu item {i}", 20 * i, role="menu item") for i in range(1, 31)] + [el(99, "OK", 700)]
    after = [el(99, "OK", 700)]
    d = Perception._diff(view(before), view(after, 1.0))
    assert d["removed"] == 30 and d["text"].count("\n  - ") == 9 and "… and 22 more gone" in d["text"]
    assert '- @1 menu item "Menu item 1"' in d["text"]  # coordinates trimmed, quotes intact


def test_truncation_is_not_a_change():
    short = [el(1, "", 20, text="A long paragraph that the normal look cuts…", role="paragraph")]
    full = [el(1, "", 20, text="A long paragraph that the normal look cuts off here.", role="paragraph")]
    d = Perception._diff(view(short), view(full, 1.0))
    assert d["changed"] == 0 and "(nothing changed)" in d["text"]


def test_big_changes_fall_back_to_the_full_view():
    before = [el(i, f"A{i}", 20 * i) for i in range(1, 40)]
    after = [el(i + 100, f"B{i}", 20 * i) for i in range(1, 40)]
    assert Perception._diff(view(before), view(after, 1.0)) == {"full": "most of the screen changed"}
