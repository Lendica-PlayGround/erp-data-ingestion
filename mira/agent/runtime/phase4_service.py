from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from agent.stores.base import StateStore
from agent.stores.supabase_store import store_from_env
from erp_data_ingestion.adapters.clickhouse import ClickHouseTelemetrySink
from erp_data_ingestion.demo_dataset import load_fixed_phase4_demo
from erp_data_ingestion.demo_runner import Phase4DemoRunner
from erp_data_ingestion.publish import Phase4Publisher


class Phase4DashboardService:
    def __init__(
        self,
        *,
        store: StateStore,
        clickhouse: ClickHouseTelemetrySink,
        runner_factory: Callable[..., Phase4DemoRunner] | None = None,
    ) -> None:
        self.store = store
        self.clickhouse = clickhouse
        self.runner_factory = runner_factory or self._default_runner

    def get_state(self, *, run_id: UUID) -> dict[str, Any]:
        state = self.store.get(run_id)
        if state is None:
            raise KeyError(f"Unknown run_id {run_id}")
        return state.phase4 or {"status": "idle", "tables": []}

    def start_demo(self, *, run_id: UUID, company_id: str) -> dict[str, Any]:
        state = self.store.get(run_id)
        if state is None:
            raise KeyError(f"Unknown run_id {run_id}")
        if state.company_id != company_id:
            raise ValueError(
                f"run_id {run_id} does not belong to company_id {company_id!r}"
            )

        current = state.phase4 or {"status": "idle", "tables": []}
        if current.get("status") == "running":
            raise ValueError("Phase 4 demo already running")

        phase4 = {
            "status": "running",
            "demo_dataset": "acme-co-fixed-demo",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "last_error": None,
            "tables": [],
        }
        self.store.patch(run_id, {"phase4": phase4}, "phase4_demo_start")
        return phase4

    def record_progress(self, *, run_id: UUID, update: dict[str, Any]) -> None:
        current = self.get_state(run_id=run_id)
        merged = {**current, **update}
        if merged["status"] in {"succeeded", "failed"} and not merged.get("finished_at"):
            merged["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.store.patch(run_id, {"phase4": merged}, "phase4_demo_progress")

    def list_events(self, *, run_id: UUID, limit: int = 25) -> list[dict[str, Any]]:
        return self.clickhouse.list_events(run_id=str(run_id), limit=limit)

    def run_demo(self, *, run_id: UUID) -> None:
        dataset = load_fixed_phase4_demo()
        runner = self.runner_factory(
            output_root=Path(".mira_workspace") / "phase4-demo",
            publisher=Phase4Publisher.from_env(),
            on_progress=lambda update: self.record_progress(run_id=run_id, update=update),
        )
        runner.run(dataset=dataset, run_id=str(run_id))

    def _default_runner(self, **kwargs: Any) -> Phase4DemoRunner:
        return Phase4DemoRunner(**kwargs)


def service_from_env() -> Phase4DashboardService:
    return Phase4DashboardService(
        store=store_from_env(),
        clickhouse=ClickHouseTelemetrySink.from_env(),
    )
