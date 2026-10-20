"""One fresh bounded model invocation per critique; no tools or authority changes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol

from math_research.agent.codex import CodexToolProvider
from math_research.agent.critique import store
from math_research.agent.critique.models import CritiqueOutput, CritiqueReport, CritiqueRun
from math_research.agent.critique.prompt import CRITIC_PROMPT
from math_research.agent.model import SemanticModel
from math_research.agent.providers.base import ProviderResponse
from math_research.agent.session import SessionMessage
from math_research.core.errors import ResearchError
from math_research.ledger.records.write_boundary import automated_research


class Transport(Protocol):
    def generate(self, messages: list[SessionMessage], schema: dict) -> ProviderResponse: ...


def _generate(ot_dir: Path, run: CritiqueRun, messages: list[SessionMessage]) -> ProviderResponse:
    settings = run.settings
    if settings.provider == "codex":
        # New provider -> new isolated CODEX_HOME, ephemeral thread/start, no resume/session.
        provider = CodexToolProvider(
            settings.model,
            settings.reasoning_effort,
            deadline=time.monotonic() + 600,
            should_stop=lambda: False,
            tool_free=True,
        )
        try:
            return provider.generate(messages, tools=[])
        finally:
            provider.close()
    # New provider/client, one request with system + bundle only; no saved session/history.
    model = SemanticModel(
        ot_dir,
        provider_name=settings.provider,
        model=settings.model,
        reasoning_effort=settings.reasoning_effort,
    )
    return model.generate(messages, CritiqueOutput.model_json_schema())


@automated_research
def execute(ot_dir: Path, run: CritiqueRun, *, transport: Transport | None = None) -> CritiqueRun:
    if store.read_run(ot_dir, run.critique_id).status != "RUNNING":
        raise ResearchError("A critique cannot reuse a completed model session.")
    store.claim_execution(ot_dir, run)
    try:
        bundle = store.read_bundle(ot_dir, run)
        messages = [
            SessionMessage(
                role="system",
                content=CRITIC_PROMPT
                + "\nOutput schema:\n"
                + json.dumps(CritiqueOutput.model_json_schema()),
            ),
            SessionMessage(role="user", content=bundle.model_dump_json()),
        ]
        response = (
            transport.generate(messages, CritiqueOutput.model_json_schema())
            if transport
            else _generate(ot_dir, run, messages)
        )
        if response.kind != "message" or response.truncated or len(response.content) > 100_000:
            raise ResearchError(
                "Critique returned a tool request or oversized output; no tools run."
            )
        output = CritiqueOutput.model_validate_json(response.content)
        limits = [*bundle.limitations, *output.limitations]
        if output.requires_computation:
            limits.append("Computation tools unavailable; no unsafe fallback was executed.")
        if bundle.limitations or output.requires_computation:
            output.verdict = "INCONCLUSIVE"
        report = CritiqueReport(
            **{**output.model_dump(), "limitations": sorted(set(limits))},
            critique_id=run.critique_id,
            target_id=run.target_id,
            target_type=run.target_type,
            created_at=run.created_at,
            provider=run.settings.provider,
            model=response.model or run.settings.model,
            reasoning_effort=run.settings.reasoning_effort,
            context_manifest=[bundle.target, bundle.problem, *bundle.context, *bundle.relations],
            bundle_sha256=run.bundle_sha256,
            session_id=run.session_id,
        )
        return store.finish(ot_dir, run, report=report)
    except Exception as exc:
        # Store a bounded actionable failure, never raw transport logs/credentials/model output.
        if isinstance(exc, ResearchError):
            detail = str(exc)
        else:
            detail = f"Critique failed ({type(exc).__name__}); check model output/configuration."
        return store.finish(ot_dir, run, error=detail)
