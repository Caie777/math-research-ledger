"""Fixed compiler and file tool surface used by the standalone formalization loop."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from math_research.core.atomicio import atomic_write_text

from .agent import FormalRunState
from .checker import LeanChecker, code_only
from .diagnostics import extract_diagnostics
from .freeze import hash_bytes
from .workspace import FormalWorkspace, append_event


class FormalTools:
    def __init__(
        self,
        workspace: FormalWorkspace,
        checker: LeanChecker,
        run_dir: Path,
        module: str,
        declaration: str,
        target_type: str | None = None,
    ):
        self.workspace, self.checker = workspace, checker
        self.run_dir = run_dir.resolve()
        self.module, self.declaration = module, declaration
        self.target_type = target_type
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def persist(self, state: FormalRunState) -> None:
        if (self.run_dir / "run-freeze.json").exists():
            raise ValueError("Terminal run is sealed")
        state.proof_hashes = self.workspace.proof_hashes()
        state.successful_source_facts = {
            path: fact
            for path, fact in state.successful_source_facts.items()
            if state.proof_hashes.get(path) == fact["sha256"]
        }
        state.successful_helper_facts = sorted(
            {
                name
                for fact in state.successful_source_facts.values()
                for name in fact["declarations"]
            }
        )
        atomic_write_text(self.run_dir / "run-state.json", state.model_dump_json(indent=2))

    def proof_hash(self) -> str:
        return hash_bytes(json.dumps(self.workspace.proof_hashes(), sort_keys=True).encode())

    def run_lean_build(self, state: FormalRunState, path: str | None = None) -> dict:
        self.workspace.integrity()
        if state.build_count >= state.budget.builds:
            state.stop_reason = "BUDGET_EXHAUSTED"
            return {"error": "Build budget exhausted"}
        if path is not None:
            target = self.workspace._path("run_lean_build", path, "read")
            if target.suffix != ".lean":
                raise ValueError("Compiler input must be a Lean source")
        proof_hash = hash_bytes((self.proof_hash() + (path or "ROOT")).encode())
        if proof_hash == state.last_built_hash:
            state.no_progress_events.append("REPEATED_PROOF_HASH")
            return {"error": "Proof unchanged since the previous build", "unchanged": True}
        state.build_count += 1
        state.pending_operation = "build"
        self.persist(state)
        log_path = self.run_dir / "diagnostics" / f"build-{state.build_count:03}.log"
        log_path.parent.mkdir(exist_ok=True)
        env = {
            **os.environ,
            "ELAN_HOME": str(self.checker.elan_home),
            "ELAN_TOOLCHAIN": self.workspace.frozen.lean_toolchain,
            "PATH": str(self.checker.lake.parent) + os.pathsep + os.environ.get("PATH", ""),
        }
        arguments = (
            [str(self.checker.lake), "env", "lean", path]
            if path
            else [str(self.checker.lake), "build"]
        )
        with log_path.open("x+b") as log:
            result = self.checker._run(arguments, self.workspace.root, env, log)
        self.workspace.integrity()
        state.pending_operation = None
        state.last_built_hash = proof_hash
        state.last_build_ok = result.exit_code == 0 and not result.timed_out
        state.diagnostics = extract_diagnostics(result.output)
        errors = [d.signature for d in state.diagnostics if d.severity == "error"]
        signature = ",".join(errors)
        state.repeated_errors = (
            state.repeated_errors + 1
            if signature and signature == state.last_error_signature
            else 1
        )
        state.last_error_signature = signature
        if state.repeated_errors >= 3 and signature:
            state.no_progress_events.append("REPEATED_ERROR_SIGNATURE")
        if state.last_build_ok:
            # File checks certify that file; root builds certify only the imported project closure.
            checked_files = {path} if path else set()
            if path is None:
                pending = ["WeakSchottky.lean"]
                while pending:
                    name = pending.pop()
                    if name in checked_files:
                        continue
                    checked_files.add(name)
                    source = code_only(self.workspace.read_formal_file(name, lines=200))
                    for module in re.findall(r"(?m)^\s*(?:public\s+)?import\s+([\w.]+)", source):
                        relative = module.replace(".", "/") + ".lean"
                        if relative in self.workspace.list_formal_workspace():
                            pending.append(relative)
            current = self.workspace.proof_hashes()
            for name in checked_files & current.keys():
                source = code_only(self.workspace.read_formal_file(name, lines=200))
                state.successful_source_facts[name] = {
                    "sha256": current[name],
                    "declarations": re.findall(r"\b(?:theorem|lemma)\s+([\w.']+)", source),
                }
        observation = {
            "build_ok": state.last_build_ok,
            "diagnostics": [d.model_dump() for d in state.diagnostics],
            "log": str(log_path),
            "scope": path or "ROOT",
            "timed_out": result.timed_out,
        }
        append_event(
            self.run_dir / "build-events.jsonl",
            {
                "build": state.build_count,
                "proof_hash": proof_hash,
                "exit_code": result.exit_code,
                **observation,
            },
        )
        atomic_write_text(log_path.with_suffix(".json"), json.dumps(observation, indent=2))
        self.persist(state)
        return observation

    def check_target(self, state: FormalRunState) -> dict:
        if (
            state.target_checks >= state.budget.target_checks
            or state.build_count >= state.budget.builds
        ):
            state.stop_reason = "BUDGET_EXHAUSTED"
            return {"error": "Verification budget exhausted"}
        self.workspace.integrity()
        # V0 check always performs one build. Reserve it against the same build budget.
        state.target_checks += 1
        state.build_count += 1
        state.pending_operation = "target_check"
        self.persist(state)
        path = self.run_dir / f"target-check-{state.target_checks:03}.log"
        result = self.checker.check(
            self.workspace.root,
            self.module,
            self.declaration,
            self.workspace.frozen,
            path,
            expected_type=self.target_type,
        )
        state.pending_operation = None
        atomic_write_text(path.with_suffix(".json"), result.model_dump_json(indent=2))
        state.diagnostics = extract_diagnostics(result.output_tail)
        state.last_build_ok = result.build_exit_code == 0
        if result.status.value == "checked":
            state.stop_reason = "CHECKED"
        observation = {
            **result.model_dump(exclude={"output_tail"}),
            "status": result.status.value,
            "diagnostics": [d.model_dump() for d in state.diagnostics],
        }
        append_event(
            self.run_dir / "build-events.jsonl",
            {"build": state.build_count, "operation": "target_check", **observation},
        )
        self.persist(state)
        return observation

    def execute(self, tool: str, arguments: dict, state: FormalRunState) -> dict:
        state.tool_calls += 1
        if state.tool_calls > 128:
            state.stop_reason = "BUDGET_EXHAUSTED"
            return {"error": "Tool budget exhausted"}
        self.workspace.integrity()
        if tool == "write_proof_file":
            changed = self.workspace.write_proof_file(**arguments)
            if not changed:
                state.no_progress_events.append("EMPTY_EDIT")
                return {"changed": False, "error": "No byte change"}
            path = arguments["path"]
            scope = None if path == self.module.replace(".", "/") + ".lean" else path
            return {"changed": True, **self.run_lean_build(state, path=scope)}
        if tool == "run_lean_build":
            return self.run_lean_build(state, **arguments)
        if tool in {"check_target", "FINISH"}:
            return self.check_target(state)
        if tool == "read_build_diagnostics":
            return {"diagnostics": [d.model_dump() for d in state.diagnostics]}
        if tool == "list_formal_workspace":
            return {"files": self.workspace.list_formal_workspace()}
        if tool in {"read_formal_file", "read_mathlib_source", "search_mathlib"}:
            return {"result": getattr(self.workspace, tool)(**arguments)}
        raise ValueError("Unsupported formalization tool")
