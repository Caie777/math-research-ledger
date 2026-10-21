"""Workspace discovery and path-safety helpers.

Every file operation in MathResearch Ledger must stay inside the workspace root. The
:func:`resolve_workspace_path` helper is the single choke point that enforces
this: it resolves a user-supplied path against the workspace root and refuses
anything that would escape it (``..`` traversal or absolute paths pointing
elsewhere).
"""

from __future__ import annotations

from pathlib import Path

from math_research.core.errors import PathTraversalError, ResearchError

WORKSPACE_DIRNAME = ".math-research-ledger"
LEGACY_WORKSPACE_DIRNAME = ".math-research"
STATE_DIRNAMES = (WORKSPACE_DIRNAME, LEGACY_WORKSPACE_DIRNAME)
MIGRATION_JOURNAL = ".math-research-ledger-migration.json"


def state_at(root: Path) -> Path | None:
    """One active ledger per workspace; legacy reads never migrate or write."""
    from math_research.core.config import workspace_config

    if root.name in STATE_DIRNAMES:
        root = root.parent
    if (root / MIGRATION_JOURNAL).exists():
        raise ResearchError("Interrupted migration; run math-research-ledger migrate --rollback.")
    found = [root / name for name in STATE_DIRNAMES if (root / name).exists()]
    if len(found) > 1:
        raise ResearchError(
            "Conflicting active state directories; preserve both and resolve explicitly."
        )
    if not found:
        return None
    state = found[0]
    if state.is_symlink() or not state.is_dir():
        raise ResearchError("Research state must be a directory, not a symlink or file.")
    config = workspace_config(root)
    if config and (config.workspace_version == 2) != (state.name == WORKSPACE_DIRNAME):
        raise ResearchError("workspace_version/state directory mismatch; migrate explicitly.")
    return state


def find_workspace_root(start: Path | None = None) -> Path | None:
    """Return the nearest ancestor directory containing ``.math-research-ledger``.

    Walks upward from ``start`` (default: current working directory). Returns
    ``None`` if no initialized workspace is found.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if state_at(candidate) is not None:
            return candidate
    return None


def looks_like_uninitialized_project(path: Path) -> bool:
    """True when ``path`` has project folders but no ``.math-research-ledger/`` yet."""
    if state_at(path) is not None:
        return False
    return (path / "papers").is_dir()


def resolve_cli_workspace_root(start: Path | None = None) -> Path | None:
    """Resolve the workspace root for CLI commands run from ``start``.

    Unlike :func:`find_workspace_root`, this refuses to bind a subdirectory to a
    parent workspace when the current directory already looks like its own
    project (e.g. ``papers/`` without ``.math-research-ledger/``), or when the only match
    would be the user's home directory while the command runs in a child folder.
    """
    cwd = (start or Path.cwd()).resolve()
    if state_at(cwd) is not None:
        return cwd

    if looks_like_uninitialized_project(cwd):
        return None

    found = find_workspace_root(cwd)
    if found is None:
        return None

    home = Path.home().resolve()
    if found == home and cwd != home:
        return None

    return found if found != cwd else cwd


def _strip_component_whitespace(user_path: str) -> str:
    """Trim whitespace around each path component and drop the ones left empty.

    A path component that begins or ends with a space, or contains a newline, is not a
    filename anybody meant to write — it is the same output corruption that turns
    ``read_file`` into ``read_ file``. Left alone it succeeds silently and litters the
    project: a run wrote ``" \\nscripts/verify_6. py"`` and created a real directory
    named two-spaces-newline-scripts, outside ``.math-research-ledger/`` so no re-run cleans it up,
    with the script unreachable from every sane path the model tried afterwards.

    Only the component boundaries are touched. A space *inside* a name is legitimate
    ("my notes.md") and is left exactly as written.
    """
    separator = "\\" if "\\" in user_path and "/" not in user_path else "/"
    parts = [part.strip() for part in user_path.split(separator)]
    # An empty first part is a leading separator (absolute path) and must survive.
    kept = [part for index, part in enumerate(parts) if part or index == 0]
    cleaned = separator.join(kept)
    return cleaned if cleaned.strip() else user_path


def resolve_workspace_path(workspace_root: Path | str, user_path: Path | str) -> Path:
    """Resolve ``user_path`` against ``workspace_root`` without allowing escape.

    Raises :class:`PathTraversalError` if the resolved path would fall outside
    the workspace root (via ``..`` traversal or an absolute path pointing
    elsewhere).
    """
    root = Path(workspace_root).resolve()
    candidate = Path(_strip_component_whitespace(str(user_path)))

    # Anchor relative paths to the workspace root; absolute paths are taken as-is
    # and validated below so that e.g. ``/etc/passwd`` is rejected.
    combined = candidate if candidate.is_absolute() else root / candidate
    resolved = combined.resolve()

    if resolved != root and root not in resolved.parents:
        raise PathTraversalError(
            f"Path '{user_path}' resolves outside the workspace root '{root}'."
        )
    return resolved
