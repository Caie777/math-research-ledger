"""Small public contract suite: Episode → reviewed memory → retrieval/context."""

import hashlib
import threading
from pathlib import Path

import pytest

from math_research.agent.model import ModelConfigurationRequired, get_role_provider
from math_research.agent.progress import read_progress
from math_research.agent.providers.base import BaseProvider, ProviderResponse
from math_research.agent.runtime import execute_run, prepare_run, run_directory
from math_research.app import model_settings
from math_research.ledger.episodes import list_candidates, list_episodes, review_candidate
from math_research.ledger.records import store
from math_research.ledger.state import KnowledgeStateResolver
from math_research.retrieval.context import ResearchContextBuilder
from math_research.retrieval.recall import ResearchRecall

HEADERS = {"X-Research-IDE": "1"}


def snapshot(root: Path) -> dict:
    return {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()
    }


def import_demo(workspace, demo):
    ot, request, client = workspace
    base = f"/api/problems/{request.target.problem_id}/episodes"
    preview = client.post(base + "/preflight", files={"file": ("demo.md", demo)}, headers=HEADERS)
    assert preview.status_code == 200, preview.text
    committed = client.post(
        base + "/import",
        files={"file": ("demo.md", demo)},
        data={"digest": preview.json()["content_sha256"]},
        headers=HEADERS,
    )
    assert committed.status_code == 200, committed.text
    return committed.json()


def test_episode_preview_parser_import_and_duplicate(workspace, demo):
    ot, request, client = workspace
    before = snapshot(ot)
    base = f"/api/problems/{request.target.problem_id}/episodes"
    preview = client.post(base + "/preflight", files={"file": ("demo.txt", demo)}, headers=HEADERS)
    assert preview.status_code == 200
    assert preview.json()["parse_summary"] == {"claim": 1, "proof": 1, "gap": 1, "relation": 1}
    assert snapshot(ot) == before
    changed = client.post(
        base + "/import",
        files={"file": ("demo.md", demo + b"changed")},
        data={"digest": preview.json()["content_sha256"]},
        headers=HEADERS,
    )
    assert changed.status_code == 409 and snapshot(ot) == before
    first = import_demo(workspace, demo)
    assert first["summary"]["canonical_records_created"] == 0
    second = import_demo(workspace, demo)
    assert second["duplicate"] and second["summary"]["records_created"] == 0
    assert len(list_episodes(ot)) == 1 and len(list_candidates(ot, request.target.problem_id)) == 4


def test_malformed_episode_has_no_writes(workspace):
    ot, request, client = workspace
    before = snapshot(ot)
    result = client.post(
        f"/api/problems/{request.target.problem_id}/episodes/preflight",
        files={"file": ("invalid.md", b"not an Episode")},
        headers=HEADERS,
    )
    assert result.status_code == 400 and snapshot(ot) == before


def test_review_controls_canonical_memory_and_state(workspace, demo):
    ot, request, _ = workspace
    import_demo(workspace, demo)
    pid = request.target.problem_id
    candidate = next(c for c in list_candidates(ot, pid) if c.kind == "claim")
    assert (
        KnowledgeStateResolver(ot).resolve(pid)[candidate.candidate_id].authority == "PROVISIONAL"
    )
    assert len(store.list_claims(ot, pid)) == 1
    decision = review_candidate(ot, pid, candidate.candidate_id, "accept")
    assert decision.mapped_id and len(store.list_claims(ot, pid)) == 2
    assert KnowledgeStateResolver(ot).resolve(pid)[decision.mapped_id].authority == "CANONICAL"


def test_retrieval_context_is_bounded_and_read_only(workspace, demo):
    ot, request, _ = workspace
    import_demo(workspace, demo)
    before = snapshot(ot)
    found = ResearchRecall(ot, request.target.problem_id).find_files(query="square identity")
    assert found.files
    context = ResearchContextBuilder(ot).build(request.target, token_budget=2000)
    assert request.target.node_id in {item.object_id for item in context.items}
    assert context.token_estimate <= 2000 and snapshot(ot) == before


@pytest.mark.parametrize("message", ["/portfolio", "/state P1", "/recall square", "/import"])
def test_deterministic_coordinator_needs_no_model(workspace, monkeypatch, message):
    ot, request, client = workspace
    monkeypatch.setattr(
        "math_research.app.workflows.coordinator.get_role_provider",
        lambda *a, **k: pytest.fail("deterministic model call"),
    )
    before = snapshot(ot)
    result = client.post(
        "/api/coordinator",
        json={"message": message, "selected_problem_id": request.target.problem_id},
        headers=HEADERS,
    )
    assert result.status_code == 200
    assert result.json()["kind"] in {"QUERY_RESULT", "ACTION_RESULT"}
    assert not result.json()["model_used"] and snapshot(ot) == before


def test_missing_roles_are_typed_and_do_not_create_runs(workspace):
    ot, request, client = workspace
    before = snapshot(ot)
    missing = client.post(
        "/api/coordinator", json={"message": "Summarize the best next direction"}, headers=HEADERS
    ).json()
    assert missing["kind"] == "CONFIG_REQUIRED"
    result = client.post(
        f"/api/problems/{request.target.problem_id}/research-runs?entry=web",
        json=request.model_dump(mode="json"),
        headers=HEADERS,
    )
    assert result.status_code == 409 and result.json()["detail"]["role"] == "research"
    assert snapshot(ot) == before


def test_settings_write_only_validation_and_role_registry(workspace, monkeypatch):
    ot, _, client = workspace
    fake_key = "synthetic-test-key"
    update = {
        "roles": {
            name: {"provider": "openai", "model": "synthetic-model", "enabled": True}
            for name in model_settings.ModelRoles.model_fields
        },
        "credentials": {"openai": fake_key},
    }
    before = snapshot(ot)
    saved = client.put("/api/settings/models", json=update, headers=HEADERS)
    assert saved.status_code == 200 and fake_key not in saved.text
    assert client.get("/api/settings/models").json()["status"]["research"] == "configured"

    class Fake(BaseProvider):
        name = "openai"

        def generate(self, messages, tools=None):
            return ProviderResponse(kind="message", content="fake")

    def factory(config):
        assert config.model.name == "synthetic-model"
        assert config._api_key.get_secret_value() == fake_key
        assert fake_key not in config.to_yaml()
        return Fake()

    monkeypatch.setattr(model_settings, "get_provider", factory)
    assert get_role_provider(ot, model_role="research").generate([]).content == "fake"
    update["roles"]["research"]["provider"] = "imaginary"
    invalid = client.put("/api/settings/models", json=update, headers=HEADERS)
    assert invalid.status_code == 422 and fake_key not in invalid.text
    update["roles"]["research"]["provider"] = "openai"
    update["credentials"]["openai"] = ""
    client.put("/api/settings/models", json=update, headers=HEADERS)
    with pytest.raises(ModelConfigurationRequired):
        get_role_provider(ot, model_role="research")
    assert snapshot(ot) == before


def test_fake_final_episode_and_progress_share_memory_pipeline(workspace):
    ot, request, _ = workspace

    class Fake(BaseProvider):
        name = "mock"

        def generate(self, messages, tools=None):
            return ProviderResponse(
                kind="message", content="## GAP-1\n\n**Gap**\n\nSynthetic open question."
            )

    run = execute_run(ot, prepare_run(ot, request), provider=Fake())
    progress = read_progress(run_directory(ot, run.run_id), run)
    assert run.status == "finished" and progress.status == "finished"
    assert progress.model_call_count > 0 and progress.stop_reason == run.stop_reason
    assert run.episode_id and list_candidates(ot, request.target.problem_id, run.episode_id)
    assert len(store.list_claims(ot, request.target.problem_id)) == 1


def test_start_stop_fake_run_through_coordinator_and_original_executor(workspace, monkeypatch):
    ot, request, client = workspace
    model_settings.save_settings(
        ot,
        model_settings.SettingsUpdate.model_validate(
            {"roles": {"research": {"provider": "ollama", "model": "synthetic", "enabled": True}}}
        ),
    )
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    class Fake(BaseProvider):
        name = "mock"

        def generate(self, messages, tools=None):
            return ProviderResponse(kind="message", content="## GAP-1\n\n**Gap**\n\nSynthetic gap.")

    def fake_execute(state, run, *, cancel, provider=None):
        entered.set()
        assert release.wait(5)
        result = execute_run(state, run, cancel=cancel, provider=Fake())
        finished.set()
        return result

    monkeypatch.setattr("math_research.app.api.runs.execute_run", fake_execute)
    started = client.post("/api/coordinator", json={"message": "/start P1"}, headers=HEADERS).json()
    try:
        assert started["kind"] == "ACTION_RESULT" and entered.wait(1)
        stopped = client.post(
            "/api/coordinator", json={"message": "/stop " + started["run_id"]}, headers=HEADERS
        ).json()
        assert stopped["structured_payload"]["stop_requested"]
    finally:
        release.set()
    assert finished.wait(5)
    polled = client.get(
        f"/api/problems/{request.target.problem_id}/research-runs/{started['run_id']}"
    )
    assert polled.json()["stop_reason"] == "USER_STOP"


def test_public_api_is_same_origin_and_launcher_is_repo_relative():
    import re

    root = Path(__file__).resolve().parents[1]
    api = (root / "web/src/api.ts").read_text(encoding="utf-8")
    assert not re.search(r"https?://", api)
    batch = (root / "start.bat").read_text()
    assert "%~dp0" in batch
    launcher = (root / "scripts/start_web.py").read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in launcher
    for area in (root / "src", root / "web/src", root / "scripts"):
        for path in area.rglob("*"):
            if path.suffix in {".py", ".ts", ".tsx"}:
                assert not re.search(
                    r"[A-Z]:[\\/](?:Users|Projects)[\\/]", path.read_text(encoding="utf-8")
                )


def test_local_data_and_credentials_are_ignored():
    root = Path(__file__).resolve().parents[1]
    ignore = (root / ".gitignore").read_text()
    for rule in (
        ".math-research/",
        ".local/",
        ".local-eval/",
        ".venv",
        "node_modules/",
        "web/dist/",
        "*.xml",
        ".env",
        "!.env.example",
    ):
        assert rule in ignore
