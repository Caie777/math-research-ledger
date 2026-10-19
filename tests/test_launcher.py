"""No browser/model is launched. Startup uses synthetic roots and fake servers."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts import start_web as launcher

from math_research.app.api.runs import workspace_identity


def test_root_is_script_relative():
    assert launcher.repo_root() == Path(launcher.__file__).resolve().parent.parent
    batch = (launcher.repo_root() / "start.bat").read_text()
    assert "%~dp0" in batch and "pause" in batch


def test_frontend_build_and_failure(tmp_path, monkeypatch):
    root = tmp_path / "repo with spaces"
    web = root / "web"
    (web / "node_modules").mkdir(parents=True)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: name)

    def build(args, *, cwd, check, interactive):
        assert interactive
        assert cwd == web and args[1:] == ["run", "build"]
        (web / "dist").mkdir()
        (web / "dist/index.html").write_text("built")
        return SimpleNamespace(returncode=0)

    fake = Mock(side_effect=build)
    monkeypatch.setattr("math_research.core.process.run_process", fake)
    launcher.build_frontend(root)
    launcher.build_frontend(root)
    assert fake.call_count == 1
    (web / "dist/index.html").unlink()
    fake.side_effect = lambda *a, **k: SimpleNamespace(returncode=1)
    with pytest.raises(RuntimeError, match="Frontend build failed"):
        launcher.build_frontend(root)


def test_missing_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Node.js/npm missing"):
        launcher.build_frontend(tmp_path)


def test_health_retries_and_backend_failure(monkeypatch):
    monkeypatch.setattr(launcher, "health", Mock(side_effect=[None, {"workspace_identity": "id"}]))
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    launcher.wait_ready("http://fake", "id", SimpleNamespace(is_alive=lambda: True))
    monkeypatch.setattr(launcher, "health", lambda _: None)
    with pytest.raises(RuntimeError, match="Backend stopped"):
        launcher.wait_ready("http://fake", "id", SimpleNamespace(is_alive=lambda: False))
    with pytest.raises(RuntimeError, match="timed out"):
        launcher.wait_ready("http://fake", "id", SimpleNamespace(is_alive=lambda: True), timeout=0)


def test_occupied_unrelated_port_does_not_launch_or_open(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "port_available", lambda _: False)
    monkeypatch.setattr(launcher, "health", lambda _: {"workspace_identity": "foreign"})
    browser, builder = Mock(), Mock()
    with pytest.raises(RuntimeError, match="occupied"):
        launcher.launch(tmp_path, open_browser=browser, builder=builder)
    browser.assert_not_called()
    builder.assert_not_called()


def test_existing_workspace_reuses_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "port_available", lambda _: False)
    monkeypatch.setattr(
        launcher,
        "health",
        lambda _: {"workspace_identity": workspace_identity(tmp_path / ".math-research")},
    )
    response = Mock()
    response.headers = {"Content-Type": "text/html"}
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock()
    monkeypatch.setattr(launcher.urllib.request, "urlopen", lambda *a, **k: response)
    browser, builder = Mock(), Mock()
    launcher.launch(tmp_path, open_browser=browser, builder=builder)
    browser.assert_called_once_with("http://127.0.0.1:8000")
    builder.assert_not_called()


@pytest.mark.parametrize("interrupt", [True, False])
def test_server_ready_browser_and_cleanup(tmp_path, monkeypatch, interrupt):
    monkeypatch.setattr(launcher, "port_available", lambda _: True)
    ready = threading.Event()

    class Server:
        should_exit = False

        def run(self):
            ready.set()
            while not self.should_exit:
                threading.Event().wait(0.01)

    server = Server()

    def wait(*args):
        assert ready.wait(1)
        if not interrupt:
            raise RuntimeError("Backend health timed out")

    monkeypatch.setattr(launcher, "wait_ready", wait)
    browser = Mock(side_effect=KeyboardInterrupt)
    builder = Mock()
    with pytest.raises(KeyboardInterrupt if interrupt else RuntimeError):
        launcher.launch(
            tmp_path / "path with spaces",
            open_browser=browser,
            builder=builder,
            server_factory=lambda app, port: server,
        )
    assert server.should_exit
    assert not any(t.name == "local-web" and t.is_alive() for t in threading.enumerate())
    assert browser.call_count == int(interrupt)


def test_frontend_failure_prevents_backend_and_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "port_available", lambda _: True)
    browser, backend = Mock(), Mock()
    with pytest.raises(RuntimeError, match="Frontend"):
        launcher.launch(
            tmp_path,
            builder=Mock(side_effect=RuntimeError("Frontend failed")),
            open_browser=browser,
            server_factory=backend,
        )
    browser.assert_not_called()
    backend.assert_not_called()
