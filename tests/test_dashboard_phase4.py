from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

from agent.models.onboarding import OnboardingState, SourceProfile
from agent.runtime.dashboard_app import _build_app
from agent.runtime.phase4_service import Phase4DashboardService
from agent.stores.memory import InMemoryStateStore


class FakeClickHouseAdapter:
    def list_events(self, *, run_id: str, limit: int = 25):  # type: ignore[no-untyped-def]
        _ = (run_id, limit)
        return []


def fake_runner_factory(**kwargs):  # type: ignore[no-untyped-def]
    _ = kwargs
    return object()


class FakePhase4Service:
    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []
        self.run_demo_calls: list[str] = []
        self.events = [{"event_name": "phase4.transform.completed", "attributes": {"table": "invoice"}}]
        self.state = {"status": "idle", "tables": []}
        self.raise_on_start = False

    def get_state(self, *, run_id):  # type: ignore[no-untyped-def]
        _ = run_id
        return self.state

    def list_events(self, *, run_id, limit: int = 25):  # type: ignore[no-untyped-def]
        _ = (run_id, limit)
        return self.events

    def start_demo(self, *, run_id, company_id: str):  # type: ignore[no-untyped-def]
        if self.raise_on_start:
            raise ValueError("Phase 4 demo already running")
        self.started.append((str(run_id), company_id))
        self.state = {
            "status": "running",
            "demo_dataset": "acme-co-fixed-demo",
            "tables": [],
        }
        return self.state

    def run_demo(self, *, run_id):  # type: ignore[no-untyped-def]
        self.run_demo_calls.append(str(run_id))


def _make_token(run_id: str) -> str:
    return jwt.encode(
        {"company_id": "acme-co", "run_id": run_id},
        "test-secret",
        algorithm="HS256",
    )


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


def test_phase4_dashboard_page_renders_separate_panel(monkeypatch) -> None:
    token = _make_token(str(uuid4()))
    monkeypatch.setenv("MIRA_JWT_SECRET", "test-secret")
    client = TestClient(_build_app())

    response = client.get(f"/dashboard/phase4?token={token}")

    assert response.status_code == 200
    assert "Phase 4 Demo" in response.text
    assert "Start Phase 4 Demo" in response.text
    assert "Onboarding run" not in response.text
    assert "setInterval(loadState, 3000)" in response.text


def test_phase4_dashboard_state_endpoint_returns_phase4_summary(monkeypatch) -> None:
    run_id = str(uuid4())
    token = _make_token(run_id)
    fake_service = FakePhase4Service()
    monkeypatch.setenv("MIRA_JWT_SECRET", "test-secret")
    monkeypatch.setattr("agent.runtime.dashboard_app.service_from_env", lambda: fake_service)
    client = TestClient(_build_app())

    response = client.get(f"/api/phase4/state?token={token}")

    assert response.status_code == 200
    assert response.json()["status"] in {"idle", "running", "succeeded", "failed"}


def test_phase4_dashboard_events_endpoint_returns_clickhouse_rows(monkeypatch) -> None:
    run_id = str(uuid4())
    token = _make_token(run_id)
    fake_service = FakePhase4Service()
    monkeypatch.setenv("MIRA_JWT_SECRET", "test-secret")
    monkeypatch.setattr("agent.runtime.dashboard_app.service_from_env", lambda: fake_service)
    client = TestClient(_build_app())

    response = client.get(f"/api/phase4/events?token={token}")

    assert response.status_code == 200
    assert response.json()[0]["event_name"] == "phase4.transform.completed"


def test_phase4_dashboard_start_endpoint_runs_demo(monkeypatch) -> None:
    run_id = str(uuid4())
    token = _make_token(run_id)
    fake_service = FakePhase4Service()
    monkeypatch.setenv("MIRA_JWT_SECRET", "test-secret")
    monkeypatch.setattr("agent.runtime.dashboard_app.service_from_env", lambda: fake_service)
    client = TestClient(_build_app())

    response = client.post(f"/api/phase4/start?token={token}")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert fake_service.started[0][1] == "acme-co"
    assert fake_service.run_demo_calls == [run_id]


def test_phase4_dashboard_start_endpoint_rejects_duplicate_run(monkeypatch) -> None:
    run_id = str(uuid4())
    token = _make_token(run_id)
    fake_service = FakePhase4Service()
    fake_service.raise_on_start = True
    monkeypatch.setenv("MIRA_JWT_SECRET", "test-secret")
    monkeypatch.setattr("agent.runtime.dashboard_app.service_from_env", lambda: fake_service)
    client = TestClient(_build_app())

    response = client.post(f"/api/phase4/start?token={token}")

    assert response.status_code == 409
    assert "already running" in response.json()["detail"]
