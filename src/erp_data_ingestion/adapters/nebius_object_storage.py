from erp_data_ingestion.adapters.supabase_object_storage import SupabaseObjectStorageAdapter


class NebiusObjectStorageAdapter(SupabaseObjectStorageAdapter):
    """Backward-compatible alias for the renamed Supabase S3 storage adapter."""

