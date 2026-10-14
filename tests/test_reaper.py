"""The idle reaper freezes idle desktops and must never be the one that wakes a desktop up."""

from types import SimpleNamespace

import pytest

from minion import reaper


class Stop(BaseException):
    pass


class FakeChannel:
    def __init__(self, status):
        self.status = status

    def call(self, method, params=None, timeout=None):
        assert method == "status"
        return self.status

    def close(self):
        pass


class FakeBackend:
    name = "fake"

    def __init__(self, desktops):
        self.desktops = desktops  # name -> (state, status)
        self.events = []

    def list(self, stats=False):
        return [SimpleNamespace(name=n, state=s) for n, (s, _) in self.desktops.items()]

    def ensure_awake(self, name):
        self.events.append(("wake", name))

    def channel(self, name):
        return FakeChannel(self.desktops[name][1])

    def freeze(self, name):
        self.events.append(("freeze", name))

    def stop(self, name):
        self.events.append(("stop", name))


def run_once(backend, monkeypatch, threshold=600):
    ticks = iter([None])

    def sleep(_):
        if next(ticks, "done") == "done":
            raise Stop

    monkeypatch.setattr(reaper.time, "sleep", sleep)
    monkeypatch.setattr(reaper, "_say", lambda text: None)
    with pytest.raises(Stop):
        reaper._loop(backend, threshold, 1)


def test_freezes_idle_desktops_without_waking_any(monkeypatch):
    backend = FakeBackend(
        {
            "idle": ("running", {"idle": 900, "viewed": 900}),
            "busy": ("running", {"idle": 900, "viewed": 900, "inflight": 1}),
            "watched": ("running", {"idle": 900, "viewed": 5}),
            "frozen": ("paused", {}),
        }
    )
    run_once(backend, monkeypatch)
    assert backend.events == [("freeze", "idle")]  # no ("wake", ...) for anyone
