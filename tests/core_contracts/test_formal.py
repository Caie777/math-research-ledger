from __future__ import annotations

import json
import subprocess

import pytest
from pydantic import ValidationError

from math_research.verification.formal import (
    FormalBundle,
    FormalCheckResult,
    FormalState,
    LeanChecker,
    freeze,
    load_freeze,
    verify_frozen,
)
from math_research.verification.formal.checker import (
    CommandResult,
    code_only,
    parse_probe,
    scan_sources,
)
from math_research.verification.formal.freeze import frozen_source, source_path

DECLARATION = "Example.target"
CLEAN = (
    "Example.target (n : Nat) : True\n"
    "'Example.target' depends on axioms: [propext, Classical.choice, Quot.sound]\n"
)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.35.0\n", encoding="utf-8")
    (root / "lakefile.toml").write_text('name = "example"\n', encoding="utf-8")
    (root / "lake-manifest.json").write_text(
        json.dumps({"packages": [{"name": "mathlib", "inputRev": "v4.35.0", "rev": "a" * 40}]}),
        encoding="utf-8",
    )
    (root / "Statement.lean").write_bytes(b"def statement : Prop := True\n")
    (root / "Definition.lean").write_bytes(b"def localValue : Nat := 1\n")
    (root / "Proof.lean").write_text("theorem target : True := by trivial\n", encoding="utf-8")
    executable = tmp_path / "lake.exe"
    executable.write_bytes(b"fake; never executed")
    checker = LeanChecker(executable, elan_home=tmp_path / "elan")
    frozen = freeze(root, "Statement.lean", ("Definition.lean",), tmp_path / "freezes")
    return root, frozen, checker


def fake_commands(monkeypatch, checker, results):
    calls = []
    iterator = iter(results)

    def run(arguments, root, env, log, input_text=None):
        calls.append((arguments, root, env, input_text))
        result = next(iterator)
        log.write(result.output.encode("utf-8"))
        return result

    monkeypatch.setattr(checker, "_run", run)
    return calls


def check(project, tmp_path):
    root, frozen, checker = project
    return checker.check(root, "Example", DECLARATION, frozen, tmp_path / "check.log")


def test_freeze_exact_bytes_and_normalization(project, tmp_path):
    root, frozen, _ = project
    assert frozen.statement == frozen_source(root, "Statement.lean")
    original = frozen.statement
    path = root / "Statement.lean"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    changed = frozen_source(root, "Statement.lean")
    assert original.sha256 != changed.sha256
    assert original.normalized_sha256 == changed.normalized_sha256
    # General spacing is deliberately not normalized or treated as semantic equivalence.
    path.write_bytes(b"def  statement : Prop := True\n")
    assert frozen_source(root, "Statement.lean").normalized_sha256 != original.normalized_sha256
    assert verify_frozen(root, frozen) == ("Statement.lean",)
    assert load_freeze(tmp_path / "freezes/v1/manifest.json") == frozen


@pytest.mark.parametrize(
    "path",
    ["Statement.lean", "Definition.lean", "lake-manifest.json", "lean-toolchain", "lakefile.toml"],
)
def test_each_drift_rejected_before_subprocess(project, tmp_path, monkeypatch, path):
    root, _, checker = project
    with (root / path).open("ab") as file:
        file.write(b" ")
    calls = fake_commands(monkeypatch, checker, [])
    result = check(project, tmp_path)
    assert result.status == FormalState.PROVISIONAL
    assert result.reasons == ("FROZEN_SOURCE_DRIFT",)
    assert not calls


def test_missing_dependency_is_drift(project, tmp_path, monkeypatch):
    root, _, checker = project
    (root / "lake-manifest.json").unlink()
    fake_commands(monkeypatch, checker, [])
    assert check(project, tmp_path).reasons == ("FROZEN_SOURCE_DRIFT",)


def test_versioning_preserves_v1(project, tmp_path):
    root, v1, _ = project
    old_manifest = (tmp_path / "freezes/v1/manifest.json").read_bytes()
    (root / "Statement.lean").write_bytes(b"def statement : Prop := False\n")
    with pytest.raises(FileExistsError):
        freeze(root, "Statement.lean", (), tmp_path / "freezes")
    with pytest.raises(ValueError):
        freeze(root, "Statement.lean", (), tmp_path / "freezes", version=2)
    v2 = freeze(
        root, "Statement.lean", (), tmp_path / "freezes", version=2, reason="Corrected target"
    )
    assert v2.statement.sha256 != v1.statement.sha256
    assert (tmp_path / "freezes/v1/manifest.json").read_bytes() == old_manifest
    assert (tmp_path / "freezes/v1/sources/Statement.lean").read_bytes().endswith(b"True\n")
    assert verify_frozen(root, v2) == ()


@pytest.mark.parametrize(
    "path", ["../outside", "a/../../x", "..\\x", "C:\\x", "/x", ".lake/x", ".git/x", "a:b"]
)
def test_path_traversal_rejected(project, path):
    root, _, _ = project
    with pytest.raises(ValueError):
        source_path(root, path)


def test_clean_check_is_only_checked(project, tmp_path, monkeypatch):
    root, frozen, checker = project
    calls = fake_commands(
        monkeypatch, checker, [CommandResult(0, "built"), CommandResult(0, CLEAN)]
    )
    result = check(project, tmp_path)
    assert result.status == FormalState.CHECKED
    assert result.axioms == ("propext", "Classical.choice", "Quot.sound")
    assert not result.sorry_ax and not result.custom_axioms
    assert calls[0][0] == [str(checker.lake), "build"]
    assert calls[1][0] == [str(checker.lake), "env", "lean", "--stdin"]
    assert calls[1][3] == "import Example\n#check Example.target\n#print axioms Example.target\n"
    assert calls[0][1] == root.resolve()
    assert calls[0][2]["ELAN_HOME"] == str(checker.elan_home)
    assert calls[0][2]["ELAN_TOOLCHAIN"] == frozen.lean_toolchain
    assert "RESULT" in (tmp_path / "check.log").read_text("utf-8")
    bundle = FormalBundle(
        id="FORMAL-test",
        formal_repo=str(root),
        formal_repo_commit="test",
        declaration=DECLARATION,
        frozen=frozen,
        check=result,
    )
    assert bundle.status == FormalState.CHECKED
    assert not bundle.usable_as_premise and not bundle.human_accepted and not bundle.promotes_claim
    assert bundle.correspondence_status == "PENDING"
    assert FormalState.ACCEPTED.value == "accepted"
    with pytest.raises(ValidationError):
        FormalBundle(**{**bundle.model_dump(), "human_accepted": True})
    with pytest.raises(ValidationError):
        FormalCheckResult(**{**result.model_dump(), "status": "accepted"})


@pytest.mark.parametrize(
    "build,probe,reason",
    [
        (CommandResult(1, "compile fail"), None, "BUILD_FAILED"),
        (CommandResult(None, "timeout", True), None, "TIMEOUT"),
        (CommandResult(0, ""), CommandResult(1, "unknown constant"), "MISSING_DECLARATION"),
        (
            CommandResult(0, ""),
            CommandResult(0, "Example.target : True"),
            "AXIOM_REPORT_UNREADABLE",
        ),
        (CommandResult(0, ""), CommandResult(None, "timeout", True), "TIMEOUT"),
        (CommandResult(0, ""), CommandResult(0, CLEAN, truncated=True), "AXIOM_REPORT_UNREADABLE"),
    ],
)
def test_failures_never_checked(project, tmp_path, monkeypatch, build, probe, reason):
    _, _, checker = project
    fake_commands(monkeypatch, checker, [build] + ([probe] if probe else []))
    result = check(project, tmp_path)
    assert result.status == FormalState.PROVISIONAL
    assert reason in result.reasons


@pytest.mark.parametrize("axiom", ["sorryAx", "Example.unproved"])
def test_axiom_policy(project, tmp_path, monkeypatch, axiom):
    _, _, checker = project
    output = f"Example.target : True\n'Example.target' depends on axioms: [{axiom}]\n"
    fake_commands(monkeypatch, checker, [CommandResult(0, ""), CommandResult(0, output)])
    result = check(project, tmp_path)
    assert result.status == FormalState.PROVISIONAL
    assert result.sorry_ax == (axiom == "sorryAx")
    assert result.custom_axioms == (axiom,)


def test_empty_axioms_are_allowed(project, tmp_path, monkeypatch):
    _, _, checker = project
    output = "Example.target : True\n'Example.target' does not depend on any axioms\n"
    fake_commands(monkeypatch, checker, [CommandResult(0, ""), CommandResult(0, output)])
    assert check(project, tmp_path).status == FormalState.CHECKED


@pytest.mark.parametrize("token", ["sorry", "admit", "axiom"])
def test_source_policy(project, tmp_path, monkeypatch, token):
    root, _, checker = project
    (root / "Proof.lean").write_text(f"theorem x : True := by {token}\n", encoding="utf-8")
    fake_commands(monkeypatch, checker, [CommandResult(0, ""), CommandResult(0, CLEAN)])
    result = check(project, tmp_path)
    assert result.status == FormalState.PROVISIONAL
    assert result.source_violations == (f"Proof.lean: {token}",)


def test_comment_strings_and_native(project, tmp_path, monkeypatch):
    root, _, checker = project
    text = """/- sorry /- admit -/ axiom -/
-- native_decide
def s := "sorry admit axiom"
def r := r#"axiom "sorry" admit"#
def c := 'x'
"""
    (root / "Proof.lean").write_text(text, encoding="utf-8")
    assert "sorry" not in code_only(text)
    assert scan_sources(root) == ((), False)
    (root / "Proof.lean").write_text(
        text + "example : True := by native_decide\n", encoding="utf-8"
    )
    fake_commands(monkeypatch, checker, [CommandResult(0, ""), CommandResult(0, CLEAN)])
    result = check(project, tmp_path)
    assert result.native_decide
    assert result.status == FormalState.CHECKED


@pytest.mark.parametrize("name", ["X; quit", "X\naxiom x : False", "../X", "-X", "X..Y", "X Y"])
def test_invalid_declaration_never_executed(project, tmp_path, monkeypatch, name):
    root, frozen, checker = project
    calls = fake_commands(monkeypatch, checker, [])
    with pytest.raises(ValueError):
        checker.check(root, "Example", name, frozen, tmp_path / "check.log")
    assert not calls


def test_wrong_target_report_is_not_enough():
    assert parse_probe(CLEAN.replace("Example.target", "Example.other"), DECLARATION) == (
        False,
        False,
        (),
    )
    assert parse_probe(CLEAN + CLEAN, DECLARATION)[1] is False


def test_hash_change_during_check_rejected(project, tmp_path, monkeypatch):
    root, _, checker = project

    def run(arguments, root, env, log, input_text=None):
        (root / "Definition.lean").write_bytes(b"def localValue : Nat := 2\n")
        return CommandResult(0, CLEAN if input_text else "built")

    monkeypatch.setattr(checker, "_run", run)
    result = check(project, tmp_path)
    assert result.reasons == ("FROZEN_SOURCE_DRIFT",)
    assert not result.hashes_match
    assert result.status == FormalState.PROVISIONAL


def test_logs_cannot_overwrite_repo_or_previous_log(project, tmp_path, monkeypatch):
    root, frozen, checker = project
    fake_commands(monkeypatch, checker, [])
    with pytest.raises(ValueError):
        checker.check(root, "Example", DECLARATION, frozen, root / "Statement.lean")
    (tmp_path / "check.log").write_text("prior evidence", encoding="utf-8")
    with pytest.raises(FileExistsError):
        check(project, tmp_path)


def test_incomplete_flags_cannot_produce_checked(tmp_path):
    result = FormalCheckResult(checked_at="test", log=str(tmp_path / "log"))
    assert result.status == FormalState.PROVISIONAL


@pytest.mark.parametrize("timeout", [False, True])
def test_runner_bounds_capture_keeps_full_log_and_cleans_timeout(
    project, tmp_path, monkeypatch, timeout
):
    from math_research.verification.formal import checker as checker_module

    root, _, checker = project
    checker.capture_limit = 1024
    calls = []

    class FakeProcess:
        pid = 12345
        returncode = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def communicate(self, data, timeout):
            if timeout and test_timeout:
                raise subprocess.TimeoutExpired("lake", timeout)

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    def spawn(arguments, **kwargs):
        calls.append((arguments, kwargs))
        kwargs["stdout"].write(b"x" * 10000)
        return FakeProcess()

    test_timeout = timeout
    monkeypatch.setattr(checker_module, "spawn_process", spawn)
    if checker_module.os.name != "nt":
        monkeypatch.setattr(checker_module.os, "killpg", lambda *args: None)
    with (tmp_path / "runner.log").open("w+b") as log:
        result = checker._run(
            [str(checker.lake), "build"], root, {"ELAN_HOME": str(checker.elan_home)}, log
        )
    assert result.timed_out == timeout
    assert result.truncated
    assert len(result.output) <= 1024
    assert len((tmp_path / "runner.log").read_bytes()) > 10000
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["env"]["ELAN_HOME"] == str(checker.elan_home)
    if timeout and checker_module.os.name == "nt":
        assert calls[1][0][1:] == ["/PID", "12345", "/T", "/F"]


def test_complex_type_contract_is_exact_and_not_a_command(project, tmp_path, monkeypatch):
    root, frozen, checker = project
    calls = fake_commands(
        monkeypatch, checker, [CommandResult(0, "built"), CommandResult(0, CLEAN)]
    )
    contract = "∀ (z : ℂ), z = z"
    checker.check(
        root, "Example", DECLARATION, frozen, tmp_path / "complex-check.log", expected_type=contract
    )
    assert f"#check ({DECLARATION} : {contract})" in calls[1][3]


@pytest.mark.parametrize(
    "contract", ["True; #eval IO.println 1", "True\n#eval IO.println 1", 'True) #eval "bad"']
)
def test_type_contract_rejects_command_injection(project, tmp_path, monkeypatch, contract):
    root, frozen, checker = project
    calls = fake_commands(monkeypatch, checker, [])
    with pytest.raises(ValueError):
        checker.check(
            root,
            "Example",
            DECLARATION,
            frozen,
            tmp_path / "never-created.log",
            expected_type=contract,
        )
    assert not calls and not (tmp_path / "never-created.log").exists()
