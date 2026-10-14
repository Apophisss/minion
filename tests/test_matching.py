"""Text targets: real matches win, fragments never stand in for what the agent asked for."""

from minion.agent.perceive import TARGET_MIN, WAIT_MIN, match_score


def test_exact_and_whole_word_matches():
    assert match_score("Save", "Save") == 100
    assert match_score("save as…", "Save As") == 100
    assert match_score("Help", "View Help") >= 55  # OCR merged two menu titles into one line
    assert match_score("Install", "Install now") >= 55
    assert match_score("Saved", "Document saved successfully") >= WAIT_MIN


def test_fragments_never_match():
    # Seen in dogfooding: these hit a tab-close button, Firefox's reload button and the taskbar.
    assert match_score("Qwxyzzy", "x") == 0
    assert match_score("Zebra crossing quantum", "a") == 0
    assert match_score("Favourite colour", "C") == 0
    assert match_score("Calc Dashboard", "alc") == 0
    assert match_score("Calc Dashboard", "ca") == 0


def test_partial_words_rank_low():
    inside = match_score("save", "Unsaved")
    assert 0 < inside < match_score("save", "Save As")
    assert match_score("ok", "Look") == 0  # short queries need whole words
    assert match_score("Search Wikipedia", "Search") < TARGET_MIN  # a much shorter label is not the target
