from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict


class SupabaseObjectStorageAdapter:
    def __init__(
        self,
        bucket: str,
        client: Any | None = None,
        *,
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.client = client or self._build_default_client(
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )

    def upload_run_artifacts(self, output_path: Path, manifest_path: Path) -> Dict[str, str]:
        parquet_key = self._build_object_key(output_path)
        manifest_key = self._build_object_key(manifest_path)

        self.client.upload_file(str(output_path), self.bucket, parquet_key)
        self.client.upload_file(str(manifest_path), self.bucket, manifest_key)

        return {
            "parquet_uri": f"s3://{self.bucket}/{parquet_key}",
            "manifest_uri": f"s3://{self.bucket}/{manifest_key}",
        }

    @classmethod
    def from_env(cls, client: Any | None = None) -> "SupabaseObjectStorageAdapter":
        bucket = os.getenv("SUPABASE_STORAGE_S3_BUCKET")
        if not bucket:
            raise ValueError("SUPABASE_STORAGE_S3_BUCKET is required")
        return cls(
            bucket=bucket,
            client=client,
            endpoint_url=os.getenv("SUPABASE_STORAGE_S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("SUPABASE_STORAGE_S3_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY"),
            region_name=os.getenv("SUPABASE_STORAGE_S3_REGION"),
        )

    def _build_object_key(self, path: Path) -> str:
        parts = list(path.parts)
        for index, part in enumerate(parts):
            if part.startswith("company_id="):
                return "/".join(parts[index:])
        return path.name

    def _build_default_client(
        self,
        *,
        endpoint_url: str | None,
        aws_access_key_id: str | None,
        aws_secret_access_key: str | None,
        region_name: str | None,
    ) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for the default Supabase object storage client"
            ) from exc

        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
            config=Config(s3={"addressing_style": "path"}),
        )
