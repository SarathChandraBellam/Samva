"""Pluggable tool system for Samva voice agent.

Register any :class:`BaseTool`-compatible object with :class:`ToolRegistry`
to expose it to the Gemini Live model during a session.

Quick start
-----------
::

    from samva.tools import ToolRegistry
    from samva.tools.knowledge_base import KnowledgeBaseTool
    from samva.tools.escalate import EscalateTool
    from samva.tools.collect_info import CollectInfoTool
    from samva.tools.schedule_callback import ScheduleCallbackTool

    registry = ToolRegistry()
    registry.register(KnowledgeBaseTool(kb_manager, store_name))
    registry.register(EscalateTool(on_escalate=my_handler))
    registry.register(CollectInfoTool(on_collect=save_to_crm))
    registry.register(ScheduleCallbackTool(on_schedule=push_to_calendar))

    # Plug out a tool at any time:
    registry.unregister("escalate_to_human")
"""
from .base import BaseTool
from .collect_info import CollectInfoTool
from .escalate import EscalateTool
from .knowledge_base import KnowledgeBaseTool
from .registry import ToolRegistry
from .schedule_callback import ScheduleCallbackTool

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "KnowledgeBaseTool",
    "EscalateTool",
    "CollectInfoTool",
    "ScheduleCallbackTool",
]
