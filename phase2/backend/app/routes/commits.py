"""GET /commits — git log for phase2/output/."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from .. import git_ops

router = APIRouter()


@router.get("/commits")
async def list_commits(limit: int = 50) -> dict:
    commits = git_ops.recent_commits(limit=max(1, min(limit, 200)))
    return {"commits": [asdict(c) for c in commits]}


@router.get("/commits/{sha}")
async def commit_diff(sha: str) -> dict:
    if not sha.isalnum():
        raise HTTPException(400, "invalid sha")
    diff = git_ops.commit_diff(sha)
    if not diff:
        raise HTTPException(404, "commit not found or no git repo")
    return {"sha": sha, "diff": diff}
