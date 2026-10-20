"""Native transport tests use fake RPC/backends and synthetic mathematical inputs."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from math_research.agent.codex import CodexRPC
from math_research.agent.providers.base import ProviderResponse
from math_research.agent.session import SessionMessage
from math_research.core.errors import ResearchError
from math_research.formalization import executors
from math_research.formalization.agent import ExecutorSelection
from math_research.formalization.executors import (
    APIFormalExecutor,
    CodexFormalExecutor,
    ExecutorIsolationError,
    _DecisionRPC,
)
from math_research.formalization.loop import FormalizationLoop
from test_formalization_agent import FakeProvider, response
from test_formalization_agent import formal as formal


@pytest.fixture
def native_backend(monkeypatch):
    records = []

    class FakeBackend:
        sequence = 0
        usage_value = {"inputTokens": 100, "outputTokens": 20, "cachedInputTokens": 10}
        failure = None
        content = response(("FINISH", {})).content

        def __init__(self, model, effort, **kwargs):
            assert kwargs["tool_free"] is True and kwargs["deadline"] > 0
            self.model_name = model
            self.kwargs = kwargs
            self.usage = self.usage_value.copy()
            self.closed = False
            records.append(self)

        def generate(self, messages, tools=None):
            assert tools is None
            self.messages = messages
            FakeBackend.sequence += 1
            owner = self.kwargs["rpc_factory"].__self__
            event = {
                "method": "thread/start",
                "thread_id": f"fresh-{FakeBackend.sequence}",
                "ephemeral": True,
                "fresh_home": True,
                "empty_environment": True,
            }
            owner.evidence.append(event)
            if owner.event_sink:
                owner.event_sink(event)
            if self.failure:
                raise self.failure
            return ProviderResponse(kind="message", content=self.content, model=self.model_name)

        def close(self):
            self.closed = True

    monkeypatch.setattr(executors, "CodexToolProvider", FakeBackend)
    return FakeBackend, records


def test_configured_native_selection_no_api_fallback(tmp_path, monkeypatch):
    from math_research.app import model_settings
    from math_research.app.workflows import actions
    from math_research.formalization import agent

    monkeypatch.setattr(
        model_settings,
        "resolve_role",
        lambda *args: (_ for _ in ()).throw(ResearchError("missing")),
    )
    monkeypatch.setattr(
        actions,
        "load_research_defaults",
        lambda *args: SimpleNamespace(
            research={"provider": "codex", "model": "configured-native", "reasoning_effort": "high"}
        ),
    )
    monkeypatch.setattr(agent, "select_api_provider", lambda *args: pytest.fail("No API fallback"))
    selected = executors.select_formal_executor(tmp_path)
    assert isinstance(selected.provider, CodexFormalExecutor)
    assert selected.provider.model_name == "configured-native"
    assert selected.metadata["executor"] == "codex native" and not selected.metadata["fallback"]


def test_api_executor_selection_remains_supported(tmp_path, monkeypatch):
    from math_research.app import model_settings
    from math_research.formalization import agent

    provider = FakeProvider([])
    monkeypatch.setattr(model_settings, "resolve_role", lambda *args: (object(), object()))
    monkeypatch.setattr(agent, "select_api_provider", lambda *args: ExecutorSelection(provider, {}))
    selected = executors.select_formal_executor(tmp_path)
    assert isinstance(selected.provider, APIFormalExecutor)
    assert selected.metadata["executor"] == "api"


def make_rpc(monkeypatch, *, contaminated=False):
    calls = []

    def base_call(self, method, params, **kwargs):
        calls.append((method, params))
        if method == "thread/start":
            return {
                "thread": {
                    "id": "new-1",
                    "ephemeral": True,
                    "turns": ["old-context"] if contaminated else [],
                }
            }
        return {}

    monkeypatch.setattr(CodexRPC, "call", base_call)
    rpc = object.__new__(_DecisionRPC)
    rpc.evidence, rpc.fresh_thread, rpc.on_receipt = [], None, None
    return rpc, calls


def test_rpc_requires_fresh_empty_tool_free_thread(monkeypatch):
    rpc, calls = make_rpc(monkeypatch)
    rpc.call("thread/start", {"ephemeral": True, "dynamicTools": [], "environments": []})
    assert calls[0][1]["allowProviderModelFallback"] is False
    assert calls[0][1]["runtimeWorkspaceRoots"] == []
    assert rpc.evidence[0]["fresh_home"]
    rpc.call("turn/start", {"threadId": "new-1", "environments": []})


@pytest.mark.parametrize(
    "method", ["thread/resume", "thread/fork", "command/exec", "thread/read", "thread/inject_items"]
)
def test_no_history_or_unrestricted_executor_rpc(monkeypatch, method):
    rpc, calls = make_rpc(monkeypatch)
    with pytest.raises(ExecutorIsolationError):
        rpc.call(method, {})
    assert not calls


def test_history_in_new_thread_invalidates_context(monkeypatch):
    rpc, _ = make_rpc(monkeypatch, contaminated=True)
    with pytest.raises(ExecutorIsolationError):
        rpc.call("thread/start", {"ephemeral": True, "dynamicTools": [], "environments": []})


@pytest.mark.parametrize(
    "field,value",
    [("ephemeral", False), ("dynamicTools", [{"name": "shell"}]), ("environments", [{}])],
)
def test_native_capabilities_rejected_before_transport(monkeypatch, field, value):
    rpc, calls = make_rpc(monkeypatch)
    params = {"ephemeral": True, "dynamicTools": [], "environments": [], field: value}
    with pytest.raises(ExecutorIsolationError):
        rpc.call("thread/start", params)
    assert not calls


def test_each_decision_is_a_new_thread_and_only_supplied_context(native_backend):
    _, records = native_backend
    executor = CodexFormalExecutor("configured-native", None)
    messages = [
        SessionMessage(role="system", content="Synthetic policy"),
        SessionMessage(role="user", content="Current context only"),
    ]
    executor.generate(messages)
    executor.generate(messages)
    assert executor.fresh_context_confirmed and executor.calls == 2
    assert len({e["thread_id"] for e in executor.evidence}) == 2
    assert all(record.closed and record.messages == messages for record in records)
    assert executor.snapshot()["native_usage"][0]["cached_tokens"] == 10


def test_native_missing_usage_is_null_not_estimated(formal, native_backend):
    backend, _ = native_backend
    backend.usage_value = {}
    tools, _, _ = formal
    state = FormalizationLoop(
        CodexFormalExecutor("configured-native", None), tools, "Synthetic"
    ).run()
    assert state.stop_reason == "CHECKED"
    assert state.input_tokens is None and state.output_tokens is None and not state.tokens_estimated
    usage = json.loads((tools.run_dir / "usage.json").read_text())
    assert usage["input_tokens"] is None and usage["output_tokens"] is None


def test_native_exact_usage_and_structured_actions(formal, native_backend):
    tools, _, _ = formal
    state = FormalizationLoop(
        CodexFormalExecutor("configured-native", "high"), tools, "Synthetic"
    ).run()
    assert state.stop_reason == "CHECKED"
    assert (state.input_tokens, state.output_tokens, state.cached_tokens) == (100, 20, 10)


def test_executor_timeout_is_failure_and_closed(formal, native_backend):
    backend, records = native_backend
    backend.failure = TimeoutError("Synthetic timeout")
    tools, _, _ = formal
    state = FormalizationLoop(
        CodexFormalExecutor("configured-native", None), tools, "Synthetic"
    ).run()
    assert state.stop_reason == "MODEL_FAILURE" and state.model_calls == 1
    assert records[0].closed
    assert state.input_tokens is None


def test_isolation_error_is_explicitly_invalidated(formal, native_backend):
    backend, _ = native_backend
    backend.failure = ExecutorIsolationError("Synthetic context leak")
    tools, _, _ = formal
    state = FormalizationLoop(
        CodexFormalExecutor("configured-native", None), tools, "Synthetic"
    ).run()
    assert state.stop_reason == "INVALIDATED_CONTEXT_LEAKAGE"


def test_resume_restores_audit_only_not_native_thread(formal, native_backend):
    backend, records = native_backend
    backend.content = response(("list_formal_workspace", {})).content
    tools, _, _ = formal
    initial = FormalizationLoop(CodexFormalExecutor("configured-native", None), tools, "Synthetic")
    initial.step()
    backend.content = response(("FINISH", {})).content
    resumed = FormalizationLoop(CodexFormalExecutor("configured-native", None), tools, "Synthetic")
    assert resumed.state.model_calls == 1
    assert resumed.run().stop_reason == "CHECKED"
    assert resumed.state.model_calls == 2
    assert len(records) == 2 and all(r.closed for r in records)


def test_thread_only_preflight_does_not_start_inference(tmp_path, monkeypatch):
    import tomllib

    from math_research.agent import codex
    from math_research.agent.transport import CodexCLIExecutor

    temporary = codex.tempfile.TemporaryDirectory
    monkeypatch.setattr(
        codex.tempfile, "TemporaryDirectory", lambda **kwargs: temporary(dir=tmp_path, **kwargs)
    )

    original = tmp_path / "original-home"
    original.mkdir()
    (original / "auth.json").write_text("synthetic-auth", encoding="utf-8")
    monkeypatch.setattr(codex, "_codex_env", lambda: {"CODEX_HOME": str(original)})
    monkeypatch.setattr(CodexCLIExecutor, "preflight", lambda *args, **kwargs: "synthetic-cli")
    methods = []

    class RPC:
        def __init__(self, folder, *, env, **kwargs):
            home = __import__("pathlib").Path(env["CODEX_HOME"])
            assert home != original
            config = tomllib.loads((home / "config.toml").read_text("utf-8"))
            assert config["features"]["shell_tool"] is False
            assert config["features"]["unified_exec"] is False
            assert config["features"]["memories"] is False

        def call(self, method, params):
            methods.append(method)
            assert params["ephemeral"] and params["environments"] == []
            assert params["dynamicTools"] == []
            return {"thread": {"id": "fresh", "ephemeral": True}, "model": "synthetic-native"}

        def close(self):
            pass

    backend = codex.CodexToolProvider(
        "synthetic-native",
        None,
        deadline=1e30,
        should_stop=lambda: False,
        tool_free=True,
        rpc_factory=RPC,
    )
    backend._start([SessionMessage(role="system", content="Synthetic")], [], start_turn=False)
    assert methods == ["thread/start"]
    backend.close()
