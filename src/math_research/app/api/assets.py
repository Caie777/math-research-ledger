"""Problem-scoped retained asset metadata and bounded, hash-checked byte previews."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from math_research.memory.assets import (
    AssetIntegrityError,
    AssetNotFoundError,
    AssetNotRetainedError,
    find_research_assets,
    lookup_research_asset,
    read_research_asset,
    resolve_research_asset,
)
from math_research.memory.records import store


def install_asset_routes(app: FastAPI, ot_dir: Path) -> None:
    def scoped(problem_id: str) -> None:
        store.require_dossier(ot_dir, problem_id)

    @app.get("/api/problems/{problem_id}/research-assets")
    def discover(
        problem_id: str,
        object_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(12, ge=1, le=20),
    ) -> dict:
        scoped(problem_id)
        refs = find_research_assets(ot_dir, problem_id, object_id)
        page = refs[offset : offset + limit]
        try:
            for ref in page:
                resolve_research_asset(ot_dir, ref)
        except (AssetIntegrityError, AssetNotFoundError) as exc:
            raise unavailable(exc) from exc
        return {
            "assets": [r.model_dump(mode="json") for r in page],
            "total": len(refs),
            "offset": offset,
            "truncated": offset + limit < len(refs),
        }

    def unavailable(exc: Exception) -> HTTPException:
        status = (
            409
            if isinstance(exc, AssetIntegrityError)
            else 403
            if isinstance(exc, AssetNotRetainedError)
            else 404
        )
        return HTTPException(status, str(exc))

    @app.get("/api/problems/{problem_id}/research-assets/{asset_id}")
    def metadata(problem_id: str, asset_id: str) -> dict:
        scoped(problem_id)
        try:
            ref = lookup_research_asset(ot_dir, problem_id, asset_id)
            resolve_research_asset(ot_dir, ref)
            return ref.model_dump(mode="json")
        except (AssetIntegrityError, AssetNotFoundError, AssetNotRetainedError) as exc:
            raise unavailable(exc) from exc

    @app.get("/api/problems/{problem_id}/research-assets/{asset_id}/content")
    def content(
        problem_id: str,
        asset_id: str,
        offset: int = Query(0, ge=0),
        length: int = Query(4000, ge=1, le=4000),
    ) -> dict:
        scoped(problem_id)
        try:
            # Verify and preview from the same read; do not reopen via FileResponse.
            return read_research_asset(ot_dir, problem_id, asset_id, offset=offset, length=length)
        except (AssetIntegrityError, AssetNotFoundError, AssetNotRetainedError) as exc:
            raise unavailable(exc) from exc
