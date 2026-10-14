import pytest

from minion import cli


def test_parser_builds_and_has_commands():
    p = cli.build_parser()
    args = p.parse_args(["-d", "office-1", "click", "@3"])
    assert args.desktop == "office-1" and args.target == ["@3"]
    args = p.parse_args(["click", "@3", "-d", "dev-2", "--json"])
    assert args.desktop == "dev-2" and args.json
    args = p.parse_args(["up", "office", "--size", "1024x768", "-v", "/tmp:/home/agent/x"])
    assert args.profile == "office" and args.mount == ["/tmp:/home/agent/x"]


@pytest.mark.parametrize(
    "parts,expected",
    [
        (["640", "400"], [640, 400]),
        (["640,400"], "640,400"),
        (["@3"], "@3"),
        (["Sign", "in"], "Sign in"),
        ([], None),
    ],
)
def test_targets(parts, expected):
    assert cli._target(parts) == expected


@pytest.mark.parametrize(
    "path,expected",
    [
        ("office-1:~/a.txt", ("office-1", "~/a.txt")),
        (":~/a.txt", (None, "~/a.txt")),
        ("report.pdf", None),
        ("C:\\Users\\me\\a.txt", None),
        ("./local:file", None),
    ],
)
def test_split_remote(path, expected):
    assert cli.split_remote(path) == expected


def test_help_and_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "minion" in capsys.readouterr().out
    assert cli.main(["version"]) == 0


def test_profiles_command(capsys):
    assert cli.main(["profiles"]) == 0
    out = capsys.readouterr().out
    assert "office" in out and "research" in out
    assert cli.main(["profiles", "office", "--json"]) == 0
