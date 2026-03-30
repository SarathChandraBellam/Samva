"""Provider protocol — abstract interface over any LLM backend."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """
    Minimal interface for an LLM backend provider.

    Implement this protocol to swap out Google Gemini for another backend
    (e.g. OpenAI Realtime, local Whisper + TTS, etc.).

    The provider is responsible for:
    - Creating and caching the SDK client
    - Exposing model identifiers for live streaming and search
    """

    def get_client(self) -> Any:
        """Return (or lazily create) the SDK client instance."""
        ...

    def get_live_model(self) -> str:
        """Return the model ID used for real-time voice streaming."""
        ...

    def get_search_model(self) -> str:
        """Return the model ID used for knowledge-base RAG search."""
        ...
