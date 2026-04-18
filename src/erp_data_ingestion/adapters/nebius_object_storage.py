from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class NebiusObjectStorageAdapter:
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
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for the default Nebius object storage client"
            ) from exc

        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )
