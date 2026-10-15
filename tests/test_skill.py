"""The Agent Skill and the Claude Code plugin must stay in sync with the CLI and the package."""

import json
import re
from pathlib import Path

from minion.agent import VERSION
from minion.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "minion" / "skill" / "SKILL.md"


def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md needs YAML frontmatter"
    return dict(line.split(": ", 1) for line in m.group(1).splitlines())


def test_skill_frontmatter_follows_the_agent_skills_spec():
    meta = _frontmatter(SKILL.read_text())
    assert meta["name"] == "minion" and re.fullmatch(r"[a-z0-9-]{1,64}", meta["name"])
    assert 0 < len(meta["description"]) <= 1024


def test_plugin_ships_the_same_skill():
    assert (ROOT / "plugins/minion/skills/minion/SKILL.md").read_text() == SKILL.read_text()


def test_plugin_and_marketplace_manifests():
    plugin = json.loads((ROOT / "plugins/minion/.claude-plugin/plugin.json").read_text())
    assert plugin["name"] == "minion" and plugin["version"] == VERSION
    assert plugin["mcpServers"]["minion"]["args"] == [f"minion-desktop@{VERSION}", "mcp"]  # this exact release
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    (entry,) = market["plugins"]
    assert entry["name"] == plugin["name"] and market["owner"]["name"]
    assert entry["source"].startswith("./") and (ROOT / entry["source"]).is_dir()


def test_every_command_in_the_skill_exists():
    commands = set(build_parser()._subparsers._group_actions[0].choices)
    used = set(re.findall(r"`minion ([a-z-]+)", SKILL.read_text()))
    assert used and used <= commands, used - commands


def test_every_tool_says_whether_it_changes_things():
    from minion.tools import COMPUTER_TOOL, TOOLS

    for tool in [*TOOLS, COMPUTER_TOOL]:
        notes = tool["annotations"]
        assert {"title", "readOnlyHint", "destructiveHint"} <= set(notes), tool["name"]
