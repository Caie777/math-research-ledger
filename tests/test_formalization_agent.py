from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from math_research.agent.providers.base import BaseProvider, ProviderResponse, TokenUsage
from math_research.formalization.agent import APISelection, FormalBudget, FormalRunState
from math_research.formalization.benchmark import execute_benchmark, seal_run
from math_research.formalization.checker import CommandResult, LeanChecker
from math_research.formalization.diagnostics import extract_diagnostics
from math_research.formalization.freeze import freeze, frozen_source, hash_bytes
from math_research.formalization.loop import FormalizationLoop
from math_research.formalization.tools import FormalTools
from math_research.formalization.workspace import FormalWorkspace

PROOF = "WeakSchottky/Proofs/Target.lean"
ERROR = "error: WeakSchottky/Proofs/Target.lean:3:4: Unknown identifier `synthetic`\n⊢ True\n"
PROBE = "Bench.target : True\n'Bench.target' depends on axioms: [propext]\n"


class FakeProvider(BaseProvider):
    name = "fake-api"
    model_name = "synthetic-model"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def generate(self, messages, tools=None):
        assert tools is None
        self.messages.append(messages)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def response(*actions, usage=True):
    return ProviderResponse(
        kind="message",
        content=json.dumps(
            {
                "summary": "Synthetic test action",
                "actions": [{"tool": tool, "arguments": args} for tool, args in actions],
            }
        ),
        usage=TokenUsage(prompt_tokens=100, completion_tokens=20) if usage else None,
        model="synthetic-model",
    )


@pytest.fixture
def formal(tmp_path, monkeypatch):
    repo = tmp_path / "eval"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "lean-toolchain").write_text("leanprover/lean4:v4.35.0\n", encoding="utf-8")
    (repo / "lake-manifest.json").write_text(
        json.dumps({"packages": [{"name": "mathlib", "inputRev": "v4.35.0", "rev": "b" * 40}]}),
        encoding="utf-8",
    )
    (repo / "lakefile.toml").write_text('name = "test"\n', encoding="utf-8")
    (repo / "Statement.lean").write_text(
        "def syntheticStatement : Prop := True\n", encoding="utf-8"
    )
    (repo / "Definition.lean").write_text("def syntheticDefinition : Nat := 1\n", encoding="utf-8")
    (repo / "WeakSchottky.lean").write_text("import WeakSchottky.Proofs.Target\n", encoding="utf-8")
    proof = repo / PROOF
    proof.parent.mkdir(parents=True)
    proof.write_bytes(b"import Statement\n")
    mathlib = repo / ".lake/packages/mathlib/Mathlib"
    mathlib.mkdir(parents=True)
    (mathlib / "Synthetic.lean").write_text(
        "lemma synthetic_lookup : True := by trivial\n", encoding="utf-8"
    )
    frozen = freeze(repo, "Statement.lean", ("Definition.lean",), tmp_path / "freezes")
    frozen = frozen.model_copy(
        update={"dependencies": (*frozen.dependencies, frozen_source(repo, "WeakSchottky.lean"))}
    )
    run = tmp_path / "run"
    workspace = FormalWorkspace(repo, frozen, run / "access-audit.jsonl")
    lake = tmp_path / "lake.exe"
    lake.touch()
    checker = LeanChecker(lake)
    results = []
    calls = []

    def compile(arguments, root, env, log, input_text=None):
        calls.append(arguments)
        assert env["ELAN_HOME"]
        result = results.pop(0) if results else CommandResult(0, PROBE if input_text else "built\n")
        log.write(result.output.encode("utf-8"))
        return result

    monkeypatch.setattr(checker, "_run", compile)
    tools = FormalTools(workspace, checker, run, "WeakSchottky.Proofs.Target", "Bench.target")
    return tools, results, calls


@pytest.mark.parametrize(
    "path",
    [
        "Statement.lean",
        "Definition.lean",
        "lean-toolchain",
        "lakefile.toml",
        "lake-manifest.json",
        "WeakSchottky.lean",
        "../escape.lean",
        "WeakSchottky/Proofs/../../Statement.lean",
        r"D:\Projects\formalizations\weak-schottky\WeakSchottky\Lemma41Proof.lean",
    ],
)
def test_forbidden_writes_are_audited(formal, path):
    tools, _, _ = formal
    with pytest.raises(ValueError):
        tools.workspace.write_proof_file(path, "synthetic")
    events = [json.loads(line) for line in tools.workspace.audit.read_text("utf-8").splitlines()]
    assert events[-1]["allowed"] is False
    assert events[-1]["operation"] == "write"


def test_file_tools_and_atomic_write(formal):
    tools, _, _ = formal
    workspace = tools.workspace
    assert workspace.write_proof_file(PROOF, "theorem synthetic : True := by trivial\n")
    assert not workspace.write_proof_file(PROOF, "theorem synthetic : True := by trivial\n")
    assert "synthetic" in workspace.read_formal_file(PROOF)
    assert PROOF in workspace.list_formal_workspace()
    assert not list((workspace.root / PROOF).parent.glob("*.tmp"))
    with pytest.raises(ValueError):
        workspace.read_formal_file("../baseline.lean")


def test_mathlib_tools_are_rooted(formal):
    tools, _, _ = formal
    assert tools.workspace.search_mathlib("synthetic_lookup")[0]["path"] == "Synthetic.lean"
    assert "synthetic_lookup" in tools.workspace.read_mathlib_source("Synthetic.lean")
    with pytest.raises(ValueError):
        tools.workspace.read_mathlib_source("../../../../Statement.lean")


def test_symlink_escape_is_rejected(formal, tmp_path, monkeypatch):
    tools, _, _ = formal
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.lean").write_text("outside", encoding="utf-8")
    link = tools.workspace.root / "WeakSchottky/Helpers"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        original = Path.is_symlink
        # Windows without link privileges: exercise the same metadata boundary deterministically.
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == link or original(path))
    with pytest.raises(ValueError):
        tools.workspace.write_proof_file("WeakSchottky/Helpers/secret.lean", "changed")
    assert (outside / "secret.lean").read_text() == "outside"


def test_junction_escape_is_rejected(formal, monkeypatch):
    tools, _, _ = formal
    # Simulate Windows junction detection without requiring elevated OS link privileges.
    monkeypatch.setattr(os.path, "isjunction", lambda p: Path(p).name == "Helpers", raising=False)
    with pytest.raises(ValueError):
        tools.workspace.write_proof_file("WeakSchottky/Helpers/x.lean", "changed")


@pytest.mark.parametrize("source", ["#eval IO.println 1", "run_tac x", "unsafe def x := 1"])
def test_source_cannot_bypass_file_tools(formal, source):
    tools, _, _ = formal
    with pytest.raises(ValueError):
        tools.workspace.write_proof_file(PROOF, source)


def test_diagnostics_preserve_goals_and_stable_error_signature():
    parsed = extract_diagnostics(ERROR)
    assert (parsed[0].file, parsed[0].line, parsed[0].column, parsed[0].severity) == (
        PROOF,
        3,
        4,
        "error",
    )
    assert "⊢ True" in parsed[0].context
    assert parsed[0].signature == extract_diagnostics(ERROR.replace(":3:4:", ":9:8:"))[0].signature
    assert extract_diagnostics("error: build failed")[0].severity == "error"


def test_build_failure_success_and_repeated_hash(formal):
    tools, results, calls = formal
    state = FormalRunState(run_id="test")
    results.append(CommandResult(1, ERROR))
    assert not tools.run_lean_build(state)["build_ok"]
    assert state.diagnostics[0].context
    assert tools.run_lean_build(state)["unchanged"]
    assert len(calls) == 1
    tools.workspace.write_proof_file(PROOF, "theorem synthetic : True := by trivial\n")
    assert tools.run_lean_build(state)["build_ok"]
    assert "synthetic" in state.successful_helper_facts


def test_v0_target_checker_wrapper(formal):
    tools, _, _ = formal
    state = FormalRunState(run_id="test")
    assert tools.check_target(state)["status"] == "checked"
    assert state.stop_reason == "CHECKED"
    assert state.build_count == state.target_checks == 1


def test_target_contract_is_derived_without_a_proof_and_checked(formal, monkeypatch):
    from math_research.formalization.benchmark import statement_contract

    # Synthetic predicate only: no Lemma 4.1 proof or strategy is supplied by this test.
    source = "namespace Synthetic\ndef predicate (x : ℕ) : Prop := x = x\nend Synthetic\n"
    contract = statement_contract(source)
    assert contract == "∀ (x : ℕ), Synthetic.predicate x"
    tools, _, _ = formal
    tools.target_type = contract
    captured = []

    def compile(arguments, root, env, log, input_text=None):
        if input_text:
            captured.append(input_text)
            return CommandResult(1, PROBE + "error: type mismatch\n")
        return CommandResult(0, "built")

    monkeypatch.setattr(tools.checker, "_run", compile)
    state = FormalRunState(run_id="synthetic-type-mismatch")
    assert tools.check_target(state)["status"] == "provisional_formal"
    assert state.stop_reason is None
    assert "#check (Bench.target : ∀ (x : ℕ), Synthetic.predicate x)" in captured[0]


def test_type_contract_cannot_inject_lean_commands(formal):
    tools, _, calls = formal
    with pytest.raises(ValueError):
        tools.checker.check(
            tools.workspace.root,
            "Synthetic",
            "Bench.target",
            tools.workspace.frozen,
            tools.run_dir / "injected.log",
            expected_type="True\n#eval IO.println 1",
        )
    assert not calls


def test_edit_compile_error_repair_and_exact_check(formal):
    tools, results, _ = formal
    results.extend([CommandResult(1, ERROR), CommandResult(0, "built")])
    provider = FakeProvider(
        [
            response(
                ("write_proof_file", {"path": PROOF, "content": "example : True := by synthetic\n"})
            ),
            response(
                (
                    "write_proof_file",
                    {"path": PROOF, "content": "theorem target : True := by trivial\n"},
                ),
                ("FINISH", {}),
            ),
        ]
    )
    loop = FormalizationLoop(provider, tools, "Synthetic informal target")
    state = loop.run()
    assert state.stop_reason == "CHECKED"
    assert state.model_calls == 2 and state.build_count == 3 and state.target_checks == 1
    assert (state.input_tokens, state.output_tokens) == (200, 40)
    assert "Unknown identifier" in provider.messages[1][1].content
    assert "formalization-spike-v0" not in provider.messages[0][1].content
    assert (tools.run_dir / "usage.json").is_file()


def test_repeated_error_gets_one_reflection_then_stops(formal):
    tools, results, _ = formal
    results.extend([CommandResult(1, ERROR) for _ in range(4)])
    provider = FakeProvider(
        [
            response(
                (
                    "write_proof_file",
                    {"path": PROOF, "content": f"example : True := by synthetic\n-- attempt {i}\n"},
                )
            )
            for i in range(4)
        ]
    )
    state = FormalizationLoop(provider, tools, "Synthetic").run()
    assert state.stop_reason == "NO_PROGRESS"
    assert state.model_calls == 4
    assert state.reflection_used
    assert "No progress detected" in provider.messages[-1][1].content


def test_empty_edit_stops_after_reflection(formal):
    tools, _, _ = formal
    action = ("write_proof_file", {"path": PROOF, "content": "import Statement\n"})
    state = FormalizationLoop(
        FakeProvider([response(action), response(action)]), tools, "Synthetic"
    ).run()
    assert state.stop_reason == "NO_PROGRESS" and state.build_count == 0


def test_looping_lookup_stops(formal):
    tools, _, _ = formal
    state = FormalizationLoop(
        FakeProvider([response(("search_mathlib", {"query": "synthetic"})) for _ in range(4)]),
        tools,
        "Synthetic",
    ).run()
    assert state.stop_reason == "NO_PROGRESS"
    assert "LOOPING_ACTION" in state.no_progress_events


@pytest.mark.parametrize("mode", ["calls", "tokens", "builds", "targets"])
def test_budgets_are_hard_limits(formal, mode):
    tools, _, _ = formal
    budget = FormalBudget(model_calls=1)
    provider = FakeProvider([response(("list_formal_workspace", {}))])
    loop = FormalizationLoop(provider, tools, "Synthetic", budget=budget)
    if mode == "tokens":
        loop.state.input_tokens = loop.state.budget.total_tokens
    if mode == "builds":
        loop.state.build_count = loop.state.budget.builds
        provider = FakeProvider([response(("run_lean_build", {}))])
        loop.provider = provider
    if mode == "targets":
        loop.state.target_checks = loop.state.budget.target_checks
        loop.provider = FakeProvider([response(("FINISH", {}))])
    assert loop.run().stop_reason == "BUDGET_EXHAUSTED"


def test_model_failure_never_persists_sdk_secret(formal):
    tools, _, _ = formal
    state = FormalizationLoop(
        FakeProvider([RuntimeError("secret-api-token")]), tools, "Synthetic"
    ).run()
    assert state.stop_reason == "MODEL_FAILURE"
    assert "secret-api-token" not in (tools.run_dir / "agent-events.jsonl").read_text()


def test_malformed_response_and_estimated_usage(formal):
    tools, _, _ = formal
    bad = ProviderResponse(kind="message", content="not json")
    state = FormalizationLoop(FakeProvider([bad, bad]), tools, "Synthetic").run()
    assert state.stop_reason == "MODEL_FAILURE"
    assert state.malformed_responses == 2 and state.tokens_estimated


def test_resume_retains_state_budgets_and_diagnostics(formal):
    tools, results, _ = formal
    results.append(CommandResult(1, ERROR))
    first = FormalizationLoop(FakeProvider([response(("run_lean_build", {}))]), tools, "Synthetic")
    first.step()
    resumed = FormalizationLoop(FakeProvider([response(("FINISH", {}))]), tools, "Synthetic")
    assert resumed.state.model_calls == 1 and resumed.state.diagnostics
    assert resumed.run().stop_reason == "CHECKED"
    assert resumed.state.model_calls == 2


def test_codex_provider_is_rejected(formal):
    tools, _, _ = formal
    provider = FakeProvider([])
    provider.name = "codex"
    with pytest.raises(ValueError):
        FormalizationLoop(provider, tools, "Synthetic")


def test_selection_does_not_fallback_to_codex(tmp_path, monkeypatch):
    from math_research.core.errors import ResearchError
    from math_research.formalization import agent

    monkeypatch.setattr(
        agent, "resolve_role", lambda *args: (_ for _ in ()).throw(ResearchError("missing"))
    )

    class Defaults:
        research = {"provider": "codex", "model": "native-only"}

    monkeypatch.setattr(agent, "load_research_defaults", lambda *args: Defaults())
    monkeypatch.setattr(
        agent, "get_provider", lambda *args: pytest.fail("Native fallback forbidden")
    )
    selected = agent.select_api_provider(tmp_path)
    assert selected.provider is None
    assert selected.metadata["status"] == "BLOCKED_API_CONFIGURATION"


def test_configured_api_role_uses_existing_adapter(tmp_path, monkeypatch):
    from math_research.app.model_settings import RoleSettings
    from math_research.formalization import agent

    provider = FakeProvider([])
    settings = RoleSettings(enabled=True, provider="openai", model="configured-api")
    monkeypatch.setattr(agent, "resolve_role", lambda *args: (settings, None))
    monkeypatch.setattr(agent, "role_provider", lambda *args: provider)
    selected = agent.select_api_provider(tmp_path)
    assert selected.provider is provider and selected.metadata["model"] == "configured-api"


def test_terminal_run_seal_blocks_resume(formal):
    tools, _, _ = formal
    state = FormalRunState(run_id="test", stop_reason="BUDGET_EXHAUSTED")
    tools.persist(state)
    digest = seal_run(tools.run_dir)
    seal = tools.run_dir / "run-freeze.json"
    assert hash_bytes(seal.read_bytes()) == digest
    with pytest.raises(ValueError):
        tools.persist(state)
    with pytest.raises(FileExistsError):
        seal_run(tools.run_dir)


def test_blocked_benchmark_is_terminal_single_reservation(formal, tmp_path, monkeypatch):
    from math_research.formalization import benchmark

    tools, _, _ = formal
    out = tmp_path / "official"
    out.mkdir()
    (out / "frozen-inputs.json").write_text(
        tools.workspace.frozen.model_dump_json(), encoding="utf-8"
    )
    (out / "informal-target.md").write_text("Synthetic", encoding="utf-8")
    monkeypatch.setattr(
        benchmark,
        "select_formal_executor",
        lambda *args: APISelection(None, {"status": "BLOCKED_API_CONFIGURATION"}),
    )
    result = execute_benchmark(
        tmp_path, tools.workspace.root, out, {"declaration": "Bench.target"}, tools.checker.lake
    )
    assert result["result"] == "BLOCKED" and result["model_calls"] == 0
    assert not result["benchmark_valid"] and not result["official_run_started"]
    assert (out / "benchmark.sha256").read_text().strip() == hash_bytes(
        (out / "benchmark.json").read_bytes()
    )
    with pytest.raises(FileExistsError):
        execute_benchmark(
            tmp_path, tools.workspace.root, out, {"declaration": "Bench.target"}, tools.checker.lake
        )


def test_helper_file_is_compiled_and_facts_expire_on_edit(formal):
    tools, _, calls = formal
    state = FormalRunState(run_id="helper-test")
    path = "WeakSchottky/Helpers/Synthetic.lean"
    result = tools.execute(
        "write_proof_file",
        {"path": path, "content": "lemma syntheticHelper : True := by trivial\n"},
        state,
    )
    assert result["build_ok"]
    assert calls[-1][1:] == ["env", "lean", path]
    assert "syntheticHelper" in state.successful_helper_facts
    tools.workspace.write_proof_file(path, "-- revised before next successful check\n")
    tools.persist(state)
    assert "syntheticHelper" not in state.successful_helper_facts


def test_official_infra_crash_is_invalidated_not_retried(formal, tmp_path, monkeypatch):
    from math_research.formalization import benchmark

    tools, _, _ = formal
    out = tmp_path / "crashed"
    out.mkdir()
    (out / "frozen-inputs.json").write_text(
        tools.workspace.frozen.model_dump_json(), encoding="utf-8"
    )
    (out / "informal-target.md").write_text("Synthetic", encoding="utf-8")
    monkeypatch.setattr(
        benchmark,
        "select_formal_executor",
        lambda *args: APISelection(
            FakeProvider([]), {"status": "CONFIGURED", "provider": "fake-api"}
        ),
    )

    def crash(*args, **kwargs):
        raise RuntimeError("Synthetic infrastructure crash")

    monkeypatch.setattr(benchmark, "FormalizationLoop", crash)
    metadata = {"declaration": "Bench.target", "target_type": "True"}
    result = execute_benchmark(tmp_path, tools.workspace.root, out, metadata, tools.checker.lake)
    assert result["result"] == "BENCHMARK_INVALIDATED_BY_INFRA_BUG"
    assert not result["benchmark_valid"]
    assert (out / "run/run-freeze.json").exists()
    with pytest.raises(FileExistsError):
        execute_benchmark(tmp_path, tools.workspace.root, out, metadata, tools.checker.lake)


def test_configuration_only_never_generates_even_with_a_provider(formal, tmp_path, monkeypatch):
    from math_research.formalization import benchmark

    tools, _, _ = formal
    out = tmp_path / "no-egress"
    out.mkdir()
    (out / "frozen-inputs.json").write_text(
        tools.workspace.frozen.model_dump_json(), encoding="utf-8"
    )
    (out / "informal-target.md").write_text("Synthetic", encoding="utf-8")
    provider = FakeProvider([])
    monkeypatch.setattr(
        benchmark,
        "select_formal_executor",
        lambda *args: APISelection(provider, {"status": "CONFIGURED", "provider": "fake-api"}),
    )
    result = execute_benchmark(
        tmp_path,
        tools.workspace.root,
        out,
        {"declaration": "Bench.target"},
        tools.checker.lake,
        allow_execution=False,
    )
    assert result["result"] == "BLOCKED" and result["configuration_only"]
    assert result["stop_reason"] == "BLOCKED_EXTERNAL_APPROVAL"
    assert not provider.messages and result["model_calls"] == 0
