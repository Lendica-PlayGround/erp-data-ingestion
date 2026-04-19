from pathlib import Path


def _read_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in Path(path).read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_env_example_includes_phase4_clickhouse_and_storage_settings() -> None:
    env_values = _read_env(".env.example")

    expected_values = {
        "CLICKHOUSE_HOST": "",
        "CLICKHOUSE_PORT": "8443",
        "CLICKHOUSE_USERNAME": "default",
        "CLICKHOUSE_PASSWORD": "",
        "CLICKHOUSE_DATABASE": "phase4",
        "CLICKHOUSE_SECURE": "true",
        "SUPABASE_STORAGE_S3_BUCKET": "mira",
        "SUPABASE_STORAGE_S3_ENDPOINT_URL": "",
        "SUPABASE_STORAGE_S3_ACCESS_KEY_ID": "",
        "SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY": "",
        "SUPABASE_STORAGE_S3_REGION": "us-east-1",
    }

    assert {
        key: env_values.get(key) for key in expected_values
    } == expected_values
