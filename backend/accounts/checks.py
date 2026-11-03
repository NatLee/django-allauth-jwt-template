from django.conf import settings
from django.core.checks import Error, register


@register()
def dummy_provider_only_in_debug(app_configs, **kwargs) -> list[Error]:
    """The dummy provider lets anyone sign in as anyone; keep it off live sites."""
    if settings.DUMMY_PROVIDER_APP in settings.INSTALLED_APPS and not settings.DEBUG:
        return [
            Error(
                "The dummy login provider is on while DEBUG is off.",
                hint="Unset ENABLE_DUMMY_PROVIDER (it is only for trying things out locally).",
                id="accounts.E001",
            )
        ]
    return []
