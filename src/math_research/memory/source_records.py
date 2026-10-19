"""Paper ingestion with source pinning.

Local PDFs are copied into the workspace and pinned with a SHA-256 hash so that
summaries cannot silently drift when an upstream source changes. URLs are
registered as metadata and marked "unpinned" until downloaded. Local PDFs are
parsed into structure + reading notes automatically (``pypdf`` is a core dependency).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass

PaperSourceType = Literal["local_pdf", "url", "arxiv", "manual", "doi"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Paper(BaseModel):
    id: str
    source: str
    source_type: PaperSourceType
    title: str | None = None
    retrieved_at: datetime | None = None
    local_path: str | None = None
    sha256: str | None = None
    extraction_method: str | None = None
    text_path: str | None = None
    summary_path: str | None = None
    pinned: bool = False
    # Acquisition provenance (Milestone 43).
    doi: str | None = None
    arxiv_id: str | None = None
    year: int | None = None
    license: str | None = None
    full_text_accessible: bool | None = None
    access_note: str | None = None
    abstract: str | None = None
    source_connector: str | None = None
    citation_count: int | None = None
    # Structured reading (Milestone 45).
    structure_path: str | None = None
    note_path: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


_PAPER_NOTE_TEMPLATE = """\
# {id} — {title}

> **PLACEHOLDER ONLY** — PDF not parsed yet. Re-run `paper fetch` or `paper ingest` \
to parse once full text is cached locally.

## Source

{source}

## Main question

## Contributions

## Methods

## Key assumptions

## Evidence used

## Limitations

## Algorithms or procedures

## Claims relevant to this project

## Open questions

## Possible follow-up tasks
"""


def papers_dir(ot_dir: Path) -> Path:
    return ot_dir / "papers"


def _meta_path(paper_dir: Path) -> Path:
    return paper_dir / "metadata.yaml"


def _save_meta(ot_dir: Path, paper: Paper) -> None:
    paper_dir = papers_dir(ot_dir) / paper.id
    paper_dir.mkdir(parents=True, exist_ok=True)
    _meta_path(paper_dir).write_text(
        yaml.safe_dump(paper.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )


_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(?P<id>[^\s?#]+)", re.IGNORECASE)


def list_papers(ot_dir: Path) -> list[Paper]:
    base = papers_dir(ot_dir)
    if not base.is_dir():
        return []
    papers: list[Paper] = []
    for child in sorted(base.iterdir()):
        meta = _meta_path(child)
        if child.is_dir() and meta.is_file():
            data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
            papers.append(Paper.model_validate(data))
    return papers


def get_paper(ot_dir: Path, paper_id: str) -> Paper | None:
    for paper in list_papers(ot_dir):
        if paper.id == paper_id:
            return paper
    return None


ARXIV_LICENSE = "arXiv.org perpetual, non-exclusive license"


def is_paper_parsed(ot_dir: Path, paper: Paper) -> bool:
    """True when ``read_paper`` has produced structure + reading note artifacts."""
    return (papers_dir(ot_dir) / paper.id / "structure.json").is_file()
