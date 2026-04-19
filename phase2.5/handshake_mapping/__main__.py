"""CLI: generate handshake_mapping.json from Phase 2 output + mid-layer schemas."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from openai import OpenAI

from .config import get_settings
from .llm_map import map_phase2_table
from .models import HandshakeRun, utc_now_iso
from .phase2_loader import discover_tables

log = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AI-powered column mapping from phase2/output to mid-layer v1.",
    )
    p.add_argument(
        "--phase2-output",
        type=Path,
        default=None,
        help="Path to phase2/output (default: PHASE25_PHASE2_OUTPUT_DIR)",
    )
    p.add_argument(
        "--midlayer-schema-dir",
        type=Path,
        default=None,
        help="Path to midlayer/v1 (default: PHASE25_MIDLAYER_SCHEMA_DIR)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: PHASE25_OUTPUT_FILE)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="OpenAI model (default: PHASE25_MODEL or gpt-4o)",
    )
    p.add_argument(
        "--tables",
        nargs="*",
        help="Optional subset of Phase 2 table slugs to map.",
    )
    p.add_argument(
        "--validate-only",
        action="store_true",
        help="Load inputs and exit without calling the API.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    settings = get_settings()
    phase2_out = args.phase2_output or settings.phase2_output_path
    midlayer_v1 = args.midlayer_schema_dir or settings.midlayer_schema_path
    out_path = args.out or settings.output_path
    model = args.model or settings.model

    if not phase2_out.is_dir():
        log.error("Phase 2 output directory not found: %s", phase2_out)
        return 2
    if not midlayer_v1.is_dir():
        log.error("Mid-layer schema directory not found: %s", midlayer_v1)
        return 2

    tables = discover_tables(phase2_out)
    if args.tables:
        want = {t.lower() for t in args.tables}
        tables = [t for t in tables if t.slug.lower() in want]

    if not tables:
        log.error("No Phase 2 tables found under %s/tables", phase2_out)
        return 2

    if args.validate_only:
        for t in tables:
            log.info("OK %s (%d columns)", t.slug, len(t.columns_doc.get("columns", [])))
        log.info("validate-only: skipping API calls.")
        return 0

    if not settings.openai_api_key.strip():
        log.error(
            "OPENAI_API_KEY is not set. From phase2.5 run: "
            "cp .env.example .env  (two paths only — no extra words after .env), "
            "then edit .env and replace the placeholder key, or export OPENAI_API_KEY in the shell."
        )
        return 2

    client = OpenAI(api_key=settings.openai_api_key)
    mapped = []
    for pt in tables:
        log.info("Mapping table %s …", pt.slug)
        th = map_phase2_table(pt, client=client, model=model, midlayer_v1=midlayer_v1)
        mapped.append(th)

    run = HandshakeRun(
        generated_at=utc_now_iso(),
        phase2_output_dir=str(phase2_out),
        midlayer_schema_dir=str(midlayer_v1),
        model=model,
        tables=mapped,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(run.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log.info("Wrote %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
