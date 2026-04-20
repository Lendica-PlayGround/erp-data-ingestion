from __future__ import annotations

from erp_data_ingestion.serializers.contact_v1 import ContactV1Serializer


class CustomerV1Serializer(ContactV1Serializer):
    """Customer rows reuse the contact serializer shape for Phase 4 demo."""

    pass
