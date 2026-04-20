from datetime import datetime, timezone
from pathlib import Path

from erp_data_ingestion.adapters.clickhouse import ClickHouseTelemetrySink
from erp_data_ingestion.adapters.supabase_object_storage import SupabaseObjectStorageAdapter
from erp_data_ingestion.models import RunMetadataRecord, TelemetryEvent


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str]] = []

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.uploads.append((filename, bucket, key))


class FakeClickHouseClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, list[list[object]], list[str]]] = []

    def insert(self, table: str, data: list[list[object]], column_names: list[str]) -> None:
        self.inserts.append((table, data, column_names))


class FakeQueryClient:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, object]]] = []

    def query(self, sql: str, parameters: dict[str, object]):
        self.queries.append((sql, parameters))
        return type(
            "Result",
            (),
            {
                "result_rows": [
                    [
                        "phase4.transform.completed",
                        "2026-04-18T08:00:00+00:00",
                        '{"run_id":"run-1","table":"invoice"}',
                    ]
                ]
            },
        )()
def test_supabase_adapter_uploads_parquet_and_manifest_with_bucket_keys(tmp_path: Path) -> None:
    parquet_path = tmp_path / "company_id=company_123/table=invoice/sync_type=initial/date=2026-04-18/run_id=run-1/invoice.parquet"
    manifest_path = parquet_path.with_name("manifest.json")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.write_bytes(b"parquet-bytes")
    manifest_path.write_text('{"run_id":"run-1"}', encoding="utf-8")

    client = FakeS3Client()
    adapter = SupabaseObjectStorageAdapter(bucket="phase4-lake", client=client)

    uploaded = adapter.upload_run_artifacts(
        output_path=parquet_path,
        manifest_path=manifest_path,
    )

    assert uploaded["parquet_uri"] == "s3://phase4-lake/company_id=company_123/table=invoice/sync_type=initial/date=2026-04-18/run_id=run-1/invoice.parquet"
    assert uploaded["manifest_uri"] == "s3://phase4-lake/company_id=company_123/table=invoice/sync_type=initial/date=2026-04-18/run_id=run-1/manifest.json"
    assert client.uploads[0][1] == "phase4-lake"
    assert client.uploads[1][2].endswith("/manifest.json")


def test_clickhouse_sink_inserts_run_metadata_and_telemetry_events() -> None:
    client = FakeClickHouseClient()
    sink = ClickHouseTelemetrySink(client=client)

    run_metadata = RunMetadataRecord(
        run_id="run-1",
        company_id="company_123",
        table="invoice",
        sync_type="initial",
        schema_version="invoice.v1",
        source_path="supabase://midlayer-csv/company_123_invoice_initial.csv",
        output_path="s3://phase4-lake/company_id=company_123/table=invoice/run_id=run-1/invoice.parquet",
        row_count=1,
        status="success",
        validation_summary={"invalid_rows": 0},
    )
    telemetry_events = [
        TelemetryEvent(
            event_name="phase4.transform.completed",
            attributes={
                "company_id": "company_123",
                "table": "invoice",
                "row_count": 1,
            },
            occurred_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )
    ]

    sink.write_run(run_metadata=run_metadata, telemetry_events=telemetry_events)

    assert client.inserts[0][0] == "phase4_run_metadata"
    assert client.inserts[1][0] == "phase4_telemetry_events"
    assert client.inserts[0][1][0][0] == "run-1"
    assert client.inserts[1][1][0][0] == "phase4.transform.completed"


def test_supabase_adapter_from_env_uses_expected_variables(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_build_default_client(self, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return FakeS3Client()

    monkeypatch.setenv("SUPABASE_STORAGE_S3_BUCKET", "phase4-lake")
    monkeypatch.setenv(
        "SUPABASE_STORAGE_S3_ENDPOINT_URL",
        "https://project-ref.storage.supabase.co/storage/v1/s3",
    )
    monkeypatch.setenv("SUPABASE_STORAGE_S3_ACCESS_KEY_ID", "key-id")
    monkeypatch.setenv("SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("SUPABASE_STORAGE_S3_REGION", "us-east-1")
    monkeypatch.setattr(
        SupabaseObjectStorageAdapter,
        "_build_default_client",
        fake_build_default_client,
    )

    adapter = SupabaseObjectStorageAdapter.from_env()

    assert adapter.bucket == "phase4-lake"
    assert captured["endpoint_url"] == "https://project-ref.storage.supabase.co/storage/v1/s3"
    assert captured["aws_access_key_id"] == "key-id"
    assert captured["aws_secret_access_key"] == "secret"
    assert captured["region_name"] == "us-east-1"


def test_clickhouse_sink_from_env_uses_expected_variables(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_build_default_client(self, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return FakeClickHouseClient()

    monkeypatch.setenv("CLICKHOUSE_HOST", "clickhouse.internal")
    monkeypatch.setenv("CLICKHOUSE_PORT", "8443")
    monkeypatch.setenv("CLICKHOUSE_USERNAME", "analytics")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "secret")
    monkeypatch.setenv("CLICKHOUSE_DATABASE", "phase4")
    monkeypatch.setenv("CLICKHOUSE_SECURE", "true")
    monkeypatch.setattr(
        ClickHouseTelemetrySink,
        "_build_default_client",
        fake_build_default_client,
    )

    sink = ClickHouseTelemetrySink.from_env()

    assert sink.client is not None
    assert captured["host"] == "clickhouse.internal"
    assert captured["port"] == 8443
    assert captured["username"] == "analytics"
    assert captured["password"] == "secret"
    assert captured["database"] == "phase4"
    assert captured["secure"] is True


def test_clickhouse_sink_from_env_normalizes_full_url_host(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_build_default_client(self, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return FakeClickHouseClient()

    monkeypatch.setenv("CLICKHOUSE_HOST", "https://clickhouse.example")
    monkeypatch.setenv("CLICKHOUSE_PORT", "8443")
    monkeypatch.setenv("CLICKHOUSE_USERNAME", "analytics")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "secret")
    monkeypatch.setenv("CLICKHOUSE_DATABASE", "phase4")
    monkeypatch.setenv("CLICKHOUSE_SECURE", "true")
    monkeypatch.setattr(
        ClickHouseTelemetrySink,
        "_build_default_client",
        fake_build_default_client,
    )

    sink = ClickHouseTelemetrySink.from_env()

    assert sink.client is not None
    assert captured["host"] == "clickhouse.example"
    assert captured["port"] == 8443
    assert captured["secure"] is True


def test_clickhouse_sink_lists_recent_events_for_run() -> None:
    sink = ClickHouseTelemetrySink(client=FakeQueryClient())

    rows = sink.list_events(run_id="run-1", limit=10)

    assert rows[0]["event_name"] == "phase4.transform.completed"
    assert rows[0]["attributes"]["table"] == "invoice"
