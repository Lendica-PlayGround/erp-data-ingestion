from __future__ import annotations

import os
from pathlib import Path


def _load_repo_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _connection_kwargs() -> dict[str, str]:
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "sslmode": os.environ.get("POSTGRES_SSLMODE", "require"),
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _load_repo_dotenv(repo_root / ".env")

    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - operational guard
        raise SystemExit(
            "psycopg is required to apply Supabase migrations. "
            "Install it with `python3 -m pip install \"psycopg[binary]\"`."
        ) from exc

    migrations_dir = Path(__file__).resolve().parent / "migrations"
    migration_paths = sorted(migrations_dir.glob("*.sql"))
    if not migration_paths:
        raise SystemExit("No SQL migrations found.")

    with psycopg.connect(**_connection_kwargs()) as conn:
        with conn.cursor() as cur:
            for path in migration_paths:
                print(f"Applying {path.name}...")
                cur.execute(path.read_text())
        conn.commit()

    print(f"Applied {len(migration_paths)} migration(s).")


if __name__ == "__main__":
    main()
