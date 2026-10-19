"""Read-only bounded page/line preflight; never includes research trajectories."""

import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Literal

from pypdf import PdfReader

from math_research.agent.source_digest.models import Locator, SourceChunk, SourceDigestContext
from math_research.core.errors import ResearchError
from math_research.memory.records import store
from math_research.memory.sources import SOURCE_CONNECTOR, read_source
from math_research.memory.state import KnowledgeStateResolver

MAX_CANDIDATE_CHUNKS = 12
MAX_CHUNK_CHARS = 10000
MAX_CONTEXT_FIELD = 8000


def build_context(ot_dir: Path, pid: str, source_id: str) -> SourceDigestContext:
    problem = store.require_dossier(ot_dir, pid)
    statement = store.read_statement(ot_dir, pid)
    paper, source_path, raw = read_source(ot_dir, pid, source_id)
    filename = (
        paper.title or source_path.name
        if paper.source_connector == SOURCE_CONNECTOR
        else source_path.name
    )
    chunks: list[SourceChunk] = []
    limits: list[str] = []
    fmt: Literal["PDF", "MARKDOWN", "TXT"]
    unit: Literal["page", "line"]
    pdf = source_path.suffix.lower() == ".pdf"
    if pdf:
        limits.append(
            "PDF text extraction may lose mathematical glyphs/layout; inspect original pages."
        )
        reader = PdfReader(BytesIO(raw))
        total = len(reader.pages)
        count = min(total, MAX_CANDIDATE_CHUNKS)
        pages = sorted({round(i * (total - 1) / max(1, count - 1)) for i in range(count)})
        for page in pages:
            text = reader.pages[page].extract_text() or ""
            chunks.append(
                SourceChunk(
                    chunk_id=f"CHUNK-{len(chunks) + 1:04d}",
                    page=page + 1,
                    text=text[:MAX_CHUNK_CHARS],
                    truncated=len(text) > MAX_CHUNK_CHARS,
                )
            )
        if not any(chunk.text.strip() for chunk in chunks):
            raise ResearchError("PDF has no readable text in sampled pages; OCR is not available.")
        if count < total:
            limits.append(
                "Only evenly sampled pages are available; unprocessed pages are reported."
            )
        fmt, unit = "PDF", "page"
    else:
        lines = raw.decode("utf-8-sig").splitlines(keepends=True)
        total = len(lines)
        groups: list[SourceChunk] = []
        start, content, truncated = 1, "", False
        for number, line in enumerate(lines, 1):
            if content and len(content) + len(line) > MAX_CHUNK_CHARS:
                groups.append(
                    SourceChunk(
                        chunk_id=f"CHUNK-{len(groups) + 1:04d}",
                        line_start=start,
                        line_end=number - 1,
                        text=content,
                        truncated=truncated,
                    )
                )
                start, content, truncated = number, "", False
            content += line[:MAX_CHUNK_CHARS]
            truncated = truncated or len(line) > MAX_CHUNK_CHARS
        if content:
            groups.append(
                SourceChunk(
                    chunk_id=f"CHUNK-{len(groups) + 1:04d}",
                    line_start=start,
                    line_end=total,
                    text=content,
                    truncated=truncated,
                )
            )
        count = min(len(groups), MAX_CANDIDATE_CHUNKS)
        indices = sorted({round(i * (len(groups) - 1) / max(1, count - 1)) for i in range(count)})
        chunks = [groups[i] for i in indices]
        if count < len(groups):
            limits.append("Only sampled line ranges are available; omissions are explicit.")
        fmt, unit = ("MARKDOWN" if source_path.suffix.lower() == ".md" else "TXT"), "line"
    if not chunks or not any(c.text.strip() for c in chunks):
        raise ResearchError("Source has no readable text.")
    if any(chunk.truncated for chunk in chunks):
        limits.append("One or more source units exceed the character cap; excerpts are partial.")
    target = store.get_claim(ot_dir, pid, problem.primary_claim_id or "")
    target_text = target.statement if target else ""
    if len(statement) > MAX_CONTEXT_FIELD or len(target_text) > MAX_CONTEXT_FIELD:
        limits.append(
            "Problem/primary target text is bounded; inspect the original for full scope."
        )
    terminology = []
    if target:
        states = KnowledgeStateResolver(ot_dir).resolve(pid)
        for dependency in states[target.id].dependencies[:6]:
            record = store.get_claim(ot_dir, pid, dependency)
            state = states.get(dependency)
            if (
                record
                and state
                and state.authority == "CANONICAL"
                and state.usable_premise
                and re.search(r"definition|notation|定义|记号", record.statement, re.I)
            ):
                terminology.append({"record_id": record.id, "content": record.statement[:1000]})
    return SourceDigestContext(
        problem_id=pid,
        problem_statement=statement[:MAX_CONTEXT_FIELD],
        primary_target_id=target.id if target else None,
        primary_target_statement=target_text[:MAX_CONTEXT_FIELD],
        accepted_terminology=terminology,
        source_id=source_id,
        source_filename=filename,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        format=fmt,
        total_units=total,
        unit=unit,
        chunks=chunks,
        limitations=limits,
    )


def validate_support(
    context: SourceDigestContext, locator: Locator | None, span: str
) -> Literal["VALID", "PROVENANCE_INCOMPLETE", "INVALID"]:
    if locator is None or not span.strip():
        return "PROVENANCE_INCOMPLETE"
    if context.unit == "page":
        if (
            locator.page is None
            or locator.page_end is not None
            or locator.page > context.total_units
            or locator.line_start is not None
            or locator.line_end is not None
        ):
            return "INVALID"
        parts = [c for c in context.chunks if c.page == locator.page]
        text = "\n".join(c.text for c in parts)
    else:
        if (
            locator.page is not None
            or locator.page_end is not None
            or locator.line_start is None
            or locator.line_end is None
            or locator.line_start > locator.line_end
            or locator.line_end > context.total_units
        ):
            return "INVALID"
        parts = [
            c
            for c in context.chunks
            if c.line_start is not None
            and c.line_end is not None
            and c.line_start <= locator.line_start <= locator.line_end <= c.line_end
        ]
        text = "\n".join(
            "\n".join(
                c.text.splitlines()[
                    locator.line_start - (c.line_start or 1) : locator.line_end
                    - (c.line_start or 1)
                    + 1
                ]
            )
            for c in parts
        )
    if not parts:
        return "PROVENANCE_INCOMPLETE"

    def normalize(value: str) -> str:
        return " ".join(value.split())

    if normalize(span) not in normalize(text):
        return "INVALID"
    if locator.heading and not any(locator.heading in c.text for c in parts):
        return "INVALID"
    return "VALID"


def coverage(
    context: SourceDigestContext, processed: list[SourceChunk]
) -> tuple[list[Locator], list[Locator], bool]:
    ranges, covered = [], set()
    for chunk in processed:
        if chunk.page is not None:
            ranges.append(Locator(page=chunk.page))
            if not chunk.truncated:
                covered.add(chunk.page)
        else:
            ranges.append(Locator(line_start=chunk.line_start, line_end=chunk.line_end))
            if not chunk.truncated:
                covered.update(range(chunk.line_start or 1, (chunk.line_end or 0) + 1))
    omitted: list[Locator] = []
    start = None
    for number in range(1, context.total_units + 2):
        missing = number <= context.total_units and number not in covered
        if missing and start is None:
            start = number
        if not missing and start is not None:
            if context.unit == "page":
                omitted.append(Locator(page=start, page_end=number - 1))
            else:
                omitted.append(Locator(line_start=start, line_end=number - 1))
            start = None
    return ranges, omitted, not omitted
