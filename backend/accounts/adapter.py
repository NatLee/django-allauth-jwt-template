"""
The two sign-up rules allauth has no setting for. Everything else (social
login, connecting accounts, tokens, error codes) is plain allauth.

1. Only email addresses on ``settings.ALLOWED_EMAIL_DOMAINS`` may sign up or
   connect a third-party account (no list means every domain is fine).
2. A third-party login whose email already belongs to someone is refused,
   instead of creating a second account: the person signs in to the existing
   account first and connects the provider from there.

Both rules raise a ``ValidationError`` with a code. allauth turns that into
``?error=<code>`` on the frontend's callback URL for redirect logins, and
into a 400 response for the JSON endpoints.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.account.utils import user_email
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin
from allauth.socialaccount.providers.base import AuthProcess

EMAIL_DOMAIN_NOT_ALLOWED = "email_domain_not_allowed"
EMAIL_DOMAIN_NOT_ALLOWED_MESSAGE = _("Sign-up is limited to email addresses on approved domains.")


def email_domain_allowed(email: str | None) -> bool:
    allowed = settings.ALLOWED_EMAIL_DOMAINS
    if not allowed:
        return True
    # Without an address there is no domain to approve.
    domain = (email or "").rpartition("@")[2].lower()
    return domain in allowed


def email_in_use(email: str) -> bool:
    """Whether any user already has this address (verified or not)."""
    if EmailAddress.objects.filter(email__iexact=email).exists():
        return True
    user_model = get_user_model()
    email_field = user_model.get_email_field_name()
    return user_model._default_manager.filter(**{f"{email_field}__iexact": email}).exists()


class AccountAdapter(DefaultAccountAdapter):
    error_messages = {
        **DefaultAccountAdapter.error_messages,
        EMAIL_DOMAIN_NOT_ALLOWED: EMAIL_DOMAIN_NOT_ALLOWED_MESSAGE,
    }

    def clean_email(self, email: str) -> str:
        """Every place a person types an address: signup, adding an email,
        and the "pick an email" step of a third-party signup."""
        email = super().clean_email(email)
        if not email_domain_allowed(email):
            raise self.validation_error(EMAIL_DOMAIN_NOT_ALLOWED)
        return email

    def add_message(self, *args, **kwargs) -> None:
        """Don't queue allauth's "Successfully signed in" style messages.

        With HEADLESS_ONLY there is no allauth page that would show them, so
        they would sit in the session and pop up in the Django admin later.
        """


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    error_messages = {
        **DefaultSocialAccountAdapter.error_messages,
        EMAIL_DOMAIN_NOT_ALLOWED: EMAIL_DOMAIN_NOT_ALLOWED_MESSAGE,
    }

    def pre_social_login(self, request: HttpRequest, sociallogin: SocialLogin) -> None:
        if sociallogin.is_existing:
            # A returning account; connecting one that belongs to someone
            # else is refused by allauth itself ("connected_other").
            return
        email = self._email_of(sociallogin)
        if not email_domain_allowed(email):
            raise self.validation_error(EMAIL_DOMAIN_NOT_ALLOWED)
        connecting = sociallogin.state.get("process") == AuthProcess.CONNECT
        if not connecting and email and email_in_use(email):
            raise self.validation_error("email_taken", sociallogin.provider.name)

    @staticmethod
    def _email_of(sociallogin: SocialLogin) -> str:
        if sociallogin.user is not None and (email := user_email(sociallogin.user)):
            return email
        if sociallogin.email_addresses:
            return sociallogin.email_addresses[0].email
        return ""

