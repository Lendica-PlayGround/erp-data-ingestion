from datetime import datetime, timezone
from pathlib import Path

from erp_data_ingestion.adapters.clickhouse import ClickHouseTelemetrySink
from erp_data_ingestion.adapters.nebius_object_storage import NebiusObjectStorageAdapter
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


def test_nebius_adapter_uploads_parquet_and_manifest_with_bucket_keys(tmp_path: Path) -> None:
    parquet_path = tmp_path / "company_id=company_123/table=invoice/sync_type=initial/date=2026-04-18/run_id=run-1/invoice.parquet"
    manifest_path = parquet_path.with_name("manifest.json")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.write_bytes(b"parquet-bytes")
    manifest_path.write_text('{"run_id":"run-1"}', encoding="utf-8")

    client = FakeS3Client()
    adapter = NebiusObjectStorageAdapter(bucket="phase4-lake", client=client)

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
