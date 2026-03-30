"""ScheduleCallbackTool — arrange a callback appointment for the caller."""
from __future__ import annotations

import logging
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)


class ScheduleCallbackTool:
    """
    Tool that the model calls to schedule a return call for the caller.

    The tool stores the request in :attr:`scheduled` and fires an optional
    ``on_schedule`` callback so you can push it into a calendar, CRM, or queue.

    Hook into scheduling
    --------------------
    ::

        def push_to_calendar(entry: dict) -> None:
            calendar_api.create_event(entry)

        registry.register(ScheduleCallbackTool(on_schedule=push_to_calendar))
    """

    name = "schedule_callback"

    declaration = types.FunctionDeclaration(
        name="schedule_callback",
        description=(
            "Schedule a callback appointment when the caller cannot be helped "
            "immediately or prefers to be called back at a specific time. "
            "Use this instead of keeping the caller waiting indefinitely."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "caller_name": types.Schema(
                    type=types.Type.STRING,
                    description="Full name of the caller.",
                ),
                "phone_number": types.Schema(
                    type=types.Type.STRING,
                    description="Phone number to call back.",
                ),
                "preferred_time": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Caller's preferred callback time, e.g. "
                        "'tomorrow morning', '3pm Friday', 'anytime this week'."
                    ),
                ),
                "reason": types.Schema(
                    type=types.Type.STRING,
                    description="Brief reason for the callback.",
                ),
            },
            required=["phone_number", "preferred_time"],
        ),
    )

    def __init__(self, on_schedule=None) -> None:
        """
        Parameters
        ----------
        on_schedule:
            Optional ``(entry: dict) -> None`` callback fired when a callback
            is scheduled.
        """
        self._on_schedule = on_schedule
        self.scheduled: list[dict] = []

    async def execute(self, args: dict[str, Any]) -> str:
        entry = {k: v for k, v in args.items() if v}
        self.scheduled.append(entry)
        logger.info("[ScheduleCallbackTool] scheduled: %s", entry)

        if self._on_schedule:
            try:
                self._on_schedule(entry)
            except Exception as exc:
                logger.warning(
                    "[ScheduleCallbackTool] on_schedule callback raised: %s", exc
                )

        phone = entry.get("phone_number", "the number provided")
        time = entry.get("preferred_time", "as soon as possible")
        name = entry.get("caller_name", "the caller")

        return (
            f"Callback scheduled for {name} at {phone}, preferred time: {time}. "
            "Confirm the appointment to the caller and thank them for their patience."
        )
