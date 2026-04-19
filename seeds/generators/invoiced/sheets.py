"""
Google Sheets I/O helpers for the Invoiced feeder.

- Flattens Invoiced-shaped dicts to rows in the column order defined by
  ``schemas.py``. Nested objects/arrays are JSON-serialised into ``*_json``
  columns, preserving full fidelity.
- Handles credential loading: ``GOOGLE_SHEETS_SA_KEY`` (inline JSON or path to
  a key file), then ``GOOGLE_APPLICATION_CREDENTIALS`` (service account JSON path), else
  Application Default Credentials (e.g. ``gcloud auth application-default login``).
- Provides ``open_or_create_worksheet`` to ensure the target tab exists
  with the right header row.

Depends only on ``gspread`` + ``google-auth``; no extra DB / ORM.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    import google.auth
    import gspread
    from gspread.exceptions import APIError as GspreadAPIError
    from google.auth.credentials import Credentials as GoogleAuthCredentials
    from google.auth.exceptions import DefaultCredentialsError
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
except ImportError as exc:  # pragma: no cover - import-time guard
    raise SystemExit(
        f"Missing dependency: {exc.name}. "
        "Install with `pip install -r requirements.txt`."
    ) from exc


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# When overriding `--scopes` for `gcloud auth application-default login`, gcloud
# requires cloud-platform in the list; the client libraries still use SCOPES above.
GCLOUD_ADC_LOGIN_SCOPES_CSV = (
    "https://www.googleapis.com/auth/cloud-platform," + ",".join(SCOPES)
)

# Columns in the schema headers that are pre-serialised JSON payloads.
# Any raw dict/list value for one of these columns is ``json.dumps``-ed.
_JSON_COLUMN_SUFFIX = "_json"


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def load_credentials() -> GoogleAuthCredentials:
    """Resolve creds: inline SA JSON, SA key file path, or Application Default Credentials."""
    sa_raw = os.environ.get("GOOGLE_SHEETS_SA_KEY", "").strip()
    if sa_raw:
        try:
            info = json.loads(sa_raw)
        except json.JSONDecodeError:
            p = Path(sa_raw).expanduser()
            if p.is_file():
                return ServiceAccountCredentials.from_service_account_file(
                    str(p), scopes=SCOPES
                )
            raise SystemExit(
                "GOOGLE_SHEETS_SA_KEY is set but is neither valid JSON nor an existing file path. "
                "Paste the service-account key as a single-line JSON string, or set it to the "
                "path of a .json key file, or use GOOGLE_APPLICATION_CREDENTIALS."
            )
        return ServiceAccountCredentials.from_service_account_info(info, scopes=SCOPES)

    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            raise SystemExit(
                f"GOOGLE_APPLICATION_CREDENTIALS={path!r} does not point to a file."
            )
        return ServiceAccountCredentials.from_service_account_file(str(p), scopes=SCOPES)

    try:
        creds, _ = google.auth.default(scopes=SCOPES)
    except DefaultCredentialsError as exc:
        raise SystemExit(
            "No Google credentials found. Set GOOGLE_SHEETS_SA_KEY (inline JSON), "
            "GOOGLE_APPLICATION_CREDENTIALS (service account key file path), "
            "or run `gcloud auth application-default login` for user credentials "
            "(your Google account must have access to the spreadsheet). "
            "See .env.example."
        ) from exc
    return creds


def _gspread_api_error_from_exc(exc: BaseException) -> GspreadAPIError | None:
    if isinstance(exc, PermissionError) and isinstance(exc.__cause__, GspreadAPIError):
        return exc.__cause__
    if isinstance(exc, GspreadAPIError):
        return exc
    return None


def _exit_if_known_gspread_403(exc: BaseException) -> None:
    """Replace opaque PermissionError with actionable hints for common 403 bodies."""
    err = _gspread_api_error_from_exc(exc)
    if err is None:
        return
    code = getattr(err.response, "status_code", None)
    if code != 403:
        return
    try:
        body = err.response.text or ""
    except Exception:  # pragma: no cover - defensive
        body = ""
    bl = body.lower()

    if "insufficient authentication scopes" in bl:
        raise SystemExit(
            "Google Sheets API returned 403: insufficient authentication scopes. "
            "Application Default Credentials from `gcloud auth application-default login` "
            "are scoped to cloud-platform by default, not Sheets.\n\n"
            "Re-authorize; when you pass --scopes, gcloud also requires cloud-platform "
            "in the same list:\n\n"
            f"  gcloud auth application-default login --scopes={GCLOUD_ADC_LOGIN_SCOPES_CSV}\n\n"
            "If gcloud warns that Sheets/Drive scopes are blocked for the default OAuth client, "
            "use GOOGLE_APPLICATION_CREDENTIALS / GOOGLE_SHEETS_SA_KEY (service account) "
            "or your own OAuth client ID (see Google Cloud ADC troubleshooting)."
        ) from exc

    if "has not been used in project" in bl or (
        "api has not been used" in bl and "sheets" in bl
    ):
        m = re.search(
            r"https://console\.developers\.google\.com/apis/api/sheets\.googleapis\.com[^\s\"'<>]+",
            body,
        )
        link = m.group(0) if m else (
            "https://console.cloud.google.com/apis/library/sheets.googleapis.com"
        )
        raise SystemExit(
            "Google Sheets API is disabled or has never been enabled for the GCP project "
            "that owns this credential (e.g. the service account key's project).\n\n"
            f"Enable it (same project as in the error): {link}\n\n"
            "If you use Drive operations, also enable Google Drive API in that project. "
            "Wait a few minutes after enabling, then retry."
        ) from exc


# ---------------------------------------------------------------------------
# Worksheet bootstrap
# ---------------------------------------------------------------------------

def open_or_create_worksheet(
    client: gspread.Client,
    spreadsheet_id: str,
    title: str,
    headers: Sequence[str],
) -> gspread.Worksheet:
    try:
        sh = client.open_by_key(spreadsheet_id)
    except PermissionError as exc:
        _exit_if_known_gspread_403(exc)
        raise
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=2000, cols=max(26, len(headers)))
        ws.update("A1", [list(headers)], value_input_option="RAW")
        return ws

    first_row = ws.row_values(1)
    if not first_row:
        ws.update("A1", [list(headers)], value_input_option="RAW")
    elif first_row[: len(headers)] != list(headers):
        log.warning(
            "Worksheet %r header does not match generator schema; "
            "appending rows anyway. Existing header: %s",
            title, first_row,
        )
    return ws


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _as_cell(value: Any) -> str:
    """Coerce any Python value into a cell string.

    Rules:
    - ``None`` → "" (matches how Invoiced null-ables round-trip through CSV).
    - ``bool`` → "true"/"false".
    - ``dict`` / ``list`` → ``json.dumps`` with stable sort.
    - ``int`` / ``float`` / ``str`` → ``str(value)``.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def record_to_row(record: dict, headers: Sequence[str]) -> list[str]:
    """Flatten a record dict into a row, honoring the ``*_json`` convention.

    For a header ``foo_json`` we look up ``record["foo"]`` (the raw nested
    value, not a pre-serialised string) and JSON-encode it. This mirrors how
    Invoiced returns nested objects alongside their scalar siblings.
    """
    row: list[str] = []
    for col in headers:
        if col.endswith(_JSON_COLUMN_SUFFIX):
            raw_key = col[: -len(_JSON_COLUMN_SUFFIX)]
            value = record.get(raw_key)
            if value is None:
                row.append("")
            else:
                row.append(json.dumps(value, sort_keys=True, separators=(",", ":")))
            continue
        row.append(_as_cell(record.get(col)))
    return row


def append_records(
    ws: gspread.Worksheet,
    records: Iterable[dict],
    headers: Sequence[str],
) -> int:
    rows = [record_to_row(r, headers) for r in records]
    if not rows:
        return 0
    ws.append_rows(rows, value_input_option="RAW", insert_data_option="INSERT_ROWS")
    return len(rows)


def rewrite_row(
    ws: gspread.Worksheet,
    row_number: int,
    record: dict,
    headers: Sequence[str],
) -> None:
    """Overwrite a single row (1-based) with the serialised record."""
    values = [record_to_row(record, headers)]
    last_col_letter = _col_letter(len(headers))
    ws.update(f"A{row_number}:{last_col_letter}{row_number}", values, value_input_option="RAW")


def _col_letter(n: int) -> str:
    """1→A, 26→Z, 27→AA, ..."""
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


__all__ = [
    "load_credentials",
    "open_or_create_worksheet",
    "append_records",
    "rewrite_row",
    "record_to_row",
]
