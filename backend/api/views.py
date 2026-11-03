"""
Your own API. Put your endpoints here; with the defaults in settings they
accept ``Authorization: Bearer <access token>`` from allauth.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.module_loading import import_string
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from allauth.headless.contrib.rest_framework.authentication import JWTTokenAuthentication


class MeView(APIView):
    """The example protected endpoint: who is calling, and with what."""

    @extend_schema(
        responses=inline_serializer(
            "Me",
            {
                "id": serializers.IntegerField(),
                "email": serializers.EmailField(),
                "username": serializers.CharField(),
                "authenticated_with": serializers.ChoiceField(choices=["jwt", "session"]),
                "token_expires_at": serializers.IntegerField(allow_null=True),
            },
        )
    )
    def get(self, request: Request) -> Response:
        user = request.user
        with_jwt = isinstance(request.successful_authenticator, JWTTokenAuthentication)
        return Response(
            {
                "id": user.pk,
                "email": user.email,
                "username": user.get_username(),
                "authenticated_with": "jwt" if with_jwt else "session",
                # The access token's claims are in request.auth.
                "token_expires_at": request.auth["exp"] if with_jwt else None,
            }
        )


class NoAccessTokens(APIException):
    status_code = 501
    default_code = "no_access_tokens"
    default_detail = "HEADLESS_TOKEN_STRATEGY does not hand out access tokens."


class SessionTokenView(APIView):
    """Give the signed-in browser session the same JWT pair an app gets.

    allauth puts tokens only in the responses of its *app* endpoints
    (``/_allauth/app/v1/...``), while third-party redirect logins only run
    through its *browser* endpoints. After a browser login, a page POSTs here
    (with its CSRF token) to get the pair from allauth's own token strategy.

    The tokens belong to this session: ``POST /_allauth/app/v1/tokens/refresh``
    renews them, and logging out (``DELETE .../auth/session``) ends them.
    """

    authentication_classes = [SessionAuthentication]

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "TokenPair",
            {"access_token": serializers.CharField(), "refresh_token": serializers.CharField()},
        ),
    )
    def post(self, request: Request) -> Response:
        strategy = import_string(settings.HEADLESS_TOKEN_STRATEGY)()
        tokens = strategy.create_access_token_payload(request)
        if not tokens:
            raise NoAccessTokens()
        return Response(tokens)
