"""ProxyTransformer: every row of arch §6.3 on plain header lists (PR-02, PR-03, PR-04, PR-09)."""

import pytest

from mockan.gateway.proxy.transform import (
    ForwardInfo,
    RouteMapping,
    build_request_headers,
    build_response_headers,
    build_upstream_path,
    build_upstream_url,
    hop_by_hop_names,
    origin_of,
)

INFO = ForwardInfo(
    developer_slug="ehtesham", scheme="https", host="mock.test", client_ip="203.0.113.7"
)


def request_headers(headers: list[tuple[str, str]], **overrides: object) -> dict[str, list[str]]:
    """`build_request_headers` as {name: [values]} for easy assertions."""
    options: dict[str, object] = {"info": INFO, "upstream_host": "limsa.stage.internal"}
    options.update(overrides)
    grouped: dict[str, list[str]] = {}
    for name, value in build_request_headers(headers, **options):  # type: ignore[arg-type]
        grouped.setdefault(name, []).append(value)
    return grouped


def mapping(
    *,
    base: str = "https://limsa.stage.internal",
    prefix: str = "/limsa",
    strip: bool = False,
) -> RouteMapping:
    return RouteMapping(
        developer_slug="ehtesham",
        public_base_url="https://mock.test",
        upstream_base_url=base,
        service_prefix=prefix,
        strip_prefix=strip,
    )


# ---- path and query -----------------------------------------------------------------------------


@pytest.mark.req("PR-02")
class TestUpstreamPath:
    def test_the_developer_slug_is_removed(self) -> None:
        path = build_upstream_path(
            raw_path="/ehtesham/limsa/api/v1/x",
            upstream_path="/limsa/api/v1/x",
            service_prefix="/limsa",
            strip_prefix=False,
        )
        assert path == "/limsa/api/v1/x"

    def test_percent_encoding_is_preserved_byte_for_byte(self) -> None:
        path = build_upstream_path(
            raw_path="/ehtesham/limsa/files/a%2Fb%20c",
            upstream_path="/limsa/files/a/b c",
            service_prefix="/limsa",
            strip_prefix=False,
        )
        assert path == "/limsa/files/a%2Fb%20c"

    def test_strip_prefix_removes_the_service_prefix_too(self) -> None:
        path = build_upstream_path(
            raw_path="/ehtesham/limsa/api/v1/x",
            upstream_path="/api/v1/x",
            service_prefix="/limsa",
            strip_prefix=True,
        )
        assert path == "/api/v1/x"

    @pytest.mark.parametrize("raw", ["/ehtesham/limsa", "/ehtesham/LIMSA/"])
    def test_stripping_the_whole_path_leaves_the_root(self, raw: str) -> None:
        path = build_upstream_path(
            raw_path=raw, upstream_path="/", service_prefix="/limsa", strip_prefix=True
        )
        assert path == "/"

    def test_strip_prefix_ignores_the_case_of_the_prefix(self) -> None:
        path = build_upstream_path(
            raw_path="/ehtesham/LIMSA/Orders%2F1",
            upstream_path="/Orders/1",
            service_prefix="/limsa",
            strip_prefix=True,
        )
        assert path == "/Orders%2F1"

    def test_an_encoded_prefix_falls_back_to_the_decoded_path(self) -> None:
        path = build_upstream_path(
            raw_path="/ehtesham/lim%73a/x y",
            upstream_path="/x y",
            service_prefix="/limsa",
            strip_prefix=True,
        )
        assert path == "/x%20y"

    def test_without_a_raw_path_the_decoded_path_is_re_encoded(self) -> None:
        path = build_upstream_path(
            raw_path=None,
            upstream_path="/limsa/a b/ü%",
            service_prefix="/limsa",
            strip_prefix=False,
        )
        assert path == "/limsa/a%20b/%C3%BC%25"

    def test_an_encoded_slug_segment_does_not_leak_into_the_path(self) -> None:
        # `%2F` in the first segment decodes to a slash, so the raw and decoded paths disagree.
        path = build_upstream_path(
            raw_path="/ehtesham%2Flimsa/x",
            upstream_path="/x",
            service_prefix="/limsa",
            strip_prefix=True,
        )
        assert path == "/x"


@pytest.mark.req("PR-02")
@pytest.mark.parametrize(
    ("base", "path", "query", "expected"),
    [
        ("https://h.test", "/a/b", "", "https://h.test/a/b"),
        ("https://h.test/", "/a/b", "", "https://h.test/a/b"),
        ("https://h.test/base", "/a", "", "https://h.test/base/a"),
        ("https://h.test:8443", "/a", "x=1&y=%20z&flag", "https://h.test:8443/a?x=1&y=%20z&flag"),
        ("https://h.test", "/", "", "https://h.test/"),
    ],
)
def test_url_is_base_url_plus_path_plus_raw_query(
    base: str, path: str, query: str, expected: str
) -> None:
    assert build_upstream_url(base, path, query) == expected


# ---- request headers ----------------------------------------------------------------------------


class TestRequestHeaders:
    @pytest.mark.req("PR-02")
    def test_host_is_the_upstream_host_not_mockans(self) -> None:
        out = request_headers([("host", "mock.test"), ("accept", "*/*")])
        assert out["host"] == ["limsa.stage.internal"]
        assert out["accept"] == ["*/*"]

    @pytest.mark.req("PR-02")
    def test_hop_by_hop_headers_are_dropped(self) -> None:
        out = request_headers(
            [
                ("connection", "keep-alive"),
                ("keep-alive", "timeout=5"),
                ("proxy-authorization", "Basic x"),
                ("proxy-connection", "keep-alive"),
                ("te", "trailers"),
                ("trailer", "x"),
                ("transfer-encoding", "chunked"),
                ("upgrade", "h2c"),
                ("x-keep", "yes"),
            ]
        )
        assert "x-keep" in out
        for name in (
            "connection", "keep-alive", "proxy-authorization", "proxy-connection", "te",
            "trailer", "transfer-encoding", "upgrade",
        ):  # fmt: skip
            assert name not in out

    @pytest.mark.req("PR-02")
    def test_headers_named_in_connection_are_dropped_too(self) -> None:
        out = request_headers(
            [("connection", "Keep-Alive, X-Secret-Hop"), ("x-secret-hop", "1"), ("x-keep", "1")]
        )
        assert "x-secret-hop" not in out
        assert out["x-keep"] == ["1"]

    @pytest.mark.req("PR-02")
    def test_expect_is_not_forwarded(self) -> None:
        assert "expect" not in request_headers([("expect", "100-continue")])

    @pytest.mark.req("PR-02")
    def test_authorization_traceparent_and_duplicates_pass_through_in_order(self) -> None:
        headers = [
            ("authorization", "Bearer abc"),
            ("traceparent", "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
            ("cookie", "a=1"),
            ("x-multi", "one"),
            ("x-multi", "two"),
        ]
        out = build_request_headers(headers, info=INFO, upstream_host="limsa.stage.internal")
        assert [pair for pair in out if pair[0] in {name for name, _ in headers}] == headers

    @pytest.mark.req("PR-02")
    def test_x_forwarded_headers_are_set(self) -> None:
        out = request_headers([("host", "mock.test")])
        assert out["x-forwarded-for"] == ["203.0.113.7"]
        assert out["x-forwarded-proto"] == ["https"]
        assert out["x-forwarded-host"] == ["mock.test"]
        assert out["x-forwarded-prefix"] == ["/ehtesham"]

    @pytest.mark.req("PR-02")
    def test_x_mockan_developer_is_added(self) -> None:
        assert request_headers([])["x-mockan-developer"] == ["ehtesham"]

    @pytest.mark.req("PR-02")
    def test_client_supplied_forwarding_headers_are_replaced_not_trusted(self) -> None:
        out = request_headers(
            [
                ("host", "mock.test"),
                ("x-forwarded-proto", "gopher"),
                ("x-forwarded-host", "evil.test"),
                ("x-forwarded-prefix", "/other"),
                ("x-mockan-developer", "someone-else"),
            ]
        )
        assert out["x-forwarded-proto"] == ["https"]
        assert out["x-forwarded-host"] == ["mock.test"]
        assert out["x-forwarded-prefix"] == ["/ehtesham"]
        assert out["x-mockan-developer"] == ["ehtesham"]

    @pytest.mark.req("PR-02")
    def test_x_forwarded_for_extends_the_incoming_chain(self) -> None:
        out = request_headers([("x-forwarded-for", "198.51.100.1, 10.0.0.2")])
        assert out["x-forwarded-for"] == ["198.51.100.1, 10.0.0.2, 203.0.113.7"]

    @pytest.mark.req("PR-02")
    def test_x_forwarded_for_does_not_repeat_a_client_the_chain_already_ends_with(self) -> None:
        # Uvicorn's proxy-headers already resolved `scope["client"]` from the chain's last hop.
        out = request_headers([("x-forwarded-for", "198.51.100.1, 203.0.113.7")])
        assert out["x-forwarded-for"] == ["198.51.100.1, 203.0.113.7"]

    @pytest.mark.req("PR-02")
    def test_without_a_client_address_the_chain_is_untouched(self) -> None:
        info = ForwardInfo("ehtesham", "http", None, None)
        out = request_headers([], info=info)
        assert "x-forwarded-for" not in out
        assert "x-forwarded-host" not in out

    @pytest.mark.req("PR-04")
    def test_extra_headers_are_added_and_win_over_the_clients(self) -> None:
        out = request_headers(
            [("x-api-key", "from-browser"), ("accept", "*/*")],
            extra_headers={"X-Api-Key": "configured", "X-Tenant-Env": "stage"},
        )
        assert out["x-api-key"] == ["configured"]
        assert out["x-tenant-env"] == ["stage"]
        assert out["accept"] == ["*/*"]

    @pytest.mark.req("PR-04")
    def test_rewrite_origin_replaces_origin_and_referer_when_present(self) -> None:
        out = request_headers(
            [("origin", "http://localhost:5173"), ("referer", "http://localhost:5173/page?x=1")],
            rewrite_origin_to="https://limsa.stage.internal",
        )
        assert out["origin"] == ["https://limsa.stage.internal"]
        assert out["referer"] == ["https://limsa.stage.internal/"]

    @pytest.mark.req("PR-04")
    def test_rewrite_origin_does_not_invent_an_origin(self) -> None:
        out = request_headers([], rewrite_origin_to="https://limsa.stage.internal")
        assert "origin" not in out
        assert "referer" not in out

    @pytest.mark.req("PR-02")
    def test_origin_and_referer_are_forwarded_unchanged_by_default(self) -> None:
        out = request_headers([("origin", "http://localhost:5173"), ("referer", "http://x/y")])
        assert out["origin"] == ["http://localhost:5173"]
        assert out["referer"] == ["http://x/y"]

    @pytest.mark.req("PR-02")
    def test_websocket_handshake_headers_belong_to_one_hop(self) -> None:
        out = request_headers(
            [
                ("connection", "Upgrade"),
                ("upgrade", "websocket"),
                ("sec-websocket-key", "k"),
                ("sec-websocket-version", "13"),
                ("sec-websocket-extensions", "permessage-deflate"),
                ("sec-websocket-protocol", "chat"),
                ("cookie", "a=1"),
            ],
            websocket=True,
        )
        assert not any(name.startswith("sec-websocket-") for name in out)
        assert out["cookie"] == ["a=1"]

    def test_hop_by_hop_names_collects_connection_tokens(self) -> None:
        names = hop_by_hop_names([("Connection", "close, X-One"), ("connection", "x-two")])
        assert {"x-one", "x-two", "keep-alive", "upgrade"} <= names


# ---- Location (PR-03) ---------------------------------------------------------------------------


@pytest.mark.req("PR-03")
class TestLocationRewrite:
    @pytest.mark.parametrize(
        ("location", "expected"),
        [
            (
                "https://limsa.stage.internal/limsa/api/v1/x?y=1#frag",
                "https://mock.test/ehtesham/limsa/api/v1/x?y=1#frag",
            ),
            ("https://limsa.stage.internal", "https://mock.test/ehtesham/"),
            ("https://LIMSA.stage.internal:443/a", "https://mock.test/ehtesham/a"),
            ("//limsa.stage.internal/a", "https://mock.test/ehtesham/a"),
            ("/limsa/orders/1", "/ehtesham/limsa/orders/1"),
        ],
    )
    def test_locations_on_the_upstream_move_into_mockans_url_space(
        self, location: str, expected: str
    ) -> None:
        assert mapping().rewrite_location(location) == expected

    @pytest.mark.parametrize(
        "location",
        [
            "https://other.example/a",
            "http://limsa.stage.internal/a",  # different scheme: a different origin
            "https://limsa.stage.internal:8443/a",
            "relative/page",
            "../up",
            "?only=query",
            "mailto:someone@example.com",
        ],
    )
    def test_other_locations_are_left_alone(self, location: str) -> None:
        assert mapping().rewrite_location(location) == location

    def test_strip_prefix_puts_the_service_prefix_back(self) -> None:
        rewritten = mapping(strip=True).rewrite_location("https://limsa.stage.internal/api/x")
        assert rewritten == "https://mock.test/ehtesham/limsa/api/x"

    def test_the_base_url_path_is_not_part_of_mockans_url_space(self) -> None:
        rewritten = mapping(base="https://gw.stage/api", strip=True).rewrite_location(
            "https://gw.stage/api/orders/5"
        )
        assert rewritten == "https://mock.test/ehtesham/limsa/orders/5"

    def test_a_trailing_slash_on_the_public_base_url_is_ignored(self) -> None:
        route = RouteMapping("ehtesham", "https://mock.test/", "https://h.test", "/s", False)
        assert route.rewrite_location("https://h.test/a") == "https://mock.test/ehtesham/a"


# ---- Set-Cookie (PR-03) -------------------------------------------------------------------------


@pytest.mark.req("PR-03")
class TestSetCookieRewrite:
    def test_domain_is_removed(self) -> None:
        out = mapping().rewrite_set_cookie("a=1; Domain=limsa.stage.internal; Path=/x")
        assert "domain" not in out.lower()

    def test_path_is_prefixed_with_the_slug(self) -> None:
        assert mapping().rewrite_set_cookie("a=1; Path=/x").endswith("Path=/ehtesham/x")

    def test_a_cookie_without_path_is_scoped_to_the_slug(self) -> None:
        assert mapping().rewrite_set_cookie("a=1; HttpOnly") == "a=1; HttpOnly; Path=/ehtesham"

    def test_root_path_becomes_the_slug_without_a_trailing_slash(self) -> None:
        assert mapping().rewrite_set_cookie("a=1; Path=/") == "a=1; Path=/ehtesham"

    def test_secure_httponly_samesite_and_expiry_are_kept(self) -> None:
        cookie = (
            "sid=abc; Expires=Wed, 21 Oct 2026 07:28:00 GMT; Max-Age=60; "
            "Secure; HttpOnly; SameSite=None"
        )
        out = mapping().rewrite_set_cookie(cookie + "; Path=/api")
        assert out == cookie + "; Path=/ehtesham/api"

    def test_attribute_names_are_case_insensitive(self) -> None:
        out = mapping().rewrite_set_cookie("a=1; DOMAIN=x.test; PATH=/p; secure")
        assert out == "a=1; secure; Path=/ehtesham/p"

    def test_the_cookie_value_is_never_touched(self) -> None:
        out = mapping().rewrite_set_cookie("token=a=b==; Path=/")
        assert out.startswith("token=a=b==;")

    def test_strip_prefix_puts_the_service_prefix_into_the_path(self) -> None:
        route = mapping(strip=True)
        assert route.rewrite_set_cookie("a=1; Path=/x").endswith("Path=/ehtesham/limsa/x")
        assert route.rewrite_set_cookie("a=1; Path=/").endswith("Path=/ehtesham/limsa")

    def test_an_invalid_path_attribute_falls_back_to_the_root(self) -> None:
        assert mapping().rewrite_set_cookie("a=1; Path=relative").endswith("Path=/ehtesham")


# ---- response headers ---------------------------------------------------------------------------


class TestResponseHeaders:
    @pytest.mark.req("PR-09")
    def test_source_header_says_proxy_and_replaces_any_from_the_upstream(self) -> None:
        out = build_response_headers(
            [("x-mockan-source", "mock"), ("x-mockan-rule-id", "r1")], mapping()
        )
        assert out == [("x-mockan-source", "proxy")]

    @pytest.mark.req("PR-02")
    def test_hop_by_hop_headers_are_dropped(self) -> None:
        out = build_response_headers(
            [
                ("connection", "x-private"),
                ("x-private", "secret"),
                ("keep-alive", "timeout=5"),
                ("proxy-authenticate", "Basic"),
                ("trailer", "x"),
                ("transfer-encoding", "chunked"),
                ("x-keep", "yes"),
            ],
            mapping(),
        )
        assert [name for name, _ in out] == ["x-keep", "x-mockan-source"]

    @pytest.mark.req("PR-03")
    def test_upstream_cors_headers_are_stripped(self) -> None:
        out = build_response_headers(
            [
                ("access-control-allow-origin", "https://evil.example"),
                ("Access-Control-Allow-Credentials", "true"),
                ("access-control-expose-headers", "x-secret"),
                ("x-keep", "yes"),
            ],
            mapping(),
        )
        assert [name for name, _ in out] == ["x-keep", "x-mockan-source"]

    @pytest.mark.req("PR-02")
    def test_date_and_server_are_left_to_the_asgi_server(self) -> None:
        out = build_response_headers([("date", "x"), ("server", "nginx")], mapping())
        assert out == [("x-mockan-source", "proxy")]

    @pytest.mark.req("PR-02")
    def test_framing_and_encoding_headers_describing_the_raw_body_are_kept(self) -> None:
        out = build_response_headers(
            [("content-length", "42"), ("content-encoding", "gzip"), ("content-type", "text/x")],
            mapping(),
        )
        assert out[:3] == [
            ("content-length", "42"),
            ("content-encoding", "gzip"),
            ("content-type", "text/x"),
        ]

    @pytest.mark.req("PR-03")
    def test_each_set_cookie_line_is_rewritten_and_kept_separate(self) -> None:
        out = build_response_headers(
            [("set-cookie", "a=1; Path=/x"), ("set-cookie", "b=2; Domain=h.test")], mapping()
        )
        assert [value for name, value in out if name == "set-cookie"] == [
            "a=1; Path=/ehtesham/x",
            "b=2; Path=/ehtesham",
        ]

    @pytest.mark.req("PR-03")
    def test_location_is_rewritten_for_any_status(self) -> None:
        out = build_response_headers(
            [("location", "https://limsa.stage.internal/limsa/orders/9")], mapping()
        )
        assert ("location", "https://mock.test/ehtesham/limsa/orders/9") in out


def test_origin_of_drops_the_path_and_any_userinfo() -> None:
    assert origin_of("HTTPS://user:pw@Limsa.Stage.internal:8443/a/b?c") == (
        "https://limsa.stage.internal:8443"
    )
