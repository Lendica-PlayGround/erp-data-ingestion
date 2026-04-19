"""Supabase Vault / Nebius secrets accessors (reference-by-id only in configs)."""

from __future__ import annotations

import os
from typing import Protocol


class SecretResolver(Protocol):
    def resolve(self, ref: str) -> str: ...


class EnvSecretResolver:
    """Dev helper: map `env:STRIPE_API_KEY` to os.environ."""

    def resolve(self, ref: str) -> str:
        if ref.startswith("env:"):
            key = ref[4:]
            return os.environ[key]
        raise ValueError(f"Unsupported secret ref: {ref}")
