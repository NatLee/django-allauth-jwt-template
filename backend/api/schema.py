from drf_spectacular.extensions import OpenApiAuthenticationExtension


class AllauthJWTScheme(OpenApiAuthenticationExtension):
    """Shows allauth's JWT authentication as a Bearer token in the API docs."""

    target_class = "allauth.headless.contrib.rest_framework.authentication.JWTTokenAuthentication"
    name = "allauthJWT"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
