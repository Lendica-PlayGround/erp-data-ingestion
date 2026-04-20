from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from agent.models.onboarding import OnboardingState, SourceProfile
from erp_data_ingestion.demo_dataset import load_fixed_phase4_demo
from erp_data_ingestion.demo_runner import Phase4DemoRunner


class FakePublisher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def publish(self, lake_result):  # type: ignore[no-untyped-def]
        self.calls.append(lake_result.table)
        return type(
            "PublishedRun",
            (),
            {
                "parquet_uri": f"s3://phase4-lake/{lake_result.table}.parquet",
                "manifest_uri": f"s3://phase4-lake/{lake_result.table}.manifest.json",
                "run_metadata": lake_result.run_metadata,
            },
        )()


def test_demo_runner_reports_success_for_all_tables(tmp_path: Path) -> None:
    events: list[dict[str, object]] = []
    dataset = load_fixed_phase4_demo()
    runner = Phase4DemoRunner(
        output_root=tmp_path / "lake",
        publisher=FakePublisher(),
        on_progress=events.append,
    )

    result = runner.run(dataset=dataset, run_id="run-123")

    assert result.status == "succeeded"
    assert [table["table"] for table in result.tables] == [
        "invoice",
        "customer",
        "contact",
    ]
    assert events[0]["status"] == "running"
    assert events[-1]["status"] == "succeeded"


def test_demo_runner_reports_failure_and_stops_on_first_error(tmp_path: Path) -> None:
    events: list[dict[str, object]] = []
    dataset = load_fixed_phase4_demo()
    broken_dataset = replace(
        dataset,
        tables=[
            replace(dataset.tables[0], source_csv=dataset.root / "missing.csv"),
            *dataset.tables[1:],
        ],
    )
    runner = Phase4DemoRunner(
        output_root=tmp_path / "lake",
        publisher=FakePublisher(),
        on_progress=events.append,
    )

    result = runner.run(dataset=broken_dataset, run_id="run-999")

    assert result.status == "failed"
    assert "missing.csv" in result.last_error
    assert events[-1]["status"] == "failed"


def test_onboarding_state_supports_phase4_control_plane_dict() -> None:
    state = OnboardingState(
        run_id=uuid4(),
        company_id="acme-co",
        source=SourceProfile(system="stripe"),
        phase4={"status": "idle", "tables": []},
    )

    assert state.phase4["status"] == "idle"
