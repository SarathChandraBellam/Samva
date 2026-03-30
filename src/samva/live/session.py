"""Gemini Live API session with pluggable tool registry."""
from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import types

from ..tools.registry import ToolRegistry
from .audio import AudioCapture, AudioPlayer

logger = logging.getLogger(__name__)


class LiveVoiceSession:
    """
    Connects to Gemini Live API, streams microphone audio in, plays
    speaker audio out, and dispatches tool calls through a :class:`ToolRegistry`.

    Tools are fully plug-in / plug-out — pass any :class:`ToolRegistry` to add
    or remove capabilities without changing session code.
    """

    def __init__(
        self,
        client: genai.Client,
        model: str,
        system_prompt: str,
        voice_name: str,
        tool_registry: ToolRegistry,
        capture: AudioCapture,
        player: AudioPlayer,
    ) -> None:
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.voice_name = voice_name
        self.tool_registry = tool_registry
        self.capture = capture
        self.player = player

    # ------------------------------------------------------------------
    # Session config
    # ------------------------------------------------------------------

    def _build_config(self) -> types.LiveConnectConfig:
        tools = []
        tool_config = self.tool_registry.get_tool_config()
        if tool_config:
            tools.append(tool_config)

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
            tools=tools,
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
        """Stream mic audio to Gemini continuously (echo gate handled in AudioCapture)."""
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
                await asyncio.sleep(0.01)

    async def _receive_loop(self, session) -> None:
        """Handle incoming server messages: audio, transcripts, tool calls."""
        # session.receive() yields one complete turn then stops — loop to get all turns
        while True:
            async for message in session.receive():
                if message.tool_call:
                    await self._handle_tool_call(session, message.tool_call)
                    continue

                if message.server_content:
                    content = message.server_content

                    if content.model_turn:
                        for part in content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                await self.player.play(part.inline_data.data)

                    if content.output_transcription and content.output_transcription.text:
                        logger.info("[Agent] %s", content.output_transcription.text)

                if (
                    message.server_content
                    and getattr(message.server_content, "input_transcription", None)
                    and message.server_content.input_transcription.text
                ):
                    logger.info("[User]  %s", message.server_content.input_transcription.text)

            # Turn complete — outer loop continues waiting for next turn

    async def _handle_tool_call(self, session, tool_call) -> None:
        """Dispatch each function call through the tool registry."""
        function_responses: list[types.FunctionResponse] = []

        for fn_call in tool_call.function_calls:
            result = await self.tool_registry.dispatch(fn_call.name, fn_call.args or {})
            function_responses.append(
                types.FunctionResponse(
                    name=fn_call.name,
                    id=fn_call.id,
                    response={"result": result},
                )
            )

        if function_responses:
            await session.send_tool_response(function_responses=function_responses)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Connect to Gemini Live and run the voice loop until cancelled."""
        config = self._build_config()

        async with self.client.aio.live.connect(
            model=self.model, config=config
        ) as session:
            logger.info(
                "Live session connected | model=%s | voice=%s | tools=%s",
                self.model,
                self.voice_name,
                self.tool_registry.names(),
            )

            self.capture.start()
            self.player.start()

            send_task = asyncio.create_task(self._send_audio_loop(session))
            recv_task = asyncio.create_task(self._receive_loop(session))

            try:
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
