"""The OIDC code flow and bearer-token validation against a real fake provider (D-12, OQ-04)."""

import time
from collections.abc import AsyncIterator, Iterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from joserfc.jwk import RSAKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mockan.admin.app import create_app
from mockan.infrastructure.db.models import Developer
from mockan.infrastructure.settings import MockanSettings
from tests.support.fake_idp import CLIENT_ID, CLIENT_SECRET, FakeIdp

pytestmark = [pytest.mark.db, pytest.mark.req("PR-01")]


@pytest.fixture
def idp() -> Iterator[FakeIdp]:
    provider = FakeIdp().start()
    yield provider
    provider.stop()


@pytest.fixture
def oidc_settings(admin_settings: MockanSettings, idp: FakeIdp) -> MockanSettings:
    return admin_settings.model_copy(
        update={
            "auth_mode": "oidc",
            "oidc_issuer": idp.issuer,
            "oidc_client_id": CLIENT_ID,
            "oidc_client_secret": CLIENT_SECRET,
            "admin_sso_subjects": ["oidc|boss"],
        }
    )


@pytest.fixture
def oidc_app(
    oidc_settings: MockanSettings, session_factory: async_sessionmaker[AsyncSession]
) -> FastAPI:
    return create_app(oidc_settings, session_factory)


@pytest.fixture
async def client(oidc_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    # https: in oidc mode the session cookie is `Secure`, so an http client would not send it back.
    transport = httpx.ASGITransport(app=oidc_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://admin") as http:
        yield http


async def sign_in(client: httpx.AsyncClient, idp: FakeIdp) -> httpx.Response:
    """Run the whole code flow: Admin → provider → Admin's callback. Returns the callback answer."""
    login = await client.get("/api/v1/auth/login")
    assert login.status_code == 302 or login.status_code == 303, login.text
    async with httpx.AsyncClient() as browser:
        authorized = await browser.get(login.headers["location"])
    callback = urlsplit(authorized.headers["location"])
    return await client.get(f"{callback.path}?{callback.query}")


# ---- the authorization-code flow ----


async def test_login_redirects_to_the_provider_with_pkce(
    client: httpx.AsyncClient, idp: FakeIdp
) -> None:
    response = await client.get("/api/v1/auth/login")

    target = urlsplit(response.headers["location"])
    query = parse_qs(target.query)
    assert f"{target.scheme}://{target.netloc}" == idp.issuer
    assert target.path == "/authorize"
    assert query["client_id"] == [CLIENT_ID]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["https://admin/api/v1/auth/callback"]
    assert query["state"] and query["code_challenge"]
    assert "openid" in query["scope"][0]


async def test_the_callback_signs_the_developer_in(
    client: httpx.AsyncClient, idp: FakeIdp, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    callback = await sign_in(client, idp)

    assert callback.status_code == 303
    assert callback.headers["location"] == "/"
    assert "secure" in callback.headers["set-cookie"].lower()  # G-12
    me = (await client.get("/api/v1/me")).json()
    assert me["displayName"] == "Alice Example"  # `name` wins
    assert me["isAdmin"] is False
    async with session_factory() as session:
        developer = await session.scalar(select(Developer))
        assert developer is not None
        assert developer.sso_subject == "oidc|alice"


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        ({"name": None}, "alice"),  # preferred_username
        ({"name": None, "preferred_username": None}, "alice@example.test"),  # email
        ({"name": None, "preferred_username": None, "email": None}, "Developer"),
    ],
)
async def test_the_display_name_falls_back(
    client: httpx.AsyncClient, idp: FakeIdp, claims: dict[str, None], expected: str
) -> None:
    idp.claims.update(claims)

    await sign_in(client, idp)

    assert (await client.get("/api/v1/me")).json()["displayName"] == expected


async def test_admin_subjects_become_admins(client: httpx.AsyncClient, idp: FakeIdp) -> None:
    idp.claims["sub"] = "oidc|boss"

    await sign_in(client, idp)

    assert (await client.get("/api/v1/me")).json()["isAdmin"] is True


async def test_a_callback_with_a_wrong_state_is_unauthenticated(
    client: httpx.AsyncClient, idp: FakeIdp
) -> None:
    await client.get("/api/v1/auth/login")

    response = await client.get("/api/v1/auth/callback?code=code-1&state=forged")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_a_callback_without_a_login_is_unauthenticated(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/auth/callback?code=x&state=y")

    assert response.status_code == 401


async def test_the_dev_login_parameters_are_ignored_in_oidc_mode(
    client: httpx.AsyncClient, idp: FakeIdp
) -> None:
    response = await client.get("/api/v1/auth/login", params={"as": "root", "admin": "1"})

    assert urlsplit(response.headers["location"]).path == "/authorize"  # still the provider


# ---- bearer tokens ----


async def test_a_valid_bearer_token_signs_in_and_creates_the_developer(
    client: httpx.AsyncClient, idp: FakeIdp, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    token = idp.token()

    first = await client.get("/api/v1/me", headers={"authorization": f"Bearer {token}"})
    second = await client.get("/api/v1/me", headers={"authorization": f"bearer {token}"})

    assert first.status_code == 200
    assert first.json()["displayName"] == "Alice Example"
    assert second.json()["id"] == first.json()["id"]
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Developer)) == 1


async def test_an_audience_list_containing_the_client_is_accepted(
    client: httpx.AsyncClient, idp: FakeIdp
) -> None:
    token = idp.token(audience=["other-api", CLIENT_ID])

    response = await client.get("/api/v1/me", headers={"authorization": f"Bearer {token}"})

    assert response.status_code == 200


def forged_key() -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": "idp-1", "use": "sig"})  # same kid, new key


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda idp: idp.token(audience="someone-else"), id="wrong-audience"),
        pytest.param(lambda idp: idp.token(issuer="https://evil.example.com"), id="wrong-issuer"),
        pytest.param(lambda idp: idp.token(lifetime=-3600), id="expired"),
        pytest.param(lambda idp: idp.token(key=forged_key()), id="signed-by-another-key"),
        pytest.param(
            lambda idp: idp.token(key=RSAKey.generate_key(2048, parameters={"kid": "unknown"})),
            id="unknown-key-id",
        ),
        pytest.param(lambda idp: idp.token(sub=None), id="no-subject"),
        pytest.param(lambda idp: "not.a.jwt", id="garbage"),
        pytest.param(lambda idp: "", id="empty"),
    ],
)
async def test_bad_bearer_tokens_are_unauthenticated(
    client: httpx.AsyncClient, idp: FakeIdp, build: object
) -> None:
    token = build(idp)  # type: ignore[operator]

    response = await client.get("/api/v1/me", headers={"authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_a_token_without_an_expiry_is_rejected(
    client: httpx.AsyncClient, idp: FakeIdp
) -> None:
    from joserfc import jwt

    token = jwt.encode(
        {"alg": "RS256", "kid": idp.key.kid},
        {"iss": idp.issuer, "aud": CLIENT_ID, "sub": "oidc|alice"},
        idp.key,
    )

    response = await client.get("/api/v1/me", headers={"authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_a_token_signed_with_the_client_secret_is_rejected(
    client: httpx.AsyncClient, idp: FakeIdp
) -> None:
    """Algorithm confusion: HS256 with a shared secret must never validate."""
    from joserfc import jwt
    from joserfc.jwk import OctKey

    secret = OctKey.import_key(CLIENT_SECRET.ljust(32, "x"))
    token = jwt.encode(
        {"alg": "HS256"},
        {"iss": idp.issuer, "aud": CLIENT_ID, "sub": "oidc|alice", "exp": int(time.time()) + 600},
        secret,
    )

    response = await client.get("/api/v1/me", headers={"authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_only_the_bearer_scheme_counts(client: httpx.AsyncClient, idp: FakeIdp) -> None:
    for header in (f"Basic {idp.token()}", idp.token(), "Bearer", "Bearer   "):
        response = await client.get("/api/v1/me", headers={"authorization": header})
        assert response.status_code == 401, header


async def test_an_unreachable_provider_means_unauthenticated_not_a_crash(
    oidc_settings: MockanSettings, session_factory: async_sessionmaker[AsyncSession], idp: FakeIdp
) -> None:
    token = idp.token()
    idp.stop()
    app = create_app(oidc_settings, session_factory)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="https://admin") as http:
        response = await http.get("/api/v1/me", headers={"authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert "couldn't be verified" in response.json()["detail"]


async def test_a_rotated_signing_key_is_picked_up(client: httpx.AsyncClient, idp: FakeIdp) -> None:
    old = idp.token()
    assert (
        await client.get("/api/v1/me", headers={"authorization": f"Bearer {old}"})
    ).status_code == 200

    idp.key = RSAKey.generate_key(2048, parameters={"kid": "idp-2", "use": "sig"})
    new = idp.token()
    response = await client.get("/api/v1/me", headers={"authorization": f"Bearer {new}"})

    assert response.status_code == 200  # the unknown kid triggered one JWKS refetch


async def test_a_session_beats_a_bearer_token(client: httpx.AsyncClient, idp: FakeIdp) -> None:
    await sign_in(client, idp)
    idp.claims["sub"] = "oidc|someone-else"

    response = await client.get("/api/v1/me", headers={"authorization": f"Bearer {idp.token()}"})

    assert response.json()["displayName"] == "Alice Example"


# ---- misconfiguration fails at startup ----


def test_oidc_mode_needs_the_provider_settings(admin_settings: MockanSettings) -> None:
    settings = admin_settings.model_copy(update={"auth_mode": "oidc"})

    with pytest.raises(RuntimeError, match=r"MOCKAN_OIDC_ISSUER.*MOCKAN_OIDC_CLIENT_ID"):
        create_app(settings)


def test_a_short_session_secret_is_refused_outside_dev_mode(admin_settings: MockanSettings) -> None:
    settings = admin_settings.model_copy(update={"auth_mode": "oidc", "session_secret": "short"})

    with pytest.raises(RuntimeError, match="MOCKAN_SESSION_SECRET"):
        create_app(settings)


def test_dev_mode_may_run_without_a_session_secret(admin_settings: MockanSettings) -> None:
    settings = admin_settings.model_copy(update={"session_secret": ""})

    assert create_app(settings) is not None
