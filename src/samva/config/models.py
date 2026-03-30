"""Model and voice configuration for Samva voice agent."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# All voices available in Gemini Live API
AVAILABLE_VOICES: list[str] = ["Kore", "Puck", "Charon", "Fenrir", "Aoede"]


@dataclass
class ModelConfig:
    """Gemini model identifiers and voice selection."""

    # Gemini Live API model for real-time voice streaming
    live_model: str = field(
        default_factory=lambda: os.environ.get(
            "SAMVA_LIVE_MODEL", "gemini-3.1-flash-live-preview"
        )
    )
    # Gemini model used for knowledge base RAG search
    search_model: str = field(
        default_factory=lambda: os.environ.get(
            "SAMVA_SEARCH_MODEL", "gemini-1.5-flash"
        )
    )
    # Voice persona for the agent
    voice_name: str = field(
        default_factory=lambda: os.environ.get("SAMVA_VOICE", "Kore")
    )

    def validate(self) -> None:
        if self.voice_name not in AVAILABLE_VOICES:
            raise ValueError(
                f"Invalid voice '{self.voice_name}'. "
                f"Available voices: {', '.join(AVAILABLE_VOICES)}"
            )
