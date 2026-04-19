from datetime import date
from pathlib import Path

from erp_data_ingestion.publish import Phase4Publisher
from erp_data_ingestion.phase4 import Phase4Transformer


class FakeObjectStorageAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path]] = []

    def upload_run_artifacts(self, output_path: Path, manifest_path: Path) -> dict[str, str]:
        self.calls.append((output_path, manifest_path))
        return {
            "parquet_uri": "s3://phase4-lake/company_id=company_123/table=invoice/run_id=run-1/invoice.parquet",
            "manifest_uri": "s3://phase4-lake/company_id=company_123/table=invoice/run_id=run-1/manifest.json",
        }


class FakeClickHouseSink:
    def __init__(self) -> None:
        self.calls: list[tuple[object, list[object]]] = []

    def write_run(self, *, run_metadata: object, telemetry_events: list[object]) -> None:
        self.calls.append((run_metadata, telemetry_events))


def test_phase4_publisher_uploads_artifacts_and_writes_clickhouse_records(tmp_path: Path) -> None:
    input_csv = tmp_path / "company_123_invoice_initial_20260418_run-1.csv"
    input_csv.write_text(
        "\n".join(
            [
                "id,remote_id,number,contact,company,issue_date,due_date,currency,sub_total,total_tax_amount,total_amount,balance,status",
                "inv_internal_1,src_inv_1,INV-001,contact_123,company_123,2026-04-18T00:00:00+00:00,2026-04-30T00:00:00+00:00,USD,100.0,5.0,105.0,25.0,OPEN",
            ]
        ),
        encoding="utf-8",
    )
    transformer = Phase4Transformer(schema_version="invoice.v1")
    lake_result = transformer.transform_midlayer_csv(
        input_csv=input_csv,
        output_root=tmp_path / "lake",
        table="invoice",
        company_id="company_123",
        sync_type="initial",
        run_id="run-1",
        logical_date=date(2026, 4, 18),
    )

    storage = FakeObjectStorageAdapter()
    sink = FakeClickHouseSink()
    publisher = Phase4Publisher(object_storage=storage, clickhouse_sink=sink)

    published = publisher.publish(lake_result)

    assert storage.calls == [(lake_result.output_path, lake_result.manifest_path)]
    assert sink.calls[0][0].output_path == "s3://phase4-lake/company_id=company_123/table=invoice/run_id=run-1/invoice.parquet"
    assert published.parquet_uri.endswith("/invoice.parquet")
    assert published.manifest_uri.endswith("/manifest.json")
    assert published.run_metadata.output_path == published.parquet_uri
