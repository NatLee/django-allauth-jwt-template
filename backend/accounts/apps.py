from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self) -> None:
        from accounts import checks  # noqa: F401  (registers the system checks)
