"""WebSocket hubs (D-18): the live request log of the signed-in Developer."""

import contextlib
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mockan.admin.auth import SESSION_KEY
from mockan.admin.hub import RequestLogHub
from mockan.admin.services import developers

router = APIRouter(tags=["hubs"])

CLOSE_UNAUTHENTICATED = 4401  # the WebSocket analogue of 401


@router.websocket("/hubs/request-log")
async def request_log(socket: WebSocket) -> None:
    """Pushes the caller's new request-log entries (the JSON of `GET /me/request-logs` items).

    Auth is the session cookie only. A request without one is refused during the handshake.
    """
    hub: RequestLogHub | None = socket.app.state.hub
    developer_id: uuid.UUID | None = None
    with contextlib.suppress(ValueError):
        developer_id = uuid.UUID(str(socket.session.get(SESSION_KEY)))
    if hub is None or developer_id is None:
        await socket.close(code=CLOSE_UNAUTHENTICATED)
        return
    async with socket.app.state.session_factory() as session:
        developer = await developers.get_by_id(session, developer_id)
    if developer is None:
        await socket.close(code=CLOSE_UNAUTHENTICATED)
        return

    await socket.accept()
    subscriber = await hub.subscribe(developer.id, socket)
    try:
        while True:
            await socket.receive_text()  # the Panel sends nothing; this notices a disconnect
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(developer.id, subscriber)
