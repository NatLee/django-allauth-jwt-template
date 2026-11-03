from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "api"

    def ready(self) -> None:
        from api import schema  # noqa: F401  (teaches the API docs about allauth's JWT auth)
