import pytest

from minion.agent.xinput import InputError, XInput, normalize_combo, normalize_modifiers, split_combo


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
        ("cmd+c", "ctrl+c"),  # macOS habits mean ctrl on these desktops
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


class FakeXdo(XInput):
    """Records xdotool calls; the pointer starts at (100, 100)."""

    def __init__(self):
        self.calls, self.at = [], (100, 100)

    def _xdo(self, *args, timeout=30.0):
        if args[0] == "getmouselocation":
            return f"X={self.at[0]}\nY={self.at[1]}\nSCREEN=0\nWINDOW=1\n"
        self.calls.append(args)
        if args[0] == "mousemove":
            i = 2 if args[1] == "--sync" else 1
            self.at = (int(args[i]), int(args[i + 1]))
        return ""


def test_pointer_moves_never_wait_for_a_move_that_cannot_happen():
    # xdotool's `mousemove --sync` to where the pointer already is waits ~15 s for motion
    xi = FakeXdo()
    xi.click(100, 100)
    assert xi.calls == [("click", "--repeat", "1", "--delay", "70", "1")]
    xi.calls.clear()
    xi.click(140, 100)
    assert xi.calls[0][:6] == ("mousemove", "--sync", "140", "100", "click", "--repeat")
    xi.calls.clear()
    xi.move(140, 100)
    xi.scroll("down", 2, 140, 100)
    assert xi.calls == [("click", "--repeat", "2", "--delay", "25", "5")]
    xi.calls.clear()
    xi.drag(140, 100, 143, 100)  # 12 steps over 3 px: no repeated points
    moves = [c for c in xi.calls if c[0] == "mousemove"]
    assert [c[2:] for c in moves] == [("141", "100"), ("142", "100"), ("143", "100")]
