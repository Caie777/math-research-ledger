"""Confirmed onboarding and read-only maintenance adapters for the existing stores."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from math_research.app.maintenance.workspace import (
    MAX_PACK_BYTES,
    handoff_pack,
    system_health,
    verify_snapshot,
    workspace_snapshot,
)
from math_research.app.workflows.episodes import MAX_UPLOAD_BYTES
from math_research.core.atomicio import file_lock
from math_research.core.errors import ResearchError
from math_research.core.jsonl import next_sequential_id
from math_research.ledger.records import claims, store
from math_research.ledger.sources import SourceUpload, save_source, source_papers, validate_source
from math_research.retrieval.index import IndexDoc
from math_research.retrieval.recall import ResearchRecall
from math_research.retrieval.related_research import MemoryHit


class ProblemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    statement: str = Field(min_length=1, max_length=20000)
    target_type: Literal["Claim", "Gap"]
    description: str = Field(default="", max_length=2000)

    @field_validator("title", "statement", "description", mode="before")
    @classmethod
    def trim(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def problem_preview(value: ProblemInput, sources: list[SourceUpload]) -> dict:
    payload = {
        **value.model_dump(),
        "sources": [
            {"filename": s.filename, "sha256": s.digest, "size": len(s.content)} for s in sources
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return {**payload, "source_count": len(sources), "digest": digest}


def install_problem_routes(app: FastAPI, ot_dir: Path, write_header: Callable) -> None:
    def scoped(pid: str) -> None:
        if not any(dossier.id == pid for dossier in store.list_dossiers(ot_dir)):
            raise HTTPException(404, "Problem not found in this workspace.")

    async def inputs(
        metadata: str, files: list[UploadFile] | None
    ) -> tuple[ProblemInput, list[SourceUpload]]:
        try:
            value = ProblemInput.model_validate_json(metadata)
            if len(files or []) > 10:
                raise ResearchError("At most 10 source files per confirmation.")
            uploads = [
                validate_source(f.filename or "", await f.read(MAX_UPLOAD_BYTES + 1))
                for f in files or []
            ]
            return value, uploads
        except (ValidationError, ResearchError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/problems/preview", dependencies=[Depends(write_header)])
    async def preview(
        metadata: Annotated[str, Form()], files: Annotated[list[UploadFile] | None, File()] = None
    ) -> dict:
        value, sources = await inputs(metadata, files)
        return problem_preview(value, sources)

    @app.post("/api/problems", dependencies=[Depends(write_header)])
    async def create(
        metadata: Annotated[str, Form()],
        digest: Annotated[str, Form()],
        confirmed: Annotated[bool, Form()],
        files: Annotated[list[UploadFile] | None, File()] = None,
    ) -> dict:
        value, sources = await inputs(metadata, files)
        if not confirmed or digest != problem_preview(value, sources)["digest"]:
            raise HTTPException(400, "Explicit confirmation of the unchanged preview is required.")
        # Reuse the human-input authority boundary and original Claim/OPEN_GAP semantics.
        with file_lock(ot_dir / "problems" / ".onboarding"):
            next_id = next_sequential_id("PROBLEM", len(store.list_dossiers(ot_dir)))
            if (ot_dir / "problems" / next_id).exists():
                raise ResearchError(
                    "Problem ID conflicts with an existing directory. "
                    "Inspect the store before creating; nothing was overwritten."
                )
            dossier = store.create_dossier(ot_dir, value.statement, title=value.title)
            target = claims.add_claim(
                ot_dir,
                dossier.id,
                claim_type="OPEN_GAP" if value.target_type == "Gap" else "CONJECTURE",
                statement=value.statement,
                notes=value.description,
            )
            dossier.primary_claim_id = target.id
            store.save_dossier(ot_dir, dossier)
            saved = [save_source(ot_dir, dossier.id, source).id for source in sources]
        return {
            "problem_id": dossier.id,
            "target_id": target.id,
            "target_type": value.target_type,
            "status": target.status,
            "source_ids": saved,
        }

    @app.get("/api/problems/{pid}/sources")
    def sources(pid: str) -> list:
        scoped(pid)
        nav = ResearchRecall(ot_dir, pid)
        return [
            nav._file(
                pid,
                IndexDoc(
                    artifact_id=p.id,
                    artifact_type="dossier:source",
                    title=p.title or p.source,
                    text="",
                    problem_id=pid,
                ),
                MemoryHit(
                    object_id=p.id,
                    object_type="dossier:source",
                    title=p.title or p.source,
                    excerpt="",
                ),
                {},
                None,
            )
            for p in source_papers(ot_dir, pid)
        ]

    @app.post("/api/problems/{pid}/sources", dependencies=[Depends(write_header)])
    async def add_source(
        pid: str, file: Annotated[UploadFile, File()], confirmed: Annotated[bool, Form()]
    ) -> dict:
        scoped(pid)
        if not confirmed:
            raise HTTPException(400, "Confirm saving the selected raw source.")
        upload = validate_source(file.filename or "", await file.read(MAX_UPLOAD_BYTES + 1))
        saved = save_source(ot_dir, pid, upload)
        return {"source_id": saved.id, "filename": saved.title, "sha256": saved.sha256}

    @app.get("/api/maintenance/health")
    def health() -> dict:
        return system_health(ot_dir)

    @app.get("/api/maintenance/snapshot")
    def snapshot() -> Response:
        return Response(
            workspace_snapshot(ot_dir),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="workspace_snapshot.zip"'},
        )

    @app.post("/api/maintenance/snapshot/verify", dependencies=[Depends(write_header)])
    async def verify(file: Annotated[UploadFile, File()]) -> dict:
        raw = await file.read(MAX_PACK_BYTES + 1)
        if len(raw) > MAX_PACK_BYTES:
            raise HTTPException(400, "Snapshot exceeds 512 MiB verification limit.")
        return verify_snapshot(raw)

    @app.get("/api/problems/{pid}/handoff/{tid}")
    def handoff(pid: str, tid: str) -> Response:
        scoped(pid)
        return Response(
            handoff_pack(ot_dir, pid, tid),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{tid}_handoff.zip"'},
        )
