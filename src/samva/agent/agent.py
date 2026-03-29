"""VoiceAgent: wires together KB manager, Live session, and audio I/O."""
from __future__ import annotations

import asyncio
import logging

from google import genai

from ..config import Config
from ..knowledge_base.manager import KnowledgeBaseManager
from ..live.audio import AudioCapture, AudioPlayer
from ..live.session import LiveVoiceSession

logger = logging.getLogger(__name__)


class VoiceAgent:
    """
    High-level orchestrator.

    Usage::

        agent = VoiceAgent(config)
        agent.setup_knowledge_base()   # idempotent — connect or create store
        asyncio.run(agent.run())
    """

    def __init__(self, config: Config) -> None:
        config.validate()
        self.config = config
        self.client = genai.Client(api_key=config.api_key)
        self.kb = KnowledgeBaseManager(
            client=self.client,
            search_model=config.search_model,
        )
        self._store_name: str | None = None

    # ------------------------------------------------------------------
    # Knowledge base
    # ------------------------------------------------------------------

    def setup_knowledge_base(self) -> str:
        """Connect to (or create) the configured knowledge base store."""
        self._store_name = self.kb.create_or_get_store(self.config.kb_store_name)
        docs = self.kb.list_documents(self._store_name)
        logger.info(
            "Knowledge base ready | store=%s | documents=%d",
            self._store_name,
            len(docs),
        )
        return self._store_name

    def _search(self, query: str) -> str:
        """Synchronous search called from the async tool-call handler."""
        if not self._store_name:
            return "Knowledge base is not initialised."
        return self.kb.search(self._store_name, query)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the real-time voice session (blocks until Ctrl+C)."""
        if not self._store_name:
            self.setup_knowledge_base()

        capture = AudioCapture(
            sample_rate=self.config.input_sample_rate,
            channels=self.config.channels,
            chunk_size=self.config.chunk_size,
        )
        player = AudioPlayer(
            sample_rate=self.config.output_sample_rate,
            channels=self.config.channels,
        )

        session = LiveVoiceSession(
            client=self.client,
            model=self.config.live_model,
            system_prompt=self.config.system_prompt,
            voice_name=self.config.voice_name,
            search_fn=self._search,
            capture=capture,
            player=player,
        )

        try:
            await session.run()
        finally:
            capture.close()
            player.close()
