"""BaseTool protocol — interface every pluggable tool must satisfy."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from google.genai import types


@runtime_checkable
class BaseTool(Protocol):
    """
    Protocol that every tool registered with :class:`ToolRegistry` must implement.

    To add a new tool
    -----------------
    1. Create a module in ``samva/tools/`` (e.g. ``my_tool.py``).
    2. Define a class that satisfies this protocol::

           class MyTool:
               name = "my_tool_name"
               declaration = types.FunctionDeclaration(name="my_tool_name", ...)

               async def execute(self, args: dict[str, Any]) -> str:
                   ...

    3. Register it::

           registry.register(MyTool())

    4. The Live session will automatically expose it to the model and dispatch
       calls through :meth:`ToolRegistry.dispatch`.
    """

    @property
    def name(self) -> str:
        """Unique function name as declared to the model."""
        ...

    @property
    def declaration(self) -> types.FunctionDeclaration:
        """Gemini function declaration exposed to the Live API."""
        ...

    async def execute(self, args: dict[str, Any]) -> str:
        """
        Execute the tool and return a plain-text result.

        The result is sent back to the model as a FunctionResponse.
        For special side effects (e.g. call transfer), encode the intent as
        a structured string and handle it in the session layer.
        """
        ...
