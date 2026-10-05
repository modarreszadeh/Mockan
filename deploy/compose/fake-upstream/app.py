"""A tiny stand-in for a real backend, for the compose demo (profile `demo`).

`/echo` and `/{anything}` answer with what they received; `/limsa/api/v1/dashboard` is the "real"
endpoint of the PRD journey; `/identity/connect/token` plays the login.
"""

import base64

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

ALL = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


async def echo(request: Request) -> Response:
    body = await request.body()
    return JSONResponse(
        {
            "source": "fake-upstream",
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "headers": dict(request.headers),
            "body": base64.b64encode(body).decode(),
        }
    )


async def dashboard(_request: Request) -> Response:
    return JSONResponse({"source": "real backend", "widgets": []})


async def token(_request: Request) -> Response:
    return JSONResponse({"access_token": "demo-token", "token_type": "Bearer", "expires_in": 3600})


app = Starlette(
    routes=[
        Route("/limsa/api/v1/dashboard", dashboard, methods=ALL),
        Route("/identity/connect/token", token, methods=ALL),
        Route("/{path:path}", echo, methods=ALL),
    ]
)
