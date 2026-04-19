"""Git helpers scoped to ``phase2/output/``.

The outer repo is already a git repository. We only ever stage paths that
live under the configured output directory so the agent can never touch
unrelated files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from git import InvalidGitRepositoryError, Repo

from .settings import get_settings

log = logging.getLogger(__name__)


@dataclass
class CommitRecord:
    sha: str
    short_sha: str
    message: str
    timestamp: float
    author: str
    files: list[str]


def _repo() -> Repo | None:
    out = get_settings().output_path
    try:
        return Repo(out, search_parent_directories=True)
    except InvalidGitRepositoryError:
        log.warning("phase2/output is not inside a git repository; commits disabled")
        return None


def _rel_to_repo(repo: Repo, paths: Iterable[Path]) -> list[str]:
    root = Path(repo.working_tree_dir).resolve()
    rel: list[str] = []
    for p in paths:
        p = Path(p).resolve()
        try:
            rel.append(str(p.relative_to(root)))
        except ValueError:
            continue
    return rel


def commit_output(message: str, paths: Iterable[Path] | None = None) -> CommitRecord | None:
    """Stage ``paths`` (or the whole output dir) and commit.

    Only paths under ``phase2/output`` are accepted. If nothing is staged,
    no commit is created and ``None`` is returned.
    """
    repo = _repo()
    if repo is None:
        return None

    out = get_settings().output_path
    if paths is None:
        paths = [out]

    safe: list[Path] = []
    for p in paths:
        p = Path(p).resolve()
        try:
            p.relative_to(out)
        except ValueError:
            log.warning("refusing to stage path outside output dir: %s", p)
            continue
        safe.append(p)

    if not safe:
        return None

    rel = _rel_to_repo(repo, safe)
    if not rel:
        return None

    repo.index.add(rel)
    if not repo.index.diff("HEAD") and not repo.untracked_files:
        return None
    # Double-check there's staged content (diff("HEAD") can be empty on an
    # empty-tree repo; fall back to a status check).
    if not repo.git.diff("--cached", "--name-only").strip():
        return None

    commit = repo.index.commit(message)
    changed = repo.git.show("--name-only", "--pretty=format:", commit.hexsha).strip().splitlines()
    return CommitRecord(
        sha=commit.hexsha,
        short_sha=commit.hexsha[:7],
        message=commit.message.strip(),
        timestamp=float(commit.committed_date),
        author=commit.author.name or "agent",
        files=[f for f in changed if f],
    )


def recent_commits(limit: int = 50) -> list[CommitRecord]:
    repo = _repo()
    if repo is None:
        return []
    out = get_settings().output_path
    root = Path(repo.working_tree_dir).resolve()
    try:
        rel = str(out.relative_to(root))
    except ValueError:
        rel = None

    records: list[CommitRecord] = []
    kwargs = {"max_count": limit, "paths": rel} if rel else {"max_count": limit}
    for commit in repo.iter_commits(**kwargs):
        files = repo.git.show(
            "--name-only", "--pretty=format:", commit.hexsha
        ).strip().splitlines()
        records.append(
            CommitRecord(
                sha=commit.hexsha,
                short_sha=commit.hexsha[:7],
                message=commit.message.strip(),
                timestamp=float(commit.committed_date),
                author=commit.author.name or "agent",
                files=[f for f in files if f],
            )
        )
    return records


def commit_diff(sha: str) -> str:
    repo = _repo()
    if repo is None:
        return ""
    return repo.git.show(sha, "--pretty=fuller")
