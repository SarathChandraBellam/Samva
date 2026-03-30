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
from fastapi.responses import JSONResponse, PlainTextResponse

from ..config import Config
from ..knowledge_base.manager import KnowledgeBaseManager
from ..providers import GeminiProvider
from ..tools import (
    CollectInfoTool,
    EscalateTool,
    KnowledgeBaseTool,
    ScheduleCallbackTool,
    ToolRegistry,
)
from .call_session import TwilioCallSession

logger = logging.getLogger(__name__)

_TWIML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{stream_url}" />
    </Connect>
</Response>"""


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

class _AppState:
    config: Config
    provider: GeminiProvider
    kb: KnowledgeBaseManager
    store_name: str
    stream_url: str


def _build_tool_registry(kb: KnowledgeBaseManager, store_name: str) -> ToolRegistry:
    """
    Construct the default tool registry for phone calls.

    Customise here to add, remove, or reconfigure tools.  Each tool can accept
    an ``on_*`` callback for side-effects (CRM writes, calendar entries, etc.).
    """
    registry = ToolRegistry()
    registry.register(KnowledgeBaseTool(kb, store_name))
    registry.register(EscalateTool())
    registry.register(CollectInfoTool())
    registry.register(ScheduleCallbackTool())
    return registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = _AppState()
    state.config = Config()
    state.config.validate()

    state.provider = GeminiProvider(state.config)
    client = state.provider.get_client()

    state.kb = KnowledgeBaseManager(
        client=client,
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
    """Twilio POSTs here when an inbound call arrives."""
    s = _s(request)
    twiml = _TWIML.format(stream_url=s.stream_url)
    logger.info("Incoming call → media stream at %s", s.stream_url)
    return PlainTextResponse(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# WebSocket endpoint — one connection per active call
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

            if event == "connected":
                logger.info("Twilio WS connected (protocol=%s)", msg.get("protocol"))

            elif event == "start":
                info = msg["start"]
                call_sid = info["callSid"]
                stream_sid = msg["streamSid"]

                tool_registry = _build_tool_registry(s.kb, s.store_name)
                system_prompt = s.config.resolve_prompt()

                session = TwilioCallSession(
                    call_sid=call_sid,
                    stream_sid=stream_sid,
                    websocket=websocket,
                    client=s.provider.get_client(),
                    live_model=s.config.live_model,
                    system_prompt=system_prompt,
                    voice_name=s.config.voice_name,
                    tool_registry=tool_registry,
                )
                await session.start()
                logger.info(
                    "Call started | callSid=%s | streamSid=%s", call_sid, stream_sid
                )

            elif event == "media":
                if session:
                    track = msg["media"].get("track", "inbound")
                    if track == "inbound":
                        await session.push_audio(msg["media"]["payload"])
                    else:
                        logger.debug("Skipping %s track", track)

            elif event == "stop":
                logger.info("Call stopped | callSid=%s", call_sid)
                break

            elif event == "mark":
                logger.debug("Mark: %s", msg.get("mark", {}).get("name"))

    except WebSocketDisconnect:
        logger.info("Twilio WS disconnected | callSid=%s", call_sid)
    except Exception as exc:
        logger.exception("Unexpected error | callSid=%s | error=%s", call_sid, exc)
    finally:
        if session:
            await session.stop()
