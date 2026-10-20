from pathlib import Path

import pytest

from math_research.core.refs import ObjectRef
from math_research.core.workspace import init_workspace, workspace_dir
from math_research.services.research import add_claim, create_problem


@pytest.fixture
def research(tmp_path: Path):
    init_workspace(tmp_path)
    state = workspace_dir(tmp_path)
    problem = create_problem(state, "Synthetic contract", "A synthetic test problem")
    claim = add_claim(state, problem.id, "A complete synthetic claim")
    return state, ObjectRef(problem_id=problem.id, kind="claim", object_id=claim.id)
