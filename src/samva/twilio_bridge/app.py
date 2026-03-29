"""
FastAPI application: Twilio webhook + Media Streams WebSocket.

Endpoints
---------
POST /voice      Twilio calls this when a call arrives → returns TwiML
GET  /health     Liveness check
WS   /media      Twilio Media Streams bidirectional WebSocket
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, JSONResponse
from google import genai

from ..config import Config
from ..knowledge_base.manager import KnowledgeBaseManager
from .call_session import TwilioCallSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TwiML template – instructs Twilio to open a bidirectional media stream
# ---------------------------------------------------------------------------
_TWIML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{stream_url}" />
    </Connect>
</Response>"""


# ---------------------------------------------------------------------------
# Application state (initialised at startup via lifespan)
# ---------------------------------------------------------------------------
class _AppState:
    config: Config
    client: genai.Client
    kb: KnowledgeBaseManager
    store_name: str
    stream_url: str  # wss://your-host/media


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = _AppState()
    state.config = Config()
    state.config.validate()

    state.client = genai.Client(api_key=state.config.api_key)
    state.kb = KnowledgeBaseManager(
        client=state.client,
        search_model=state.config.search_model,
    )
    state.store_name = state.kb.create_or_get_store(state.config.kb_store_name)

    docs = state.kb.list_documents(state.store_name)
    logger.info(
        "Knowledge base ready | store=%s | docs=%d", state.store_name, len(docs)
    )

    host = os.environ.get("SAMVA_PUBLIC_HOST", "localhost:8000")
    state.stream_url = f"wss://{host}/media"
    logger.info("Stream URL: %s", state.stream_url)

    app.state.s = state
    yield
    logger.info("Server shutting down")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Samva Twilio Bridge", lifespan=lifespan)


def _s(request_or_ws: Any) -> _AppState:
    return request_or_ws.app.state.s


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.post("/voice")
async def voice(request: Request) -> PlainTextResponse:
    """
    Twilio POSTs here when an inbound call arrives.
    We respond with TwiML that starts a bidirectional Media Stream.
    """
    s = _s(request)
    twiml = _TWIML.format(stream_url=s.stream_url)
    logger.info("Incoming call → starting media stream at %s", s.stream_url)
    return PlainTextResponse(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# WebSocket endpoint – one connection per active call
# ---------------------------------------------------------------------------

@app.websocket("/media")
async def media(websocket: WebSocket) -> None:
    """
    Twilio Media Streams WebSocket.

    Message flow:
        connected → start → media × N → stop
    """
    await websocket.accept()

    s = _s(websocket)
    session: TwilioCallSession | None = None
    call_sid: str | None = None

    try:
        async for raw in websocket.iter_text():
            msg: dict = json.loads(raw)
            event: str = msg.get("event", "")

            # ---- connected ------------------------------------------------
            if event == "connected":
                logger.info("Twilio WS connected (protocol=%s)", msg.get("protocol"))

            # ---- start ----------------------------------------------------
            elif event == "start":
                info = msg["start"]
                call_sid = info["callSid"]
                stream_sid = msg["streamSid"]

                session = TwilioCallSession(
                    call_sid=call_sid,
                    stream_sid=stream_sid,
                    websocket=websocket,
                    client=s.client,
                    live_model=s.config.live_model,
                    system_prompt=s.config.system_prompt,
                    voice_name=s.config.voice_name,
                    search_fn=lambda q: s.kb.search(s.store_name, q),
                )
                await session.start()
                logger.info("Call started | callSid=%s | streamSid=%s", call_sid, stream_sid)

            # ---- media ----------------------------------------------------
            elif event == "media":
                if session:
                    track = msg["media"].get("track", "inbound")
                    if track == "inbound":
                        payload = msg["media"]["payload"]
                        await session.push_audio(payload)
                    else:
                        logger.debug("Skipping %s track", track)

            # ---- stop -----------------------------------------------------
            elif event == "stop":
                logger.info("Call stopped | callSid=%s", call_sid)
                break

            # ---- mark (playback confirmation) -----------------------------
            elif event == "mark":
                logger.debug("Mark received: %s", msg.get("mark", {}).get("name"))

    except WebSocketDisconnect:
        logger.info("Twilio WS disconnected | callSid=%s", call_sid)
    except Exception as exc:
        logger.exception("Unexpected error | callSid=%s | error=%s", call_sid, exc)
    finally:
        if session:
            await session.stop()
