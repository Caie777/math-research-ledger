"""All core tests use temporary research stores and fake model transports."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from math_research.agent.state import AgentRequest
from math_research.app.api.server import create_app
from math_research.core.workspace import init_workspace, workspace_dir
from math_research.memory.records import claims, store
from math_research.memory.target import ResearchTarget


@pytest.fixture
def workspace(tmp_path: Path):
    init_workspace(tmp_path)
    ot = workspace_dir(tmp_path)
    problem = store.create_dossier(ot, "Synthetic square identity")
    target = claims.add_claim(
        ot, problem.id, claim_type="CONJECTURE", statement="For real x, (x+1)^2=x^2+2x+1"
    )
    problem.primary_claim_id = target.id
    store.save_dossier(ot, problem)
    request = AgentRequest(
        target=ResearchTarget(kind="claim", problem_id=problem.id, node_id=target.id)
    )
    with TestClient(create_app(ot)) as client:
        yield ot, request, client


@pytest.fixture
def demo() -> bytes:
    return (Path(__file__).resolve().parents[1] / "examples/demo_research_episode.md").read_bytes()
