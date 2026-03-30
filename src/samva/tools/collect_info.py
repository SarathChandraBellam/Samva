"""CollectInfoTool — record caller-provided contact / account information."""
from __future__ import annotations

import logging
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)


class CollectInfoTool:
    """
    Tool that the model calls to persist information provided by the caller
    (name, email, account number, etc.).

    The collected fields are stored in-memory on the tool instance and can be
    retrieved via :attr:`collected` after the call ends.

    Hook into collection
    --------------------
    Pass an ``on_collect`` callback to react in real time::

        def save_to_crm(fields: dict) -> None:
            crm.upsert_contact(fields)

        registry.register(CollectInfoTool(on_collect=save_to_crm))
    """

    name = "collect_caller_info"

    declaration = types.FunctionDeclaration(
        name="collect_caller_info",
        description=(
            "Record information provided by the caller such as their name, "
            "email address, phone number, or account number. "
            "Call this as soon as the caller volunteers their details."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "name": types.Schema(
                    type=types.Type.STRING,
                    description="Caller's full name.",
                ),
                "email": types.Schema(
                    type=types.Type.STRING,
                    description="Caller's email address.",
                ),
                "phone": types.Schema(
                    type=types.Type.STRING,
                    description="Caller's phone number.",
                ),
                "account_number": types.Schema(
                    type=types.Type.STRING,
                    description="Caller's account or customer ID.",
                ),
                "notes": types.Schema(
                    type=types.Type.STRING,
                    description="Any additional notes about the caller's situation.",
                ),
            },
            required=[],
        ),
    )

    def __init__(self, on_collect=None) -> None:
        """
        Parameters
        ----------
        on_collect:
            Optional ``(fields: dict) -> None`` callback fired each time new
            info is collected.
        """
        self._on_collect = on_collect
        self.collected: dict[str, str] = {}

    async def execute(self, args: dict[str, Any]) -> str:
        # Merge non-empty fields into the running record
        new_fields = {k: v for k, v in args.items() if v}
        self.collected.update(new_fields)
        logger.info("[CollectInfoTool] collected: %s", new_fields)

        if self._on_collect and new_fields:
            try:
                self._on_collect(dict(self.collected))
            except Exception as exc:
                logger.warning("[CollectInfoTool] on_collect callback raised: %s", exc)

        if not new_fields:
            return "No information was provided to record."

        summary = ", ".join(f"{k}={v!r}" for k, v in new_fields.items())
        return f"Recorded caller information: {summary}. Thank the caller and continue."
