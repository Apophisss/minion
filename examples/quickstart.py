"""Minion in 20 lines: create a desktop, look at it as text, act, read a file back.

pip install minion-desktop   (and have Docker running)
python examples/quickstart.py
"""

from minion import Desktop

with Desktop.create("office", keep=False) as desk:  # removed at the end of the block
    desk.open("writer")
    desk.wait_for("Default Paragraph Style")  # Writer is ready
    desk.act({"key": "ctrl+1"}, {"type": "Hello from an agent\n"}, {"type": "Written on a Minion desktop."})
    print(desk.see())  # windows + UI elements with @ids, as text

    desk.key("ctrl+s")
    desk.fill("Name", "hello.docx")
    desk.key("Return")
    desk.wait_for("hello.docx")
    desk.download("~/Documents/hello.docx", ".")
    desk.recording("html", "hello-session.html")  # every step, with thumbnails
    print("Saved hello.docx and hello-session.html")
