"""Google Gemini provider — wraps google-genai SDK."""
from __future__ import annotations

import logging

from google import genai

from ..config import Config

logger = logging.getLogger(__name__)


class GeminiProvider:
    """
    Concrete :class:`LLMProvider` backed by Google Gemini (``google-genai``).

    The ``genai.Client`` is created lazily on first call to :meth:`get_client`
    and cached for the lifetime of the provider instance.

    Swapping provider
    -----------------
    Replace ``GeminiProvider`` with any class that implements the same three
    methods (``get_client``, ``get_live_model``, ``get_search_model``).
    No other code needs to change — the agent and sessions accept any provider.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: genai.Client | None = None

    # ------------------------------------------------------------------
    # LLMProvider protocol
    # ------------------------------------------------------------------

    def get_client(self) -> genai.Client:
        """Return (lazily created) Gemini client."""
        if self._client is None:
            self._client = genai.Client(api_key=self._config.api_key)
            logger.debug("GeminiProvider: client created")
        return self._client

    def get_live_model(self) -> str:
        return self._config.live_model

    def get_search_model(self) -> str:
        return self._config.search_model
