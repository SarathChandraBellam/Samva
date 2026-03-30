"""KnowledgeBaseTool — searches the Gemini File Search RAG store."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.genai import types

from ..knowledge_base.manager import KnowledgeBaseManager

logger = logging.getLogger(__name__)


class KnowledgeBaseTool:
    """
    Tool that lets the model search the Gemini File Search knowledge base.

    The underlying search is synchronous (``KnowledgeBaseManager.search``),
    so :meth:`execute` runs it in the default thread executor to stay async-safe.
    """

    name = "search_knowledge_base"

    declaration = types.FunctionDeclaration(
        name="search_knowledge_base",
        description=(
            "Search the knowledge base for information relevant to the caller's "
            "question. Always call this before answering domain-specific questions."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="Concise search query capturing the caller's intent.",
                )
            },
            required=["query"],
        ),
    )

    def __init__(self, kb: KnowledgeBaseManager, store_name: str) -> None:
        self._kb = kb
        self._store_name = store_name

    async def execute(self, args: dict[str, Any]) -> str:
        query: str = args.get("query", "")
        if not query:
            return "No query provided."
        logger.info("[KBTool] search: %r", query)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, self._kb.search, self._store_name, query
        )
        logger.debug("[KBTool] result: %s", result[:200])
        return result
