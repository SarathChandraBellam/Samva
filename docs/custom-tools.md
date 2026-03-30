# Custom Tools — Appointment Booking Example

Any action your agent needs to take — booking an appointment, looking up an order, creating a support ticket — is a tool. Tools are plain Python classes. Write one, register it, and the Live model can call it mid-conversation.

This guide shows a complete appointment booking tool as a concrete example.

---

## How tools work

The Live API supports function calling. You declare a function schema at session start. During the call, when the model decides it needs to book an appointment, it emits a `tool_call` message with the function name and extracted arguments. Samva's `ToolRegistry` dispatches it to your code and sends the result back as a `FunctionResponse`. The model then speaks a confirmation to the caller.

---

## The tool interface

Every tool is a class with three things:

```python
class MyTool:
    name = "my_function_name"           # must match declaration name

    declaration = types.FunctionDeclaration(
        name="my_function_name",
        description="What this tool does — the model reads this to decide when to call it.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "param": types.Schema(type=types.Type.STRING, description="..."),
            },
            required=["param"],
        ),
    )

    async def execute(self, args: dict) -> str:
        # Do the work. Return a plain string — the model reads it and speaks a response.
        return "Done. Confirmation: ..."
```

No base class needed. Any object that has `name`, `declaration`, and `async execute(args) -> str` works.

---

## Complete example: appointment booking

```python
# tools/book_appointment.py
from __future__ import annotations
import logging
from typing import Any
from google.genai import types

logger = logging.getLogger(__name__)


class BookAppointmentTool:
    """
    Book an appointment for the caller.

    The model calls this when a caller wants to schedule a visit, consultation,
    or service appointment. It extracts the details from the conversation and
    passes them here as structured arguments.
    """

    name = "book_appointment"

    declaration = types.FunctionDeclaration(
        name="book_appointment",
        description=(
            "Book an appointment for the caller. Use this when the caller wants "
            "to schedule a visit, consultation, demo, or service call. "
            "Collect name, preferred date/time, and reason before calling this."
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
                    description="Caller's phone number for the appointment reminder.",
                ),
                "preferred_date": types.Schema(
                    type=types.Type.STRING,
                    description="Preferred date, e.g. 'tomorrow', 'Friday 3pm', 'March 15'.",
                ),
                "reason": types.Schema(
                    type=types.Type.STRING,
                    description="Brief reason for the appointment.",
                ),
                "service_type": types.Schema(
                    type=types.Type.STRING,
                    description="Type of service, e.g. 'consultation', 'demo', 'repair'.",
                ),
            },
            required=["caller_name", "preferred_date"],
        ),
    )

    def __init__(self, calendar_api=None, on_booked=None) -> None:
        """
        Parameters
        ----------
        calendar_api:
            Any object with a .create_event(entry) method.
            If None, appointments are stored in-memory only.
        on_booked:
            Optional callback fired after each booking: on_booked(entry: dict)
        """
        self._calendar = calendar_api
        self._on_booked = on_booked
        self.appointments: list[dict] = []

    async def execute(self, args: dict[str, Any]) -> str:
        entry = {k: v for k, v in args.items() if v}
        self.appointments.append(entry)
        logger.info("[BookAppointmentTool] booked: %s", entry)

        # Push to your calendar system
        if self._calendar:
            try:
                self._calendar.create_event(entry)
            except Exception as exc:
                logger.warning("[BookAppointmentTool] calendar API error: %s", exc)
                return (
                    "I had trouble confirming with our calendar system. "
                    "Please tell the caller that someone will call them back to confirm."
                )

        if self._on_booked:
            try:
                self._on_booked(entry)
            except Exception as exc:
                logger.warning("[BookAppointmentTool] on_booked raised: %s", exc)

        name = entry.get("caller_name", "the caller")
        date = entry.get("preferred_date", "the requested time")
        service = entry.get("service_type", "appointment")

        return (
            f"Appointment booked for {name} — {service} on {date}. "
            "Confirm the details to the caller, thank them, and ask if there's "
            "anything else you can help with."
        )
```

---

## Register the tool

### Local mic mode

```python
import asyncio
from samva.agent import VoiceAgent
from samva.config import Config
from tools.book_appointment import BookAppointmentTool

config = Config()
config.enable_kb = False          # set in .env as SAMVA_ENABLE_KB=false if no KB needed
config.system_prompt = (
    "You are an appointment scheduler for Acme Clinic. "
    "Greet the caller, understand their need, collect their name and preferred time, "
    "then use book_appointment to confirm the booking. "
    "Always confirm the details before booking."
)

agent = VoiceAgent(config)
agent.tools.register(BookAppointmentTool(on_booked=lambda e: print("Booked:", e)))

asyncio.run(agent.run())
```

Or via `.env` + CLI with no code changes:

```env
SAMVA_ENABLE_KB=false
SAMVA_PROMPT_TEMPLATE=clinic_scheduler
```

```bash
uv run samva-run --no-kb --prompt-template clinic_scheduler
```

### Twilio bridge (phone calls)

In `twilio_bridge/app.py`, find `_build_tool_registry` and add your tool:

```python
from myapp.tools.book_appointment import BookAppointmentTool

def _build_tool_registry(kb, store_name, config):
    registry = ToolRegistry()
    if config.enable_kb:
        registry.register(KnowledgeBaseTool(kb, store_name))
    registry.register(BookAppointmentTool(calendar_api=my_calendar))
    registry.register(EscalateTool())
    return registry
```

`config.enable_kb` is read from `SAMVA_ENABLE_KB` in `.env` — flip the variable to include or exclude the KB without touching this function.

---

## Combine with the knowledge base

Register both and the model uses whichever fits:

```python
# .env
SAMVA_ENABLE_KB=true
```

```python
agent.setup_knowledge_base()   # registers search_knowledge_base

agent.tools.register(BookAppointmentTool())
agent.tools.register(EscalateTool())
agent.tools.register(CollectInfoTool())
```

The model will search the KB when the caller has a question, and book an appointment when they're ready to schedule — without you managing the flow.

---

## Remove built-in tools

The default tool set includes `escalate_to_human`, `collect_caller_info`, and `schedule_callback`. Remove any you don't want:

```python
agent.tools.unregister("schedule_callback")   # using your own booking tool instead
agent.tools.unregister("collect_caller_info") # BookAppointmentTool collects info
```

---

## What the model receives

When you register `BookAppointmentTool`, the model sees this function declaration:

```
book_appointment(caller_name, phone_number?, preferred_date, reason?, service_type?)
  → "Book an appointment for the caller. Use this when the caller wants to schedule
     a visit, consultation, demo, or service call. Collect name, preferred date/time,
     and reason before calling this."
```

The description is the key. Write it clearly — the model reads it to decide when and how to call the function. Include guidance on what to collect first, when to call it, and what not to do.

---

## Returning errors to the model

If booking fails, return a plain English string. The model will speak it to the caller:

```python
async def execute(self, args):
    if not self._calendar.is_available(args["preferred_date"]):
        return (
            "That time slot is not available. "
            "Ask the caller for an alternative date or time."
        )
    ...
```

The model treats the return value as factual context and shapes its spoken response around it.

---

## More tool ideas

| Tool | What it does |
|------|-------------|
| `lookup_order_status` | Fetch order/ticket status from your backend |
| `create_support_ticket` | Open a ticket in Zendesk, Linear, Jira |
| `check_availability` | Query a calendar before offering time slots |
| `send_confirmation_sms` | Text the caller a summary or confirmation code |
| `verify_account` | Authenticate the caller by account number or PIN |
| `get_pricing` | Return current prices from a live pricing API |
