import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime import realtime
from app.services.auth_service import decode_access_token

logger = logging.getLogger("uvicorn.error")

router = APIRouter()

# Close codes: 1008 = policy/violation (bad token), used so clients can tell
# an auth failure from a transient network drop (and stop retrying with the
# same stale token until a fresh one is read from storage).
WS_INVALID_TOKEN = 1008


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        logger.warning("realtime: rejected WebSocket with invalid token")
        await websocket.close(code=WS_INVALID_TOKEN)
        return

    await websocket.accept()
    realtime.connect(user_id, websocket)
    logger.info("realtime: user %s connected (%d online)", user_id, realtime.user_count())
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            # Clients only need the channel open; ignore any inbound frames.
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("realtime: socket error for user %s", user_id, exc_info=True)
    finally:
        realtime.disconnect(user_id, websocket)
        logger.info("realtime: user %s disconnected (%d online)", user_id, realtime.user_count())