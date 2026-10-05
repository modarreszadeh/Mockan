"""OIDC (D-12): the authorization-code flow for the Panel and JWT validation for API clients."""

from collections.abc import Mapping
from typing import Any

import structlog
from authlib.integrations.starlette_client import OAuth, OAuthError
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet
from joserfc.jws import JWSRegistry
from starlette.requests import Request
from starlette.responses import Response

from mockan.infrastructure.settings import MockanSettings

log = structlog.get_logger()

# Generic OIDC discovery (`MOCKAN_OIDC_ISSUER`); the provider is Keycloak (OQ-04, decided). Known
# Keycloak note: its access tokens carry `aud=account` unless the client has an audience mapper, so
# `verify_bearer` needs one. The Panel login uses the ID token and is not affected.

# Asymmetric algorithms only: a bearer token must never be verifiable with a shared secret, and
# `none` is not in the list.
_ALGORITHMS = [
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
    "EdDSA",
]
_LEEWAY_SECONDS = 60


class TokenError(Exception):
    """The bearer token (or the IdP answer) can't be trusted; the message is safe to show."""


class OidcClient:
    def __init__(self, settings: MockanSettings) -> None:
        self._client_id = settings.oidc_client_id
        discovery = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
        oauth = OAuth()
        self._app: Any = oauth.register(
            name="mockan",
            server_metadata_url=discovery,
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256"},
        )

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Response:
        response: Response = await self._app.authorize_redirect(request, redirect_uri)
        return response

    async def complete_login(self, request: Request) -> Mapping[str, Any]:
        """Exchange the callback's code; returns the ID token's claims (signature, issuer,
        audience, expiry and nonce are verified by Authlib)."""
        try:
            token = await self._app.authorize_access_token(request)
        except OAuthError as error:
            raise TokenError(error.description or error.error) from error
        claims = token.get("userinfo")
        if not claims or not claims.get("sub"):
            raise TokenError("The identity provider returned no subject.")
        return dict(claims)

    async def verify_bearer(self, raw_token: str) -> Mapping[str, Any]:
        """Validate a JWT access token against the provider's JWKS; returns its claims."""
        try:
            metadata = await self._app.load_server_metadata()
            registry = JWSRegistry(algorithms=_ALGORITHMS)
            try:
                token = jwt.decode(
                    raw_token,
                    KeySet.import_key_set(await self._app.fetch_jwk_set()),
                    registry=registry,
                )
            except InvalidKeyIdError:  # the provider rotated its keys: refetch once
                token = jwt.decode(
                    raw_token,
                    KeySet.import_key_set(await self._app.fetch_jwk_set(force=True)),
                    registry=registry,
                )
            jwt.JWTClaimsRegistry(
                leeway=_LEEWAY_SECONDS,
                iss={"essential": True, "value": metadata["issuer"]},
                aud={"essential": True, "value": self._client_id},
                sub={"essential": True},
                exp={"essential": True},
            ).validate(token.claims)
        except JoseError as error:
            raise TokenError("The access token is invalid or expired.") from error
        except Exception as error:  # discovery or JWKS unreachable, malformed metadata...
            log.warning("oidc_token_verification_failed", error=type(error).__name__)
            raise TokenError("The access token couldn't be verified.") from error
        return dict(token.claims)
