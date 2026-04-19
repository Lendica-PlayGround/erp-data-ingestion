"""Load Mira bootstrap markdown (PRD §2.6) for system prompt injection."""

from __future__ import annotations

from pathlib import Path

_BOOTSTRAP_DIR = Path(__file__).resolve().parent.parent / "mira"


def load_bootstrap_text(extra_user_md: str | None = None) -> str:
    parts: list[str] = []
    order = [
        "IDENTITY.md",
        "SOUL.md",
        "AGENTS.md",
        "TOOLS.md",
        "USER.md",
        "BOOTSTRAP.md",
    ]
    for name in order:
        p = _BOOTSTRAP_DIR / name
        if p.is_file():
            parts.append(f"<!-- {name} -->\n{p.read_text(encoding='utf-8')}")
    if extra_user_md:
        parts.append("<!-- runtime USER override -->\n" + extra_user_md)
    return "\n\n".join(parts)
