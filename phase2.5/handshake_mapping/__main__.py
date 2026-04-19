"""CLI: map subcommand (handshake JSON) and codegen subcommand (Python mapper script)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import py_compile
import sys
from pathlib import Path

from openai import APIError, AuthenticationError, OpenAI

from .config import get_settings


def _openai_api_key() -> str:
    """Prefer process environment (e.g. Phase 2 API subprocess) over phase2.5/.env."""
    env_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if env_key:
        return env_key
    return get_settings().openai_api_key.strip()
from .llm_map import map_phase2_table
from .mapper_codegen import (
    generate_handshake_mapper_script,
    load_handshake_run,
    verify_compiles,
    write_mapper_script,
)
from .models import HandshakeRun, utc_now_iso
from .phase2_loader import discover_tables

log = logging.getLogger(__name__)


def _normalize_argv(argv: list[str]) -> list[str]:
    """Default to `map` so existing `python -m handshake_mapping -v` keeps working."""
    if not argv:
        return ["map"]
    if argv[0] in ("-h", "--help"):
        return ["map"] + argv
    if argv[0] not in ("map", "codegen"):
        return ["map"] + argv
    return argv


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Phase 2.5: AI handshake mapping (map) and mapper codegen (codegen).",
    )
    sub = p.add_subparsers(dest="command", required=False)

    mp = sub.add_parser("map", help="Build handshake_mapping.json from Phase 2 output.")
    mp.add_argument(
        "--phase2-output",
        type=Path,
        default=None,
        help="Path to phase2/output (default: PHASE25_PHASE2_OUTPUT_DIR)",
    )
    mp.add_argument(
        "--midlayer-schema-dir",
        type=Path,
        default=None,
        help="Path to midlayer/v1 (default: PHASE25_MIDLAYER_SCHEMA_DIR)",
    )
    mp.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: PHASE25_OUTPUT_FILE)",
    )
    mp.add_argument(
        "--model",
        default=None,
        help="OpenAI model (default: PHASE25_MODEL or gpt-4o)",
    )
    mp.add_argument(
        "--tables",
        nargs="*",
        help="Optional subset of Phase 2 table slugs to map.",
    )
    mp.add_argument(
        "--validate-only",
        action="store_true",
        help="Load inputs and exit without calling the API.",
    )
    mp.add_argument("-v", "--verbose", action="store_true")

    cg = sub.add_parser(
        "codegen",
        help="Ask the model to emit a Python script that runs the handshake on source files.",
    )
    cg.add_argument(
        "--handshake",
        type=Path,
        default=None,
        help="handshake_mapping.json from `map` (default: PHASE25_OUTPUT_FILE)",
    )
    cg.add_argument(
        "--input",
        dest="input_paths",
        action="append",
        type=Path,
        default=None,
        help="Sample source file(s) (repeatable), e.g. client CSV exports.",
    )
    cg.add_argument(
        "--phase2-output",
        type=Path,
        default=None,
        help="Phase 2 output dir to attach columns.json per table (default: PHASE25_PHASE2_OUTPUT_DIR)",
    )
    cg.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write generated Python here (default: PHASE25_MAPPER_SCRIPT_OUT)",
    )
    cg.add_argument(
        "--procedure-md",
        type=Path,
        default=None,
        help="Override path to phase2.5.md procedure text.",
    )
    cg.add_argument(
        "--midlayer-csv-spec",
        type=Path,
        default=None,
        help="Override path to midlayer-csv-spec.md.",
    )
    cg.add_argument(
        "--model",
        default=None,
        help="OpenAI model (default: PHASE25_MODEL)",
    )
    cg.add_argument(
        "--skip-compile-check",
        action="store_true",
        help="Do not run py_compile on the generated file.",
    )
    cg.add_argument(
        "--validate-only",
        action="store_true",
        help="Load handshake + inputs and exit without calling the API.",
    )
    cg.add_argument("-v", "--verbose", action="store_true")

    return p


def cmd_map(args: argparse.Namespace) -> int:
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

    if not _openai_api_key():
        log.error(
            "OPENAI_API_KEY is not set. From phase2.5 run: "
            "cp .env.example .env  (two paths only — no extra words after .env), "
            "then edit .env and replace the placeholder key, or export OPENAI_API_KEY in the shell."
        )
        return 2

    client = OpenAI(api_key=_openai_api_key())
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


def cmd_codegen(args: argparse.Namespace) -> int:
    settings = get_settings()
    handshake_path = args.handshake or settings.output_path
    out_path = args.out or settings.mapper_script_path
    model = args.model or settings.model
    phase2_out = args.phase2_output or settings.phase2_output_path
    input_paths = list(args.input_paths or [])

    if not handshake_path.is_file():
        log.error("Handshake JSON not found: %s (run `map` first)", handshake_path)
        return 2

    hs = load_handshake_run(handshake_path)

    if args.validate_only:
        log.info(
            "Loaded handshake (%d tables), %d input file(s), phase2-output=%s",
            len(hs.tables),
            len(input_paths),
            phase2_out,
        )
        for p in input_paths:
            log.info("  input: %s exists=%s", p, p.is_file())
        log.info("validate-only: skipping API calls.")
        return 0

    if not _openai_api_key():
        log.error("OPENAI_API_KEY is not set.")
        return 2

    client = OpenAI(api_key=_openai_api_key())
    log.info("Generating mapper script → %s", out_path)
    try:
        code = generate_handshake_mapper_script(
            client=client,
            model=model,
            handshake=hs,
            input_paths=input_paths,
            phase2_output=phase2_out if phase2_out.is_dir() else None,
            procedure_md_path=args.procedure_md,
            midlayer_csv_spec_path=args.midlayer_csv_spec,
        )
    except AuthenticationError as e:
        log.error("OpenAI authentication failed: %s", e)
        return 2
    except APIError as e:
        log.error("OpenAI API error: %s", e)
        return 2

    write_mapper_script(code, out_path)
    log.info("Wrote %s", out_path)

    if not args.skip_compile_check:
        try:
            verify_compiles(out_path)
            log.info("py_compile OK")
        except py_compile.PyCompileError as e:
            log.error("Generated script failed py_compile: %s", e)
            log.error("Fix the script manually or re-run codegen with a different model.")
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    get_settings.cache_clear()
    argv = _normalize_argv(list(argv if argv is not None else sys.argv[1:]))
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.command == "codegen":
        return cmd_codegen(args)
    return cmd_map(args)


if __name__ == "__main__":
    raise SystemExit(main())
