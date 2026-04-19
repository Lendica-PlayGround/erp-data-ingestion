"""Ask an LLM to emit a Python script that performs the handshake mapping at runtime."""

from __future__ import annotations

import json
import logging
import py_compile
import re
import textwrap
from pathlib import Path

from openai import OpenAI

from .input_previews import build_inputs_section, phase2_columns_snippets
from .midlayer_catalog import table_columns
from .models import HandshakeRun

log = logging.getLogger(__name__)

_PKG_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PKG_DIR.parent


def _chat_completion_limit_kwargs(model: str, n: int) -> dict[str, int]:
    """OpenAI Chat Completions: newer models reject ``max_tokens`` (use ``max_completion_tokens``)."""
    m = (model or "").lower()
    if m.startswith("gpt-5") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        return {"max_completion_tokens": n}
    return {"max_tokens": n}


def load_handshake_run(path: Path) -> HandshakeRun:
    return HandshakeRun.model_validate_json(path.read_text(encoding="utf-8"))


def _read_text_limited(path: Path, max_chars: int) -> str:
    if not path.is_file():
        return f"(file not found: {path})"
    return path.read_text(encoding="utf-8")[:max_chars]


def _csv_spec_excerpt(path: Path | None) -> str:
    p = path or (_REPO_ROOT / "midlayer-schema-guide" / "midlayer-csv-spec.md")
    return _read_text_limited(p, 6000)


def _extract_python_block(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


CODEGEN_SYSTEM = """\
You are an expert Python engineer building data-ingestion mappers.

You will receive:
1) The Phase 2.5 handshake procedure (high-level goals).
2) A machine-readable `handshake_mapping.json` description: for each Phase 2 column, \
target mid-layer column(s) or `other`, plus `processing_steps` and confidence.
3) Optional previews of real source files (CSV/text).
4) Phase 2 `columns.json` snippets when available (datatypes, domains).
5) Mid-layer CSV formatting rules (types, nulls, money decimals, ISO timestamps).
6) Canonical mid-layer column order per table.

Your task: write **one complete Python 3.10+ script** that implements the handshake:

- Read source rows from **arbitrary user-supplied paths** passed on the command line (no hard-coded \
filenames). The Phase 2 backend always invokes: \
`python <script> --input <csv_path> --output <output_dir> --table <contacts|customers|invoices>`. \
You **must** implement these three flags with `argparse` (`--table` required). Support UTF-8. \
Discover columns from the CSV header at runtime. \
Write **exactly one** file: `<output_dir>/<table>_mapped.csv` where `<table>` matches `--table` \
(e.g. `contacts_mapped.csv` for `--table contacts`). Do not use other output basenames.
- For each table described in the handshake artifact, map columns according to \
`phase2_column` → `midlayer_columns` and apply `processing_steps` literally where they \
describe transforms. If `midlayer_columns` is `["other"]`, route the value into `_unmapped` \
as JSON (alphabetical keys) per spec.
- Emit **mid-layer CSV** rows: header exactly the canonical column list for that \
`midlayer_table`, values obeying the CSV spec (empty string for null, booleans `true`/`false`, \
money with 4 decimal places when applicable, ISO 8601 UTC with `Z` for datetimes).
- Do **not** hard-code client-specific column names beyond what is already in the handshake \
JSON and file previews; derive behavior from that data structures at runtime where possible \
(e.g. iterate `HANDSHAKE_TABLES` embedded as parsed JSON or dict literals loaded from a \
constant in the script).
- Prefer the standard library (`csv`, `json`, `datetime`, `decimal`, `argparse`, `pathlib`). \
You may use `pandas` only if clearly needed; if you use it, import it and note it in the docstring.
- The script must be **runnable**: \
`python generated_mapper.py --input /path/to/source.csv --output /tmp/out --table contacts` \
(never embed a specific client filename in the code).
- Include a short module docstring stating the script was produced from a handshake artifact \
and is table-specific or multi-table as appropriate.
- If multiple mid-layer tables exist in the handshake, still use **one `--table` per run**; the \
backend calls the script once per table. Unsupported `--table` values should exit with a clear \
error on stderr.

Output **only** the Python source code. No markdown outside a single ```python block is OK; \
if you use a fence, put the entire program inside it. No explanations before or after.
"""


def generate_handshake_mapper_script(
    *,
    client: OpenAI,
    model: str,
    handshake: HandshakeRun,
    input_paths: list[Path],
    phase2_output: Path | None,
    procedure_md_path: Path | None,
    midlayer_csv_spec_path: Path | None,
) -> str:
    proc_p = procedure_md_path or (_PKG_DIR / "phase2.5.md")
    procedure = _read_text_limited(proc_p, 4000)
    csv_rules = _csv_spec_excerpt(midlayer_csv_spec_path)
    previews = build_inputs_section(input_paths)
    slugs = [t.phase2_table for t in handshake.tables]
    phase2_cols = ""
    if phase2_output and phase2_output.is_dir():
        phase2_cols = phase2_columns_snippets(phase2_output, slugs)

    canonical = table_columns()
    _MAX_HANDSHAKE_JSON = 35_000
    hs_json = handshake.model_dump_json(indent=2)
    if len(hs_json) > _MAX_HANDSHAKE_JSON:
        hs_json = (
            hs_json[:_MAX_HANDSHAKE_JSON]
            + "\n... [truncated: handshake JSON exceeded token budget; reduce column count or step text] ..."
        )

    user = textwrap.dedent(
        f"""\
        ## Phase 2.5 procedure (from phase2.5.md)
        {procedure}

        ## handshake_mapping.json (artifact to implement; may be truncated if very large)
        ```json
        {hs_json}
        ```

        ## Canonical mid-layer CSV column order (enforce headers in this order)
        ```json
        {json.dumps(canonical, indent=2)}
        ```

        ## Mid-layer CSV spec excerpt
        ```markdown
        {csv_rules}
        ```

        ## Phase 2 columns.json (per table, when present)
        {phase2_cols or "(not provided)"}

        ## Source file previews (actual input data shape)
        {previews}

        Generate the mapper script now.
        """
    )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CODEGEN_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        **_chat_completion_limit_kwargs(model, 8192),
    )
    choice = completion.choices[0].message.content
    if not choice:
        raise RuntimeError("Empty response from model")
    code = _extract_python_block(choice)
    if not code.strip():
        raise RuntimeError("Model returned no Python code")
    return code


def verify_compiles(path: Path) -> None:
    py_compile.compile(str(path), doraise=True)


def write_mapper_script(code: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(code.rstrip() + "\n", encoding="utf-8")
