import json

from framework.observability import build_run_event, publish_run_events


def test_build_run_event_includes_phase4_identifiers_and_payload() -> None:
    event = build_run_event(
        "validation_completed",
        company_id="acme",
        run_id="run-123",
        load_batch_id="batch-1",
        table_name="customers",
        severity="info",
        payload={"row_count": 4, "failed_count": 1},
    )

    assert event["event_type"] == "validation_completed"
    assert event["company_id"] == "acme"
    assert event["run_id"] == "run-123"
    assert event["load_batch_id"] == "batch-1"
    assert event["table_name"] == "customers"
    assert event["severity"] == "info"
    assert event["payload_json"] == {"row_count": 4, "failed_count": 1}
    assert event["event_time"].endswith("+00:00")


def test_publish_run_events_posts_json_each_row_payload() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        def post(self, url, *, content, auth, headers, timeout):
            self.calls.append(
                {
                    "url": url,
                    "content": content,
                    "auth": auth,
                    "headers": headers,
                    "timeout": timeout,
                }
            )

            class Response:
                def raise_for_status(self):
                    return None

            return Response()

    client = FakeClient()
    events = [
        build_run_event(
            "load_batch_completed",
            company_id="acme",
            run_id="run-123",
            load_batch_id="11",
            table_name="contacts",
            severity="info",
            payload={"status": "completed"},
        )
    ]

    publish_run_events(
        events,
        host="https://example.clickhouse.cloud",
        database="phase4",
        username="default",
        password="secret",
        client=client,
    )

    assert client.calls[0]["url"] == "https://example.clickhouse.cloud/?database=phase4"
    assert "CREATE TABLE IF NOT EXISTS run_events" in client.calls[0]["content"]
    assert client.calls[1]["url"] == "https://example.clickhouse.cloud/?database=phase4&query=INSERT%20INTO%20run_events%20FORMAT%20JSONEachRow"
    assert client.calls[1]["auth"] == ("default", "secret")
    sent_line = client.calls[1]["content"].strip()
    assert json.loads(sent_line)["event_type"] == "load_batch_completed"
    assert json.loads(sent_line)["payload_json"] == "{\"status\":\"completed\"}"
