"""Prepare disposable integration fixtures; never real research or human acceptance."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from math_research.core.refs import ObjectRef  # noqa: E402
from math_research.core.workspace import init_workspace, workspace_dir  # noqa: E402
from math_research.services.research import add_claim, create_problem  # noqa: E402
from math_research.services.verification import ExactVerificationService  # noqa: E402
from math_research.verification.models import CheckOutcome, ExactCertificate  # noqa: E402


class SyntheticFixtureChecker:
    def check(self, certificate):
        assert certificate.inputs == {"fixture": "synthetic-host-smoke"}
        return CheckOutcome(status="PASSED", summary="Synthetic host fixture, no mathematics")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    root = args.workspace.resolve()
    allowed = ROOT / ".local-eval"
    if not root.is_relative_to(allowed) or root == allowed or root.exists():
        parser.error("Choose a NEW disposable directory beneath this checkout's .local-eval.")
    root.mkdir(parents=True)
    init_workspace(root)
    state = workspace_dir(root)
    problem = create_problem(
        state,
        "PROBLEM-TEST synthetic host fixture",
        "Synthetic MCP engineering fixture. Read existing state only; do not conduct research.",
    )
    claim = add_claim(
        state,
        problem.id,
        "Synthetic transport marker: 中文 ∀z ∈ ℂ. No mathematical conclusion is asserted.",
    )
    ref = ObjectRef(problem_id=problem.id, kind="claim", object_id=claim.id)
    receipt = ExactVerificationService(
        {"synthetic-host-fixture": SyntheticFixtureChecker()}
    ).verify(
        state,
        ref,
        ExactCertificate(
            checker="synthetic-host-fixture",
            inputs={"fixture": "synthetic-host-smoke"},
            scope="Integration fixture only, not mathematical verification",
        ),
    )
    info = {
        "workspace": str(root),
        "problem_id": problem.id,
        "ref": ref.qualified_id,
        "verification_id": receipt.id,
    }
    (root / "fixture.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
