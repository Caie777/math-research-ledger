"""Per-object full version snapshots, not a universal content-addressed blob store."""

from pathlib import Path

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError
from math_research.core.hashing import sha256
from math_research.core.refs import ObjectRef
from math_research.ledger.manifest import ManifestEntry


def version_directory(state: Path, ref: ObjectRef) -> Path:
    path = (
        state.resolve()
        / "ledger"
        / "versions"
        / (ref.problem_id or "_global")
        / ref.kind
        / ref.object_id
    )
    if not path.resolve().is_relative_to(state.resolve()):
        raise ResearchError("Version history escapes research state.")
    return path


def snapshot_entry(state: Path, entry: ManifestEntry) -> None:
    path = version_directory(state, entry.ref) / entry.version
    with file_lock(path.with_suffix(".snapshot")):
        manifest = path / "record.json"
        if manifest.is_file():
            return
        raw_artifacts: list[bytes | None] = []
        for artifact in entry.artifact_refs:
            if artifact["sha256"] is None:
                raw_artifacts.append(None)
                continue
            raw = Path(artifact["path"]).read_bytes()
            if sha256(raw) != artifact["sha256"]:
                raise ResearchError("Artifact changed while preserving its version history.")
            raw_artifacts.append(raw)
        path.mkdir(parents=True, exist_ok=True)
        for index, saved_raw in enumerate(raw_artifacts):
            if saved_raw is not None:
                (path / f"artifact-{index:04d}.bin").write_bytes(saved_raw)
        # Last file marks complete preservation; partial snapshots are not listed.
        atomic_write_text(manifest, entry.model_dump_json(indent=2))


def object_history(state: Path, ref: ObjectRef) -> list[dict]:
    import json

    return [
        json.loads(p.read_text("utf-8"))
        for p in sorted(version_directory(state, ref).glob("*/record.json"))
    ]
