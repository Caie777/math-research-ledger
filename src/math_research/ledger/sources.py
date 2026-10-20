"""Explicit raw uploads in the existing pinned Paper store; never Episode parsing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PureWindowsPath

from math_research.core.atomicio import file_lock
from math_research.core.errors import ResearchError
from math_research.core.jsonl import next_sequential_id
from math_research.core.limits import MAX_UPLOAD_BYTES
from math_research.ledger.records import store
from math_research.ledger.records.write_boundary import human_write
from math_research.ledger.source_records import Paper, _save_meta, list_papers

SOURCE_CONNECTOR = "harness_source"


@dataclass(frozen=True)
class SourceUpload:
    filename: str
    content: bytes

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def validate_source(filename: str, content: bytes) -> SourceUpload:
    name = PureWindowsPath(filename)
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if (
        not filename
        or name.name != filename
        or name.drive
        or any(c in filename for c in '/\\:\x00<>"|?*')
        or filename.endswith((" ", "."))
        or filename.split(".", 1)[0].upper() in reserved
        or len(filename.encode("utf-16-le")) > 510
    ):
        raise ResearchError("Source filename must be a plain filename, never a path.")
    suffix = name.suffix.lower()
    if suffix not in {".md", ".txt", ".pdf"}:
        raise ResearchError("Source supports .md / .txt / .pdf only.")
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ResearchError("Source must be nonempty and at most 10 MiB.")
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            if not content.startswith(b"%PDF-"):
                raise ValueError("Not PDF")
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError("Encrypted PDF")
            len(reader.pages)
        except Exception as exc:
            raise ResearchError(
                "Source PDF is invalid or encrypted; supply a readable PDF."
            ) from exc
    else:
        try:
            text = content.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError("Binary input")
        except (UnicodeError, ValueError) as exc:
            raise ResearchError("Text source must be UTF-8 and contain no NUL bytes.") from exc
    return SourceUpload(filename, content)


def source_papers(ot_dir: Path, pid: str) -> list[Paper]:
    store.require_dossier(ot_dir, pid)
    linked = {r.paper_artifact for r in store.list_related_papers(ot_dir, pid)}
    return [
        p
        for p in list_papers(ot_dir)
        if p.id in linked
        and (
            p.source_connector == SOURCE_CONNECTOR
            or p.source_connector is None
            and p.pinned
            and p.local_path is not None
            and Path(p.local_path).suffix.lower() in {".pdf", ".md", ".txt"}
        )
    ]


def read_source(ot_dir: Path, pid: str, ident: str) -> tuple[Paper, Path, bytes]:
    paper = next((p for p in source_papers(ot_dir, pid) if p.id == ident), None)
    if paper is None or paper.local_path is None:
        raise ResearchError("Source not found in this Problem.")
    root = (ot_dir / "papers" / paper.id).resolve()
    path = (ot_dir / paper.local_path).resolve()
    if not root.is_relative_to(ot_dir.resolve()) or not path.is_relative_to(root):
        raise ResearchError("Source path is outside its pinned Paper directory.")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != paper.sha256:
        raise ResearchError("Pinned source SHA-256 mismatch.")
    return paper, path, raw


@human_write
def save_source(ot_dir: Path, pid: str, upload: SourceUpload) -> Paper:
    store.require_dossier(ot_dir, pid)
    # Existing Paper metadata + existing Problem related_papers; no second source index.
    with file_lock(ot_dir / "papers" / ".source-upload"):
        existing = next(
            (
                p
                for p in source_papers(ot_dir, pid)
                if p.sha256 == upload.digest and p.title == upload.filename
            ),
            None,
        )
        if existing:
            read_source(ot_dir, pid, existing.id)
            return existing
        ident = next_sequential_id("PAPER", len(list_papers(ot_dir)))
        sequence = len(list_papers(ot_dir))
        while (ot_dir / "papers" / ident).exists():
            sequence += 1
            ident = next_sequential_id("PAPER", sequence)
        relative = Path("papers") / ident / ("source" + Path(upload.filename).suffix.lower())
        path = ot_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(upload.content)
        paper = Paper(
            id=ident,
            source=upload.filename,
            source_type="manual",
            title=upload.filename,
            local_path=relative.as_posix(),
            sha256=upload.digest,
            pinned=True,
            source_connector=SOURCE_CONNECTOR,
            full_text_accessible=True,
            note_path=relative.as_posix() if path.suffix != ".pdf" else None,
            access_note="User-supplied raw source. No Episode decomposition or theorem extraction.",
        )
        _save_meta(ot_dir, paper)
        store.add_related_paper(
            ot_dir,
            pid,
            title=upload.filename,
            source=relative.as_posix(),
            paper_artifact=ident,
            relevance="User-supplied source material; not a mathematical object.",
        )
        return paper
