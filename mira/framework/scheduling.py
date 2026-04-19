"""Airflow DAG factory helpers (PRD §5.3)."""

from __future__ import annotations

from pathlib import Path


def write_stub_dag(path: Path, dag_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from airflow import DAG\n"
        "from datetime import datetime\n"
        f"DAG(dag_id={dag_id!r}, start_date=datetime(2026, 1, 1), schedule_interval='@daily')\n",
        encoding="utf-8",
    )
