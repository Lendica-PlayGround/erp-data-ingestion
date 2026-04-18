import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ArConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.django_api.ar"
    label = "ar"
