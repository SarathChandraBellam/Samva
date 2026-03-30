"""EscalateTool — signal that the call should be transferred to a human agent."""
from __future__ import annotations

import logging
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)

# Sentinel prefix that the session layer can detect to trigger a real transfer
ESCALATE_SIGNAL = "ESCALATE:"


class EscalateTool:
    """
    Tool that the model calls when it needs to hand the call to a human agent.

    The :meth:`execute` method returns a string prefixed with ``ESCALATE:``.
    The session layer (``TwilioCallSession`` / ``LiveVoiceSession``) can inspect
    tool results for this prefix and perform the actual transfer (e.g. via
    Twilio's ``<Dial>`` verb or a queue API).

    Hook into escalation
    --------------------
    Pass an ``on_escalate`` callback when constructing the tool::

        def my_handler(reason: str) -> None:
            # Notify CRM, send Slack alert, etc.
            ...

        registry.register(EscalateTool(on_escalate=my_handler))
    """

    name = "escalate_to_human"

    declaration = types.FunctionDeclaration(
        name="escalate_to_human",
        description=(
            "Transfer the caller to a live human agent. "
            "Use this when the caller requests a human, the issue is too complex, "
            "or you have been unable to resolve the problem after two attempts."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "reason": types.Schema(
                    type=types.Type.STRING,
                    description="Brief reason for the escalation (shown to the agent).",
                ),
                "department": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Optional department to route to, e.g. 'billing', "
                        "'technical', 'sales'. Leave blank if unknown."
                    ),
                ),
            },
            required=["reason"],
        ),
    )

    def __init__(self, on_escalate=None) -> None:
        """
        Parameters
        ----------
        on_escalate:
            Optional ``(reason: str, department: str) -> None`` callback invoked
            when the model triggers this tool.
        """
        self._on_escalate = on_escalate

    async def execute(self, args: dict[str, Any]) -> str:
        reason: str = args.get("reason", "Caller requested a human agent.")
        department: str = args.get("department", "general")
        logger.info("[EscalateTool] reason=%r department=%r", reason, department)

        if self._on_escalate:
            try:
                self._on_escalate(reason, department)
            except Exception as exc:
                logger.warning("[EscalateTool] on_escalate callback raised: %s", exc)

        return (
            f"{ESCALATE_SIGNAL}{reason} | department={department}\n"
            "Please inform the caller that you are transferring them now and "
            "say goodbye warmly."
        )
