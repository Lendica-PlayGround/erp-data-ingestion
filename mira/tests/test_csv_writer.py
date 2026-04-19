import json
from pathlib import Path

from framework.csv_writer import build_artifact_manifest, write_csv_with_meta


def test_write_csv_with_meta_returns_manifest_fragment_with_storage_key(tmp_path: Path) -> None:
    csv_path = tmp_path / "mapped" / "customers.csv"

    manifest = write_csv_with_meta(
        [{"external_id": "cus_123", "name": "Acme"}],
        ["external_id", "name"],
        csv_path,
        mapping_version="v1",
        source_run_id="run-123",
        storage_key="company_id=acme/run_id=run-123/batch_id=batch-1/mapped/customers.csv",
    )

    assert manifest["storage_key"] == "company_id=acme/run_id=run-123/batch_id=batch-1/mapped/customers.csv"
    assert manifest["meta_path"] == str(csv_path.with_suffix(".meta.json"))
    assert manifest["csv_path"] == str(csv_path)


def test_build_artifact_manifest_collects_expected_batch_artifacts(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw" / "source.csv"
    mapped_path = tmp_path / "mapped" / "customers.csv"
    validation_path = tmp_path / "validation" / "report.json"

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("id,name\n1,Acme\n", encoding="utf-8")
    validation_path.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    mapped_meta = write_csv_with_meta(
        [{"external_id": "cus_123", "name": "Acme"}],
        ["external_id", "name"],
        mapped_path,
        mapping_version="v1",
        source_run_id="run-123",
        storage_key="company_id=acme/run_id=run-123/batch_id=batch-1/mapped/customers.csv",
    )

    manifest = build_artifact_manifest(
        company_id="acme",
        run_id="run-123",
        load_batch_id="batch-1",
        artifacts={
            "raw": raw_path,
            "mapped": mapped_path,
            "validation": validation_path,
        },
        mapped_meta=mapped_meta,
    )

    assert manifest["artifact_prefix"] == "company_id=acme/run_id=run-123/batch_id=batch-1"
    assert manifest["artifacts"]["raw"]["storage_key"].endswith("/raw/source.csv")
    assert manifest["artifacts"]["mapped"]["meta_sha256"] == mapped_meta["meta_sha256"]
    assert manifest["artifacts"]["validation"]["sha256"]
