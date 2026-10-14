from minion.agent.recorder import Recorder


def test_macro_export_is_runnable_python():
    rec = Recorder()
    rec.add_macro("open", {"target": "calc"})
    rec.add_macro("click", {"target": "Bold", "button": "left", "count": 1})
    rec.add_macro("click", {"target": "640,400", "button": "right", "count": 2, "modifiers": "ctrl"})
    rec.add_macro("type", {"text": "Total\t=SUM(B1:B3)\n"})
    rec.add_macro("key", {"keys": "ctrl+s", "repeat": 2})
    rec.add_macro("scroll", {"direction": "down", "amount": 5})
    rec.add_macro("fill", {"target": "Name", "text": "q3.xlsx"})
    rec.add_macro("wait_for", {"text": "q3.xlsx", "timeout": 10})
    rec.add_macro("run", {"command": "ls ~/Documents"})
    code = rec.export_script("test")
    compile(code, "<macro>", "exec")
    assert "launch('calc')" in code
    assert "click('Bold')" in code
    assert "click('640,400', button='right', count=2, modifiers='ctrl')" in code
    assert "write('Total\\t=SUM(B1:B3)\\n')" in code
    assert "key('ctrl+s', repeat=2)" in code
    assert "fill('Name', 'q3.xlsx')" in code
    rec.clear()
    assert "launch" not in rec.export_script()
