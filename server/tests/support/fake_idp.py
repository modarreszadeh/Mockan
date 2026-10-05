"""A minimal OIDC provider on a real socket: discovery, JWKS, authorize, token (no mocking)."""

import time
from base64 import b64decode
from typing import Any
from urllib.parse import parse_qs, urlencode

from joserfc import jwt
from joserfc.jwk import RSAKey
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from tests.support.live_server import LiveServer

CLIENT_ID = "mockan-test"
CLIENT_SECRET = "s3cret"


def _client_secret(request: Request, form: dict[str, list[str]]) -> str | None:
    """The secret from HTTP Basic (Authlib's default) or the form body."""
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "basic":
        return b64decode(credentials).decode().partition(":")[2]
    return form.get("client_secret", [None])[0]


class FakeIdp:
    """Signs ID tokens with a generated RSA key. `claims` is what the next login will carry."""

    def __init__(self) -> None:
        self.key = RSAKey.generate_key(2048, parameters={"kid": "idp-1", "use": "sig"})
        self.claims: dict[str, Any] = {
            "sub": "oidc|alice",
            "name": "Alice Example",
            "preferred_username": "alice",
            "email": "alice@example.test",
        }
        self.codes: dict[str, dict[str, str]] = {}
        self.server = LiveServer(self._app())

    # ---- lifecycle ----

    def start(self) -> FakeIdp:
        self.server.start()
        return self

    def stop(self) -> None:
        self.server.stop()

    @property
    def issuer(self) -> str:
        return self.server.url

    # ---- tokens ----

    def token(
        self,
        *,
        audience: str | list[str] = CLIENT_ID,
        issuer: str | None = None,
        lifetime: int = 3600,
        key: RSAKey | None = None,
        algorithm: str = "RS256",
        **extra: Any,
    ) -> str:
        """A signed JWT access token. Override the defaults to build a bad one."""
        now = int(time.time())
        claims = {
            "iss": issuer or self.issuer,
            "aud": audience,
            "iat": now,
            "exp": now + lifetime,
            **self.claims,
            **extra,
        }
        signing_key = key or self.key
        return jwt.encode({"alg": algorithm, "kid": signing_key.kid}, claims, signing_key)

    # ---- the provider ----

    def _app(self) -> Starlette:
        async def discovery(_request: Request) -> Response:
            return JSONResponse(
                {
                    "issuer": self.issuer,
                    "authorization_endpoint": f"{self.issuer}/authorize",
                    "token_endpoint": f"{self.issuer}/token",
                    "jwks_uri": f"{self.issuer}/jwks",
                    "response_types_supported": ["code"],
                    "subject_types_supported": ["public"],
                    "id_token_signing_alg_values_supported": ["RS256"],
                    "token_endpoint_auth_methods_supported": [
                        "client_secret_basic",
                        "client_secret_post",
                    ],
                    "code_challenge_methods_supported": ["S256"],
                }
            )

        async def jwks(_request: Request) -> Response:
            return JSONResponse({"keys": [self.key.as_dict(private=False)]})

        async def authorize(request: Request) -> Response:
            query = request.query_params
            code = f"code-{len(self.codes) + 1}"
            self.codes[code] = {
                "nonce": query.get("nonce", ""),
                "challenge": query["code_challenge"],
            }
            return RedirectResponse(
                f"{query['redirect_uri']}?{urlencode({'code': code, 'state': query['state']})}"
            )

        async def token(request: Request) -> Response:
            form = parse_qs((await request.body()).decode())  # urlencoded; no python-multipart
            grant = self.codes.pop(form.get("code", [""])[0], None)
            if grant is None or _client_secret(request, form) != CLIENT_SECRET:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            id_token = self.token(nonce=grant["nonce"])
            return JSONResponse(
                {"access_token": self.token(), "token_type": "Bearer", "id_token": id_token}
            )

        return Starlette(
            routes=[
                Route("/.well-known/openid-configuration", discovery),
                Route("/jwks", jwks),
                Route("/authorize", authorize),
                Route("/token", token, methods=["POST"]),
            ]
        )
