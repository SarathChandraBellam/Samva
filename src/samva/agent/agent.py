"""VoiceAgent: wires together provider, KB manager, tool registry, and audio I/O."""
from __future__ import annotations

import asyncio
import logging

from ..config import Config
from ..knowledge_base.manager import KnowledgeBaseManager
from ..live.audio import AudioCapture, AudioPlayer
from ..live.session import LiveVoiceSession
from ..providers import GeminiProvider, LLMProvider
from ..tools import (
    CollectInfoTool,
    EscalateTool,
    KnowledgeBaseTool,
    ScheduleCallbackTool,
    ToolRegistry,
)

logger = logging.getLogger(__name__)


class VoiceAgent:
    """
    High-level orchestrator for the local mic/speaker voice mode.

    Deploy as a standalone agent
    ----------------------------
    ::

        from samva.agent import VoiceAgent
        from samva.config import Config

        agent = VoiceAgent(Config())
        agent.setup_knowledge_base()

        # Add or remove tools before running:
        agent.tools.unregister("escalate_to_human")
        agent.tools.register(MyCustomTool())

        import asyncio
        asyncio.run(agent.run())

    Swap the LLM provider
    ---------------------
    ::

        from samva.providers.gemini import GeminiProvider
        # Or: from myapp.providers.openai import OpenAIRealtimeProvider

        agent = VoiceAgent(config, provider=OpenAIRealtimeProvider(config))
    """

    def __init__(
        self,
        config: Config,
        provider: LLMProvider | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.provider: LLMProvider = provider or GeminiProvider(config)
        self.client = self.provider.get_client()

        self.kb = KnowledgeBaseManager(
            client=self.client,
            search_model=config.search_model,
        )
        self._store_name: str | None = None

        # Tool registry — pre-populated with default tools.
        # Mutate before calling run() to customise behaviour.
        self.tools = ToolRegistry()

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
        # Register KB search tool now that store_name is known
        self.tools.register(KnowledgeBaseTool(self.kb, self._store_name))
        return self._store_name

    def add_default_call_tools(self) -> None:
        """
        Register the full default tool set (escalate, collect info, callback).

        Called automatically by :meth:`run` unless tools were already customised.
        """
        self.tools.register(EscalateTool())
        self.tools.register(CollectInfoTool())
        self.tools.register(ScheduleCallbackTool())

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the real-time voice session (blocks until Ctrl+C)."""
        if self.config.enable_kb and not self._store_name:
            self.setup_knowledge_base()

        # Add non-KB call tools if not already present
        if not self.tools.has("escalate_to_human"):
            self.add_default_call_tools()

        system_prompt = self.config.resolve_prompt()

        capture = AudioCapture(
            sample_rate=self.config.input_sample_rate,
            channels=self.config.channels,
            chunk_size=self.config.chunk_size,
        )
        player = AudioPlayer(
            sample_rate=self.config.output_sample_rate,
            channels=self.config.channels,
            capture=capture,
        )

        session = LiveVoiceSession(
            client=self.client,
            model=self.config.live_model,
            system_prompt=system_prompt,
            voice_name=self.config.voice_name,
            tool_registry=self.tools,
            capture=capture,
            player=player,
        )

        try:
            await session.run()
        finally:
            capture.close()
            player.close()
