"""Audio configuration for Samva voice agent."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AudioConfig:
    """Audio I/O settings for the Gemini Live API and local playback."""

    # Gemini Live API expects 16 kHz PCM input
    input_sample_rate: int = field(
        default_factory=lambda: int(os.environ.get("SAMVA_INPUT_SAMPLE_RATE", "16000"))
    )
    # Gemini Live API produces 24 kHz PCM output
    output_sample_rate: int = field(
        default_factory=lambda: int(os.environ.get("SAMVA_OUTPUT_SAMPLE_RATE", "24000"))
    )
    channels: int = 1
    # PyAudio frames per buffer
    chunk_size: int = field(
        default_factory=lambda: int(os.environ.get("SAMVA_CHUNK_SIZE", "1024"))
    )
