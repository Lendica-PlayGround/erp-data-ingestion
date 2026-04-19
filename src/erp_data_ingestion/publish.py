from __future__ import annotations

from dataclasses import dataclass, replace

from erp_data_ingestion.adapters.clickhouse import ClickHouseTelemetrySink
from erp_data_ingestion.adapters.supabase_object_storage import SupabaseObjectStorageAdapter
from erp_data_ingestion.phase4 import LakeWriteResult


@dataclass
class PublishedRunResult:
    parquet_uri: str
    manifest_uri: str
    run_metadata: object


class Phase4Publisher:
    def __init__(self, *, object_storage: object, clickhouse_sink: object) -> None:
        self.object_storage = object_storage
        self.clickhouse_sink = clickhouse_sink

    def publish(self, lake_result: LakeWriteResult) -> PublishedRunResult:
        uploaded = self.object_storage.upload_run_artifacts(
            output_path=lake_result.output_path,
            manifest_path=lake_result.manifest_path,
        )
        published_run_metadata = replace(
            lake_result.run_metadata,
            output_path=uploaded["parquet_uri"],
        )
        self.clickhouse_sink.write_run(
            run_metadata=published_run_metadata,
            telemetry_events=lake_result.telemetry_events,
        )
        return PublishedRunResult(
            parquet_uri=uploaded["parquet_uri"],
            manifest_uri=uploaded["manifest_uri"],
            run_metadata=published_run_metadata,
        )

    @classmethod
    def from_env(cls) -> "Phase4Publisher":
        return cls(
            object_storage=SupabaseObjectStorageAdapter.from_env(),
            clickhouse_sink=ClickHouseTelemetrySink.from_env(),
        )
