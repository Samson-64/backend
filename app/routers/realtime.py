import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime import realtime
from app.services.auth_service import decode_access_token_claims, is_token_revoked
from app.database import SessionLocal
from app.models.user import User

logger = logging.getLogger("uvicorn.error")

router = APIRouter()

# Close codes: 1008 = policy/violation (bad token), used so clients can tell
# an auth failure from a transient network drop (and stop retrying with the
# same stale token until a fresh one is read from storage).
WS_INVALID_TOKEN = 1008


def _authenticate_socket(token: str) -> str | None:
    """Resolve a query-string token to a user id, honouring logout.

    Access tokens no longer expire, so the signature check alone would let a
    signed-out client reconnect forever. The revocation cutoff is checked here
    too; the handshake is infrequent enough that a short-lived session is fine.
    """
    if not token:
        return None
    claims = decode_access_token_claims(token)
    if claims is None:
        return None
    user_id = claims.get("sub")
    if not user_id:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or is_token_revoked(user, claims):
            return None
        return user_id
    except Exception:
        logger.exception("realtime: token check failed for user %s", user_id)
        return None
    finally:
        db.close()


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    user_id = _authenticate_socket(token)
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