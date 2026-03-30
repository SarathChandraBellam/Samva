"""Per-caller session: bridges one Twilio phone call ↔ one Gemini Live session."""
from __future__ import annotations

import asyncio
import json
import logging

from google import genai
from google.genai import types

from ..tools.escalate import ESCALATE_SIGNAL
from ..tools.registry import ToolRegistry
from .audio_conv import AudioConverter

logger = logging.getLogger(__name__)


class TwilioCallSession:
    """
    Mirrors the official Gemini Live API example pattern:
      - audio_queue  : inbound caller audio waiting to be sent to Gemini
      - send_audio   : drains queue → session.send_realtime_input
      - receive_audio: session responses → Twilio WebSocket

    Tools are fully pluggable via :class:`ToolRegistry`.  Pass any set of
    tools at construction time; the session dispatches all function calls
    through the registry with no hardcoded tool names.

    Special signal handling
    -----------------------
    If a tool result begins with ``ESCALATE:`` the session injects hold music
    text and can call an optional ``on_escalate`` hook before the model
    says goodbye and ends the interaction.
    """

    def __init__(
        self,
        call_sid: str,
        stream_sid: str,
        websocket,
        client: genai.Client,
        live_model: str,
        system_prompt: str,
        voice_name: str,
        tool_registry: ToolRegistry,
        on_escalate=None,
    ) -> None:
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.websocket = websocket
        self.client = client
        self.live_model = live_model
        self.system_prompt = system_prompt
        self.voice_name = voice_name
        self.tool_registry = tool_registry
        self.on_escalate = on_escalate

        self._converter = AudioConverter()
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._ready = asyncio.Event()
        self._run_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._run_task = asyncio.create_task(
            self._run(), name=f"session-{self.call_sid}"
        )
        logger.info("[%s] session started | tools=%s", self.call_sid, self.tool_registry.names())

    async def push_audio(self, base64_payload: str) -> None:
        """Called by the WebSocket handler for every inbound Twilio media chunk."""
        await self._ready.wait()
        pcm = self._converter.twilio_to_gemini(base64_payload)
        await self._audio_queue.put(pcm)

    async def stop(self) -> None:
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
            try:
                await self._run_task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("[%s] session stopped", self.call_sid)

    # ------------------------------------------------------------------
    # Core session
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        tools = []
        tool_config = self.tool_registry.get_tool_config()
        if tool_config:
            tools.append(tool_config)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=self.system_prompt)]
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice_name
                    )
                )
            ),
            tools=tools,
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        async with self.client.aio.live.connect(
            model=self.live_model, config=config
        ) as session:
            self._ready.set()
            logger.info("[%s] Gemini Live connected", self.call_sid)

            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._send_audio(session))
                    tg.create_task(self._receive_audio(session))
            except* asyncio.CancelledError:
                pass
            except* Exception as eg:
                for e in eg.exceptions:
                    logger.error("[%s] error: %s", self.call_sid, e)

    async def _send_audio(self, session) -> None:
        """Drain the inbound queue and stream PCM to Gemini."""
        while True:
            pcm = await self._audio_queue.get()
            await session.send_realtime_input(
                audio={"data": pcm, "mime_type": "audio/pcm;rate=16000"}
            )

    async def _receive_audio(self, session) -> None:
        """Receive Gemini responses and forward audio back to the caller."""
        while True:
            async for msg in session.receive():
                if msg.tool_call:
                    await self._handle_tool_call(session, msg.tool_call)
                    continue

                if msg.server_content:
                    content = msg.server_content

                    if getattr(content, "interrupted", False):
                        await self._send_clear()

                    if content.model_turn:
                        for part in content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                payload = self._converter.gemini_to_twilio(
                                    part.inline_data.data
                                )
                                await self._send_media(payload)

                    if content.output_transcription and content.output_transcription.text:
                        logger.info(
                            "[%s] Agent: %s",
                            self.call_sid,
                            content.output_transcription.text,
                        )

            # Drain stale audio queued while agent was speaking
            while not self._audio_queue.empty():
                self._audio_queue.get_nowait()

    async def _handle_tool_call(self, session, tool_call) -> None:
        """Dispatch function calls through the tool registry with hold feedback."""
        responses: list[types.FunctionResponse] = []

        for fn in tool_call.function_calls:
            # Give the caller feedback instead of silence
            await session.send_realtime_input(
                text="Say: 'One moment please.' Then wait silently."
            )
            try:
                result = await asyncio.wait_for(
                    self.tool_registry.dispatch(fn.name, fn.args or {}),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                logger.warning("[%s] tool '%s' timed out", self.call_sid, fn.name)
                result = (
                    "The operation timed out. Please answer from general knowledge "
                    "and suggest the caller try again."
                )

            # Handle escalation signal
            if result.startswith(ESCALATE_SIGNAL):
                logger.info("[%s] escalation triggered: %s", self.call_sid, result)
                if self.on_escalate:
                    try:
                        self.on_escalate(self.call_sid, result)
                    except Exception as exc:
                        logger.warning("[%s] on_escalate raised: %s", self.call_sid, exc)

            responses.append(
                types.FunctionResponse(
                    name=fn.name,
                    id=fn.id,
                    response={"result": result},
                )
            )

        await session.send_tool_response(function_responses=responses)

    # ------------------------------------------------------------------
    # Twilio helpers
    # ------------------------------------------------------------------

    async def _send_media(self, base64_mulaw: str) -> None:
        await self.websocket.send_text(
            json.dumps({
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": base64_mulaw},
            })
        )

    async def _send_clear(self) -> None:
        await self.websocket.send_text(
            json.dumps({
                "event": "clear",
                "streamSid": self.stream_sid,
            })
        )
