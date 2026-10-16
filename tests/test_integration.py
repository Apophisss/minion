"""Real desktops. Local: needs Xvfb & co (pytest -m x11). Docker: needs a daemon and an image
(pytest -m docker; MINION_TEST_PROFILE picks the profile, default base)."""

import os
import time

import pytest
from conftest import docker_ready, x11_ready

from minion import Desktop


def exercise(desk: Desktop) -> None:
    hello = desk.hello()
    assert hello["screen"] == [1024, 768]
    shot = desk.screenshot()
    assert (shot.width, shot.height) == (1024, 768) and shot.data[:4] == b"\x89PNG"
    small = desk.screenshot(max_width=512)
    assert small.width == 512 and small.to_screen(256, 192) == (512, 384)

    res = desk.open("terminal")
    assert res["window"], res
    obs = desk.see()
    assert "window" in obs.text.lower()

    act = desk.act({"type": "echo minion-ok\n"}, screenshot=True)
    assert act.ok and act.screenshot is not None

    run = desk.run("echo $((6*7)) && whoami")
    assert run.ok and run.stdout.split()[0] == "42"

    desk.clipboard = "clip ✓"
    assert desk.clipboard == "clip ✓"

    desk.write_text("~/minion-test.txt", "héllo")
    assert desk.read_text("~/minion-test.txt") == "héllo"
    listing = desk.ls("~")  # (the live view's Files panel)
    assert "minion-test.txt" in [e["name"] for e in listing["entries"]] and listing["home"]

    bad = desk.act({"click": "@9999"}, check=False)
    assert not bad.ok and "unknown" in bad.summary

    html = desk.recording("html")
    assert "<html" in html and "act" in html


@pytest.mark.x11
@pytest.mark.skipif(not x11_ready(), reason="local desktop tools are not installed")
def test_local_backend_end_to_end(tmp_path, monkeypatch):
    desk = Desktop.create("base", name="itest", size="1024x768", backend="local")
    try:
        exercise(desk)
        desk.freeze()
        assert desk.info().state == "paused"
        assert desk.hello()["screen"] == [1024, 768]  # thawed automatically
        tag = desk.snapshot("one")
        fork = desk.fork("itest-fork")
        try:
            assert fork.read_text("~/minion-test.txt") == "héllo"
        finally:
            fork.remove()
        desk.restore(tag)
        assert desk.read_text("~/minion-test.txt") == "héllo"
    finally:
        desk.remove()


@pytest.mark.docker
@pytest.mark.skipif(
    not os.environ.get("MINION_TEST_DOCKER") or not docker_ready(),
    reason="set MINION_TEST_DOCKER=1 with a running Docker daemon",
)
def test_docker_backend_end_to_end():
    profile = os.environ.get("MINION_TEST_PROFILE", "base")
    t0 = time.time()
    desk = Desktop.create(profile, name="itest-docker", size="1024x768", backend="docker")
    try:
        assert time.time() - t0 < 120
        exercise(desk)
        desk.freeze()
        assert desk.info().state == "paused"
        assert desk.run("echo awake").stdout.strip() == "awake"
        fork = desk.fork("itest-docker-fork")
        try:
            assert fork.read_text("~/minion-test.txt") == "héllo"
        finally:
            fork.remove()
        saved = desk.save_login("itest-login", site="itest")  # a sign-in: new desktops start as this one is
        try:
            assert saved.profile == profile and "itest-login" in [x.name for x in Desktop.logins("docker")]
            signed = Desktop.create(login="itest-login", name="itest-docker-signed", backend="docker")
            try:
                assert signed.info().profile == profile and signed.read_text("~/minion-test.txt") == "héllo"
            finally:
                signed.remove()
        finally:
            Desktop.remove_login("itest-login", "docker")
        assert "itest-login" not in [x.name for x in Desktop.logins("docker")]
    finally:
        desk.remove()
