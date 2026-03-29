"""
Audio format conversion between Twilio and Gemini Live API.

Twilio:      µ-law (G.711), 8 kHz, 8-bit, base64-encoded
Gemini in:   PCM linear, 16 kHz, 16-bit signed little-endian
Gemini out:  PCM linear, 24 kHz, 16-bit signed little-endian
"""
from __future__ import annotations

import base64

# audioop ships with CPython ≤ 3.12; audioop-lts is a drop-in for 3.13+
try:
    import audioop
except ModuleNotFoundError:          # Python 3.13+
    import audioop_lts as audioop    # type: ignore[no-redef]


class AudioConverter:
    """
    Stateful converter that maintains audioop.ratecv state for smooth
    resampling across successive audio chunks.
    """

    def __init__(self) -> None:
        self._in_state: object = None   # 8 kHz → 16 kHz filter state
        self._out_state: object = None  # 24 kHz → 8 kHz filter state

    # ------------------------------------------------------------------
    # Twilio → Gemini
    # ------------------------------------------------------------------

    def twilio_to_gemini(self, base64_payload: str) -> bytes:
        """
        Decode Twilio's base64 µ-law 8 kHz chunk → PCM 16 kHz 16-bit.
        """
        mulaw = base64.b64decode(base64_payload)
        pcm_8k = audioop.ulaw2lin(mulaw, 2)                            # → PCM 16-bit @ 8 kHz
        pcm_16k, self._in_state = audioop.ratecv(                      # upsample to 16 kHz
            pcm_8k, 2, 1, 8_000, 16_000, self._in_state
        )
        return pcm_16k

    # ------------------------------------------------------------------
    # Gemini → Twilio
    # ------------------------------------------------------------------

    def gemini_to_twilio(self, pcm_24k: bytes) -> str:
        """
        Convert Gemini's raw PCM 24 kHz 16-bit → base64 µ-law 8 kHz for Twilio.
        """
        pcm_8k, self._out_state = audioop.ratecv(                      # downsample to 8 kHz
            pcm_24k, 2, 1, 24_000, 8_000, self._out_state
        )
        mulaw = audioop.lin2ulaw(pcm_8k, 2)                            # PCM → µ-law
        return base64.b64encode(mulaw).decode()
