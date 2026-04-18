"""Base model with UUID primary key for all AR models."""

import uuid

from django.db import models


class BaseModel(models.Model):
    """Abstract base model for all AR models.

    Provides:
    - UUID primary key for security (non-enumerable IDs) and distributed system compatibility
    - Additional shared fields can be added here as needed (e.g., timestamps)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
