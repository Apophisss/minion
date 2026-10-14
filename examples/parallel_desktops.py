"""Several desktops at once: each worker gets its own computer.

Desktops are cheap (about 1.5 s to start, ~60 MB idle), so fanning out is natural.
"""

from concurrent.futures import ThreadPoolExecutor

from minion import Desktop

TOPICS = ["Ada Lovelace", "Alan Turing", "Grace Hopper"]


def research(topic: str) -> str:
    with Desktop.create("research", keep=False) as desk:
        desk.open("en.wikipedia.org/wiki/" + topic.replace(" ", "_"))
        desk.wait_for(topic, timeout=20)
        obs = desk.see(full_text=True)
        first_paragraph = next((e["text"] for e in obs.elements if e["role"] == "paragraph" and e.get("text")), "")
        return f"{topic}: {first_paragraph[:300]}"


with ThreadPoolExecutor(max_workers=len(TOPICS)) as pool:
    for summary in pool.map(research, TOPICS):
        print(summary, "\n")
