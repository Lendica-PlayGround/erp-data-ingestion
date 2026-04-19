import json
from pathlib import Path

import pytest

from supabase.load_mid_from_mapper import (
    _final_batch_status,
    _publish_events_if_configured,
    _read_rows_with_failures,
    _persist_artifacts_and_build_metadata,
    _require_run_id,
    _write_validation_report,
)


def test_write_validation_report_summarizes_batch_outcome(tmp_path: Path) -> None:
    report_path = tmp_path / "validation" / "report.json"

    report = _write_validation_report(
        report_path,
        table="customers",
        valid_rows=[{"external_id": "cus_123"}],
        failures=[(2, {"external_id": "bad"}, "missing _company_id")],
    )

    assert report["status"] == "failed"
    assert report["table"] == "customers"
    assert report["valid_row_count"] == 1
    assert report["failure_count"] == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))["failures"][0]["row_number"] == 2


def test_persist_artifacts_and_build_metadata_uploads_batch_files(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "raw.csv"
    mapped_path = tmp_path / "customers_mapped.csv"
    validation_path = tmp_path / "validation.json"
    source_path.write_text("id,name\n1,Acme\n", encoding="utf-8")
    mapped_path.write_text("external_id,name\ncus_123,Acme\n", encoding="utf-8")
    validation_path.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    monkeypatch.setenv("SUPABASE_STORAGE_S3_BUCKET", "mira")

    class FakeS3Client:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str]] = []
            self.objects: list[tuple[str, str, dict]] = []

        def upload_file(self, filename: str, bucket: str, key: str) -> None:
            self.uploads.append((filename, bucket, key))

        def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
            self.objects.append((Bucket, Key, json.loads(Body.decode("utf-8"))))

    fake_s3 = FakeS3Client()

    metadata = _persist_artifacts_and_build_metadata(
        company_id="acme",
        table_name="customers",
        load_batch_id=11,
        run_id="run-123",
        source_input=source_path,
        mapped_csv=mapped_path,
        validation_report_path=validation_path,
        status="completed",
        sync_type="delta",
        inserted_count=1,
        updated_count=0,
        failed_count=0,
        s3_client=fake_s3,
    )

    uploaded_keys = {key for _, _, key in fake_s3.uploads}
    assert "company_id=acme/run_id=run-123/batch_id=11/raw/raw.csv" in uploaded_keys
    assert "company_id=acme/run_id=run-123/batch_id=11/mapped/customers_mapped.csv" in uploaded_keys
    assert "company_id=acme/run_id=run-123/batch_id=11/validation/validation.json" in uploaded_keys
    assert fake_s3.objects[0][1] == "company_id=acme/run_id=run-123/batch_id=11/manifests/customers_manifest.json"
    assert metadata["artifact_manifest"]["artifact_prefix"] == "company_id=acme/run_id=run-123/batch_id=11"
    assert metadata["run_events"][0]["event_type"] == "load_batch_completed"
    assert metadata["run_events"][0]["load_batch_id"] == "11"
    assert metadata["artifact_manifest"]["storage_key"].endswith("/manifests/customers_manifest.json")


def test_final_batch_status_fails_when_any_validation_failure_exists() -> None:
    assert _final_batch_status(valid_row_count=2, failure_count=1) == "failed"
    assert _final_batch_status(valid_row_count=2, failure_count=0) == "completed"
    assert _final_batch_status(valid_row_count=0, failure_count=1) == "failed"


def test_require_run_id_raises_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("MIRA_RUN_ID", raising=False)

    with pytest.raises(SystemExit, match="MIRA_RUN_ID"):
        _require_run_id()


def test_read_rows_with_failures_rejects_missing_required_field(tmp_path: Path) -> None:
    csv_path = tmp_path / "contacts.csv"
    csv_path.write_text(
        "external_id,first_name,last_name,account_external_id,addresses,email_addresses,phone_numbers,last_activity_at,remote_created_at,remote_was_deleted,_unmapped,_source_system,_source_record_id,_company_id,_ingested_at,_source_file,_mapping_version,_row_hash\n"
        ",Jane,Doe,cus_123,[],[],[],2026-04-19T12:00:00Z,2026-04-19T11:00:00Z,false,{},invoiced,con_123,acme,2026-04-19T12:30:00Z,contacts.csv,v1,hash\n",
        encoding="utf-8",
    )

    rows, failures = _read_rows_with_failures("contacts", csv_path)

    assert rows == []
    assert failures
    assert "external_id" in failures[0][2]


def test_publish_events_if_configured_is_best_effort(monkeypatch) -> None:
    monkeypatch.setenv("CLICKHOUSE_HOST", "https://example.clickhouse.cloud")
    monkeypatch.setenv("CLICKHOUSE_DATABASE", "phase4")
    monkeypatch.setenv("CLICKHOUSE_USERNAME", "default")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "secret")

    def boom(*args, **kwargs):
        raise RuntimeError("clickhouse down")

    monkeypatch.setattr("supabase.load_mid_from_mapper.publish_run_events", boom)

    _publish_events_if_configured([{"event_type": "load_batch_completed"}])
