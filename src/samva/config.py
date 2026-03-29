"""Configuration for Samva voice agent."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Gemini API
    api_key: str = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY", "")
    )

    # Models
    live_model: str = field(
        default_factory=lambda: os.environ.get(
            "SAMVA_LIVE_MODEL", "gemini-3.1-flash-live-preview"
        )
    )
    search_model: str = field(
        default_factory=lambda: os.environ.get(
            "SAMVA_SEARCH_MODEL", "gemini-3-flash-preview"
        )
    )

    # Knowledge base
    kb_store_name: str = field(
        default_factory=lambda: os.environ.get(
            "SAMVA_KB_STORE_NAME", "samva-knowledge-base"
        )
    )

    # Voice settings
    voice_name: str = field(
        default_factory=lambda: os.environ.get("SAMVA_VOICE", "Kore")
    )

    # Audio
    input_sample_rate: int = 16_000   # PCM 16kHz for Live API input
    output_sample_rate: int = 24_000  # PCM 24kHz from Live API output
    channels: int = 1
    chunk_size: int = 1024            # frames per buffer

    # System prompt
    system_prompt: str = field(
        default_factory=lambda: os.environ.get(
            "SAMVA_SYSTEM_PROMPT",
            (
                "You are a helpful voice assistant named Samva. "
                "When users ask questions, always search the knowledge base first "
                "to find relevant information, then provide accurate and concise answers "
                "grounded in what you find. Keep responses conversational and brief, "
                "suitable for voice interaction. If the knowledge base doesn't contain "
                "relevant information, say so and answer from your general knowledge."
            ),
        )
    )

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )
