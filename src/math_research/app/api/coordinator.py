"""Typed Coordinator transport, sharing existing Research Agent actions/executor."""

from collections.abc import Callable
from pathlib import Path

from fastapi import Depends, FastAPI

from math_research.app.workflows.coordinator import (
    Coordinator,
    CoordinatorRequest,
    CoordinatorResponse,
    ResearchRunActions,
)
from math_research.app.workflows.portfolio import ProblemPortfolio, research_portfolio


def install_coordinator_routes(
    app: FastAPI,
    ot_dir: Path,
    write_header: Callable,
    actions: ResearchRunActions,
) -> None:
    @app.get("/api/research/portfolio")
    def portfolio() -> list[ProblemPortfolio]:
        return research_portfolio(ot_dir)

    @app.post("/api/coordinator", dependencies=[Depends(write_header)])
    def coordinate(request: CoordinatorRequest) -> CoordinatorResponse:
        return Coordinator(ot_dir, actions).respond(request)
