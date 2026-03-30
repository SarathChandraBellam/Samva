"""ToolRegistry — plug-in / plug-out registry for Live API tools."""
from __future__ import annotations

import logging
from typing import Any

from google.genai import types

from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry of tools available to the voice agent during a session.

    Tools are registered by name and dispatched dynamically when the model
    issues a function call.  Any object implementing :class:`BaseTool` can be
    registered; no subclassing required.

    Usage
    -----
    ::

        registry = ToolRegistry()
        registry.register(KnowledgeBaseTool(kb, store_name))
        registry.register(EscalateTool())

        # Plug out a tool at any time:
        registry.unregister("escalate_to_human")

        # Pass to session:
        session = LiveVoiceSession(..., tool_registry=registry)
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> "ToolRegistry":
        """Register a tool. Returns self for chaining."""
        self._tools[tool.name] = tool
        logger.debug("ToolRegistry: registered '%s'", tool.name)
        return self

    def unregister(self, name: str) -> "ToolRegistry":
        """Remove a tool by name (no-op if not registered). Returns self."""
        if name in self._tools:
            del self._tools[name]
            logger.debug("ToolRegistry: unregistered '%s'", name)
        return self

    def has(self, name: str) -> bool:
        """Return True if a tool with this name is registered."""
        return name in self._tools

    def names(self) -> list[str]:
        """Return the names of all registered tools."""
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # Gemini integration
    # ------------------------------------------------------------------

    def get_tool_config(self) -> types.Tool | None:
        """
        Return a ``types.Tool`` containing all registered function declarations,
        or ``None`` if no tools are registered.
        """
        if not self._tools:
            return None
        return types.Tool(
            function_declarations=[t.declaration for t in self._tools.values()]
        )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, name: str, args: dict[str, Any]) -> str:
        """
        Execute a registered tool by name and return its string result.

        Returns an error string if the tool is not found.
        """
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("ToolRegistry: unknown tool '%s'", name)
            return f"Unknown function: {name}"
        logger.debug("ToolRegistry: dispatching '%s' args=%s", name, args)
        try:
            return await tool.execute(args)
        except Exception as exc:
            logger.error("ToolRegistry: '%s' raised: %s", name, exc)
            return f"Tool '{name}' encountered an error: {exc}"
