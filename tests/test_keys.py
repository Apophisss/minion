import pytest

from minion.agent.xinput import InputError, normalize_combo, normalize_modifiers, split_combo


@pytest.mark.parametrize(
    "combo,expected",
    [
        ("ctrl+s", "ctrl+s"),
        ("Ctrl+S", "ctrl+s"),
        ("ctrl+A", "ctrl+a"),
        ("A", "A"),
        ("enter", "Return"),
        ("Return", "Return"),
        ("esc", "Escape"),
        ("cmd+c", "super+c"),
        ("alt+Tab", "alt+Tab"),
        ("PageDown", "Page_Down"),
        ("ctrl+shift+t", "ctrl+shift+t"),
        ("ctrl++", "ctrl+plus"),
        ("ctrl+-", "ctrl+minus"),
        ("f5", "F5"),
        ("shift+F10", "shift+F10"),
        ("space", "space"),
        ("arrowdown", "Down"),
        ("BackSpace", "BackSpace"),
    ],
)
def test_normalize_combo(combo, expected):
    assert normalize_combo(combo) == expected


def test_split_plus():
    assert split_combo("+") == ["+"]
    assert split_combo("ctrl++") == ["ctrl", "+"]
    assert split_combo(" ctrl + s ") == ["ctrl", "s"]


def test_modifiers():
    assert normalize_modifiers("ctrl+shift") == ["ctrl", "shift"]
    assert normalize_modifiers(None) == []
    with pytest.raises(InputError):
        normalize_modifiers("ctrl+x")
