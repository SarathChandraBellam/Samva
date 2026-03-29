"""Per-caller session: bridges one Twilio phone call ↔ one Gemini Live session."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from google import genai
from google.genai import types

from .audio_conv import AudioConverter

logger = logging.getLogger(__name__)

SearchFn = Callable[[str], str]

_SEARCH_KB_DECLARATION = types.FunctionDeclaration(
    name="search_knowledge_base",
    description=(
        "Search the knowledge base for information to answer the caller's question. "
        "Call this whenever the caller asks about domain-specific topics."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="Concise search query capturing the caller's intent.",
            )
        },
        required=["query"],
    ),
)


class TwilioCallSession:
    """
    Mirrors the official Gemini Live API example pattern:
      - audio_queue  : inbound caller audio waiting to be sent to Gemini
      - send_audio   : drains queue → session.send_realtime_input
      - receive_audio: session responses → Twilio WebSocket
    Both tasks run inside a TaskGroup so any error cancels the whole session.
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
        search_fn: SearchFn,
    ) -> None:
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.websocket = websocket
        self.client = client
        self.live_model = live_model
        self.system_prompt = system_prompt
        self.voice_name = voice_name
        self.search_fn = search_fn

        self._converter = AudioConverter()
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()  # unbounded, never drops
        self._ready = asyncio.Event()
        self._run_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._run_task = asyncio.create_task(self._run(), name=f"session-{self.call_sid}")
        logger.info("[%s] session started", self.call_sid)

    async def push_audio(self, base64_payload: str) -> None:
        """Called by the WebSocket handler for every inbound Twilio media chunk."""
        await self._ready.wait()
        pcm = self._converter.twilio_to_gemini(base64_payload)
        await self._audio_queue.put(pcm)   # blocking put — never drops audio

    async def stop(self) -> None:
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
            try:
                await self._run_task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("[%s] session stopped", self.call_sid)

    # ------------------------------------------------------------------
    # Core session — matches official Gemini Live API example
    # ------------------------------------------------------------------

    async def _run(self) -> None:
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
            tools=[types.Tool(function_declarations=[_SEARCH_KB_DECLARATION])],
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
        """Drain the inbound queue and stream PCM to Gemini — official pattern."""
        while True:
            pcm = await self._audio_queue.get()
            await session.send_realtime_input(
                audio={"data": pcm, "mime_type": "audio/pcm;rate=16000"}
            )

    async def _receive_audio(self, session) -> None:
        """Receive Gemini responses and forward audio back to the caller via Twilio."""
        while True:
            async for msg in session.receive():
                # Tool call
                if msg.tool_call:
                    await self._handle_tool_call(session, msg.tool_call)
                    continue

                if msg.server_content:
                    content = msg.server_content

                    # Barge-in: clear Twilio's playback buffer
                    if getattr(content, "interrupted", False):
                        await self._send_clear()

                    # Audio chunks → convert → send to caller
                    if content.model_turn:
                        for part in content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                payload = self._converter.gemini_to_twilio(part.inline_data.data)
                                await self._send_media(payload)

                    if content.output_transcription and content.output_transcription.text:
                        logger.info("[%s] Agent: %s", self.call_sid, content.output_transcription.text)

            # After each turn ends, drain the inbound queue of audio that
            # accumulated while the agent was speaking — discard stale chunks
            while not self._audio_queue.empty():
                self._audio_queue.get_nowait()

    async def _handle_tool_call(self, session, tool_call) -> None:
        responses: list[types.FunctionResponse] = []
        for fn in tool_call.function_calls:
            if fn.name == "search_knowledge_base":
                query = fn.args.get("query", "")
                logger.info("[%s] KB search: %r", self.call_sid, query)
                # Tell the caller something while we fetch — prevents dead silence
                await session.send_realtime_input(
                    text="Say: 'One moment please.' Then wait silently."
                )
                try:
                    loop = asyncio.get_running_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, self.search_fn, query),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("[%s] KB search timed out", self.call_sid)
                    result = "Search timed out. Please answer from general knowledge and suggest the caller try again."
                except Exception as e:
                    logger.error("[%s] KB search error: %s", self.call_sid, e)
                    result = "Knowledge base unavailable. Please answer from general knowledge."
            else:
                result = f"Unknown function: {fn.name}"

            responses.append(
                types.FunctionResponse(name=fn.name, id=fn.id, response={"result": result})
            )

        await session.send_tool_response(function_responses=responses)

    # ------------------------------------------------------------------
    # Twilio helpers
    # ------------------------------------------------------------------

    async def _send_media(self, base64_mulaw: str) -> None:
        await self.websocket.send_text(json.dumps({
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": base64_mulaw},
        }))

    async def _send_clear(self) -> None:
        await self.websocket.send_text(json.dumps({
            "event": "clear",
            "streamSid": self.stream_sid,
        }))
