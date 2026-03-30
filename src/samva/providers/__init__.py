"""Provider abstraction for Samva voice agent.

Swap out the underlying LLM backend by replacing :class:`GeminiProvider`
with any class implementing the :class:`LLMProvider` protocol.
"""
from .base import LLMProvider
from .gemini import GeminiProvider

__all__ = ["LLMProvider", "GeminiProvider"]
