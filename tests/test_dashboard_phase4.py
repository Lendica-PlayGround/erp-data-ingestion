from uuid import uuid4

from agent.models.onboarding import OnboardingState, SourceProfile
from agent.stores.memory import InMemoryStateStore
from agent.runtime.phase4_service import Phase4DashboardService


class FakeClickHouseAdapter:
    def list_events(self, *, run_id: str, limit: int = 25):  # type: ignore[no-untyped-def]
        _ = (run_id, limit)
        return []


def fake_runner_factory(**kwargs):  # type: ignore[no-untyped-def]
    _ = kwargs
    return object()


def test_phase4_service_initializes_running_state() -> None:
    state = OnboardingState(
        run_id=uuid4(),
        company_id="acme-co",
        source=SourceProfile(system="stripe"),
    )
    store = InMemoryStateStore()
    store.put(state)
    service = Phase4DashboardService(
        store=store,
        clickhouse=FakeClickHouseAdapter(),  # type: ignore[arg-type]
        runner_factory=fake_runner_factory,
    )

    updated = service.start_demo(run_id=state.run_id, company_id="acme-co")

    assert updated["status"] == "running"
    assert updated["demo_dataset"] == "acme-co-fixed-demo"
