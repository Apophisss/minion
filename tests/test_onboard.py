"""`minion setup` and finding Docker when a GUI app starts Minion with a minimal PATH."""

import io
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from conftest import docker_ready

from minion import cli, connect, onboard
from minion.backends import docker
from minion.errors import BackendError, NotFound

EXE = ".exe" if os.name == "nt" else ""


def same(a, b) -> bool:
    """The same path (Windows paths are case-insensitive, and `which` reports DOCKER.EXE in PATHEXT's case)."""
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    path.chmod(0o755)
    return path


# -- finding docker and podman ---------------------------------------------------------
@pytest.fixture
def no_path(tmp_path, monkeypatch):
    """PATH as a GUI app on macOS sets it: nothing useful on it."""
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.delenv("MINION_DOCKER", raising=False)
    return tmp_path


def test_docker_on_path_is_used_by_name(no_path, monkeypatch):
    executable(no_path / "empty" / f"docker{EXE}")
    assert docker.find_cli("docker", "podman") == "docker"
    assert docker.DockerBackend().bin == "docker"


def test_docker_off_path_is_found_where_it_installs(no_path, monkeypatch):
    folders = [no_path / "Docker.app/Contents/Resources/bin", no_path / "homebrew/bin"]
    monkeypatch.setattr(docker, "cli_dirs", lambda: [str(f) for f in folders])
    podman = executable(folders[0] / f"podman{EXE}")
    found = executable(folders[1] / f"docker{EXE}")
    assert same(docker.DockerBackend().bin, found)  # docker anywhere comes before podman
    # its folder joins PATH (once), so docker finds its helpers, e.g. docker-credential-desktop
    assert os.environ["PATH"].split(os.pathsep) == [str(no_path / "empty"), str(folders[1])]
    docker.find_cli("docker")
    assert os.environ["PATH"].split(os.pathsep) == [str(no_path / "empty"), str(folders[1])]
    found.unlink()
    assert same(docker.DockerBackend().bin, podman)


def test_nothing_found_keeps_the_old_message(no_path, monkeypatch):
    monkeypatch.setattr(docker, "cli_dirs", lambda: [str(no_path / "nowhere")])
    backend = docker.DockerBackend()
    assert backend.bin == "docker"

    def missing(*args, **kwargs):  # (CI machines can have docker where Windows always looks: System32)
        raise FileNotFoundError(args[0][0])

    monkeypatch.setattr(docker.subprocess, "run", missing)
    with pytest.raises(BackendError, match="Install Docker"):
        backend._run("version")


def test_minion_docker_and_podman_backend(no_path, monkeypatch):
    folder = no_path / "podman/bin"
    monkeypatch.setattr(docker, "cli_dirs", lambda: [str(folder)])
    podman = executable(folder / f"podman{EXE}")
    assert same(docker.DockerBackend("podman").bin, podman)  # MINION_BACKEND=podman
    assert docker.DockerBackend("podman").bin == "podman"  # its folder is on PATH now
    monkeypatch.setenv("PATH", str(no_path / "empty"))
    monkeypatch.setenv("MINION_DOCKER", "podman")
    assert same(docker.DockerBackend().bin, podman)
    monkeypatch.setenv("MINION_DOCKER", str(no_path / "custom" / "docker"))
    assert docker.DockerBackend().bin == str(no_path / "custom" / "docker")  # a path is used as is


def test_auto_backend_finds_docker_off_path(no_path, monkeypatch):
    """With a bare PATH, Docker in its usual folder still wins over the local backend (Linux with Xvfb)."""
    from minion import backends

    monkeypatch.setattr(backends, "_cache", {})
    monkeypatch.delenv("MINION_BACKEND", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")  # (so commands have no .exe, on every OS)
    executable(no_path / "empty" / "Xvfb")
    folder = no_path / "Docker/bin"
    monkeypatch.setattr(docker, "cli_dirs", lambda: [str(folder)])
    assert backends.get_backend().name == "local"  # no Docker anywhere: the local backend
    monkeypatch.setattr(backends, "_cache", {})
    found = executable(folder / "docker")
    backend = backends.get_backend()
    assert backend.name == "docker" and shutil.which(backend.bin) == str(found)  # its folder joined PATH


def test_cli_dirs_per_os(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    dirs = docker.cli_dirs()
    for folder in ("/usr/local/bin", "/opt/homebrew/bin", "/Applications/Docker.app/Contents/Resources/bin"):
        assert folder in dirs
    assert os.path.join(str(tmp_path), ".docker", "bin") in dirs
    assert os.path.join(str(tmp_path), ".orbstack", "bin") in dirs
    assert "/opt/podman/bin" in dirs
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    assert docker.cli_dirs() == [os.path.join(r"C:\Program Files", "Docker", "Docker", "resources", "bin")]


# -- setup ------------------------------------------------------------------------------
class FakeBackend:
    name = "docker"

    def __init__(self, ready=True, detail="docker 28.4.0", bin="docker"):
        self.ready, self.detail, self.bin = ready, detail, bin
        self.prepared = []

    def available(self):
        return self.ready, self.detail

    def prepare(self, profile, progress=None, pull=None):
        if profile.name == "broken":
            raise BackendError("pull failed")
        self.prepared.append(profile.name)
        if progress:
            progress("0.1: Pulling from apophisss/minion-" + profile.name)
        return f"ghcr.io/apophisss/minion-{profile.name}:0.1"


@pytest.fixture
def wizard(tmp_path, monkeypatch):
    """A fake home with Cursor installed, a fake Docker, and no terminal."""
    home = tmp_path / "home"
    (home / ".cursor").mkdir(parents=True)
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(home))
    for var in ("XDG_CONFIG_HOME", "APPDATA", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "GEMINI_CLI_HOME"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "bin").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(sys, "platform", "linux")
    backend = FakeBackend()
    monkeypatch.setattr(onboard, "get_backend", lambda: backend)
    monkeypatch.setattr(connect, "interactive", lambda: False)
    monkeypatch.setattr(connect, "launcher", lambda compact=False: connect.Launch("/opt/minion", ["mcp"]))
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("asked without a terminal"))
    backend.home = home
    return backend


def test_setup_without_a_terminal_uses_the_defaults(wizard, capsys):
    assert onboard.setup() == 0
    out = capsys.readouterr().out
    assert wizard.prepared == ["browser"]
    assert "Which should be ready now?" in out and "no terminal to answer" in out
    assert "Connect Minion to Cursor? [Y/n]: Y" in out  # asked app by app
    assert (
        json.loads((wizard.home / ".cursor/mcp.json").read_text())["mcpServers"]["minion"]["command"] == "/opt/minion"
    )
    assert "minion view" in out and "wikipedia" in out


def test_setup_with_options_asks_nothing(wizard, capsys):
    assert onboard.setup(["office", "dev"], yes=True, compact=True) == 0
    out = capsys.readouterr().out
    assert wizard.prepared == ["office", "dev"]
    assert "[Y/n" not in out and "Which should" not in out  # no questions at all
    assert "memo.docx" in out  # an example for the profile that was prepared


def test_setup_profiles_none(wizard, capsys):
    assert onboard.setup([], yes=True) == 0
    assert wizard.prepared == [] and "Skipped" in capsys.readouterr().out


def test_setup_unknown_profile_fails_first(wizard):
    with pytest.raises(NotFound):
        onboard.setup(["nope"], yes=True)
    assert wizard.prepared == []


def test_setup_reports_a_failed_image(wizard, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("MINION_HOME", str(tmp_path / "mh"))
    (tmp_path / "mh/profiles").mkdir(parents=True)
    (tmp_path / "mh/profiles/broken.toml").write_text('extends = "base"\ndescription = "x"\n')
    assert onboard.setup(["base", "broken"], yes=True) == 1
    captured = capsys.readouterr()
    assert wizard.prepared == ["base"] and "minion pull broken" in captured.out + captured.err


def test_setup_asks_on_a_terminal(wizard, monkeypatch):
    answers = iter(["office, research", "n"])
    monkeypatch.setattr(connect, "interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda q: next(answers))
    assert onboard.setup() == 0
    assert wizard.prepared == ["office", "research"]
    assert not (wizard.home / ".cursor/mcp.json").exists()  # said no to Cursor


@pytest.mark.parametrize(
    "platform,expected",
    [
        ("darwin", ["Docker Desktop", "OrbStack", "mac-install"]),
        ("win32", ["Docker Desktop", "winget install", "WSL 2"]),
        ("linux", ["curl -fsSL https://get.docker.com | sh", "usermod -aG docker", "MINION_BACKEND=local"]),
    ],
)
def test_setup_without_docker_says_how_to_get_it(wizard, capsys, monkeypatch, platform, expected):
    wizard.ready, wizard.detail, wizard.bin = False, "`docker` was not found", "docker"
    monkeypatch.setattr(sys, "platform", platform)
    assert onboard.setup() == 1
    out = capsys.readouterr().out
    assert all(text in out for text in expected), out
    assert wizard.prepared == [] and "[2/3]" not in out  # it stops there


@pytest.mark.parametrize(
    "platform,detail,expected",
    [
        ("darwin", "Cannot connect to the Docker daemon", "open -a Docker"),
        ("win32", "error during connect", "Engine running"),
        ("linux", "Cannot connect to the Docker daemon", "sudo systemctl start docker"),
        ("linux", "permission denied while trying to connect", "usermod -aG docker"),
    ],
)
def test_setup_with_docker_stopped_says_how_to_start_it(
    wizard, capsys, monkeypatch, tmp_path, platform, detail, expected
):
    wizard.ready, wizard.detail = False, detail
    wizard.bin = str(executable(tmp_path / "bin" / f"docker{EXE}"))
    monkeypatch.setattr(sys, "platform", platform)
    assert onboard.setup() == 1
    out = capsys.readouterr().out
    assert expected in out and "not answering" in out and "minion setup" in out


def test_podman_machine_hint(wizard, capsys, monkeypatch, tmp_path):
    wizard.ready, wizard.detail = False, "Cannot connect to Podman"
    wizard.bin = str(executable(tmp_path / "bin" / f"podman{EXE}"))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert onboard.setup() == 1
    assert "podman machine start" in capsys.readouterr().out


def test_pull_progress_is_one_line_on_a_terminal(monkeypatch):
    err = io.StringIO()
    monkeypatch.setattr(sys, "stderr", err)
    progress = onboard.PullProgress("browser", tty=True)
    for line in [
        "0.1: Pulling from apophisss/minion-browser",
        "4f55086f7dd0: Pulling fs layer",
        "d5e71e642bf5: Already exists",
        "4f55086f7dd0: Download complete",
        "4f55086f7dd0: Pull complete",
        "Status: Downloaded newer image",
    ]:
        progress(line)
    out = err.getvalue()
    assert "Downloading browser: 2/2 layers\n" in out and "Pulling from" in out and "Status:" in out
    assert out.count("\n") == 3  # one line for the layers, not one per layer update


def test_cli_registers_setup(monkeypatch):
    args = cli.build_parser().parse_args(["setup", "--profiles", "office,dev", "--yes", "--compact"])
    assert args.fn is cli.cmd_setup and args.yes and args.compact
    seen = {}
    monkeypatch.setattr(onboard, "setup", lambda names, **kw: seen.update(names=names, **kw) or 0)
    assert cli.main(["setup", "--profiles", "office, dev", "-y"]) == 0
    assert seen == {"names": ["office", "dev"], "yes": True, "compact": False}
    assert cli.main(["setup"]) == 0 and seen["names"] is None  # not given: setup asks


@pytest.mark.docker
@pytest.mark.skipif(
    not os.environ.get("MINION_TEST_DOCKER") or not docker_ready(),
    reason="set MINION_TEST_DOCKER=1 with a running Docker daemon",
)
def test_setup_for_real(tmp_path, monkeypatch, capsys):
    """The base image is already there (CI builds it), so this checks Docker and connects nothing."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(connect, "interactive", lambda: False)
    assert onboard.setup(["base"], yes=True) == 0
    out = capsys.readouterr().out
    assert "base is ready" in out and "No agent apps found" in out
