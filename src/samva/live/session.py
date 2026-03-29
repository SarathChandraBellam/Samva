"""Gemini Live API session with knowledge base tool integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from google import genai
from google.genai import types

from .audio import AudioCapture, AudioPlayer

logger = logging.getLogger(__name__)

# Sync callable: (query: str) -> str
SearchFn = Callable[[str], str]

# Function declaration exposed to the Live model
_SEARCH_KB_DECLARATION = types.FunctionDeclaration(
    name="search_knowledge_base",
    description=(
        "Search the knowledge base for information relevant to the user's question. "
        "Always call this before answering factual questions about the domain."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="Concise search query that captures the user's intent.",
            )
        },
        required=["query"],
    ),
)


class LiveVoiceSession:
    """
    Connects to Gemini Live API, streams microphone audio in, plays
    speaker audio out, and handles knowledge-base tool calls in-loop.
    """

    def __init__(
        self,
        client: genai.Client,
        model: str,
        system_prompt: str,
        voice_name: str,
        search_fn: SearchFn,
        capture: AudioCapture,
        player: AudioPlayer,
    ) -> None:
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.voice_name = voice_name
        self.search_fn = search_fn
        self.capture = capture
        self.player = player

    # ------------------------------------------------------------------
    # Session config
    # ------------------------------------------------------------------

    def _build_config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
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
            tools=[
                types.Tool(function_declarations=[_SEARCH_KB_DECLARATION])
            ],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                    silence_duration_ms=700,
                )
            ),
        )

    # ------------------------------------------------------------------
    # Main coroutines
    # ------------------------------------------------------------------

    async def _send_audio_loop(self, session) -> None:
        """Continuously read mic chunks and stream them to the session."""
        while True:
            chunk = await self.capture.read()
            if chunk:
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=chunk,
                        mime_type="audio/pcm;rate=16000",
                    )
                )
            else:
                # Small sleep to avoid spinning when queue is empty
                await asyncio.sleep(0.01)

    async def _receive_loop(self, session) -> None:
        """Handle incoming server messages: audio, transcripts, tool calls."""
        async for message in session.receive():
            # ---- Tool call ------------------------------------------------
            if message.tool_call:
                await self._handle_tool_call(session, message.tool_call)
                continue

            # ---- Model audio / text output --------------------------------
            if message.server_content:
                content = message.server_content

                if content.model_turn:
                    for part in content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            await self.player.play(part.inline_data.data)

                # Log output transcription if available
                if content.output_transcription and content.output_transcription.text:
                    logger.info("[Agent] %s", content.output_transcription.text)

            # ---- Input transcription (user speech) ------------------------
            if (
                hasattr(message, "server_content")
                and message.server_content
                and hasattr(message.server_content, "input_transcription")
                and message.server_content.input_transcription
            ):
                txt = message.server_content.input_transcription.text
                if txt:
                    logger.info("[User]  %s", txt)

    async def _handle_tool_call(self, session, tool_call) -> None:
        """Execute knowledge base searches and return results to the model."""
        function_responses: list[types.FunctionResponse] = []

        for fn_call in tool_call.function_calls:
            if fn_call.name == "search_knowledge_base":
                query: str = fn_call.args.get("query", "")
                logger.info("[Tool]  search_knowledge_base(%r)", query)

                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, self.search_fn, query
                )
                logger.debug("[Tool]  result: %s", result[:200])

                function_responses.append(
                    types.FunctionResponse(
                        name=fn_call.name,
                        id=fn_call.id,
                        response={"result": result},
                    )
                )
            else:
                logger.warning("Unknown tool call: %s", fn_call.name)
                function_responses.append(
                    types.FunctionResponse(
                        name=fn_call.name,
                        id=fn_call.id,
                        response={"error": f"Unknown function: {fn_call.name}"},
                    )
                )

        if function_responses:
            await session.send_tool_response(
                function_responses=function_responses
            )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Connect to Gemini Live and run the voice loop until cancelled."""
        config = self._build_config()

        async with self.client.aio.live.connect(
            model=self.model, config=config
        ) as session:
            logger.info("Live session connected | model=%s | voice=%s",
                        self.model, self.voice_name)

            self.capture.start()
            self.player.start()

            send_task = asyncio.create_task(self._send_audio_loop(session))
            recv_task = asyncio.create_task(self._receive_loop(session))

            try:
                # Run until either task finishes (session closed or error)
                done, pending = await asyncio.wait(
                    [send_task, recv_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass
                # Re-raise any exception from completed tasks
                for t in done:
                    if not t.cancelled() and t.exception():
                        raise t.exception()  # type: ignore[misc]
            except asyncio.CancelledError:
                send_task.cancel()
                recv_task.cancel()
                await asyncio.gather(send_task, recv_task, return_exceptions=True)
            finally:
                self.capture.stop()
                self.player.stop()
                logger.info("Live session ended")
