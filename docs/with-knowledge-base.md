# Voice Agent With Knowledge Base

Ground your agent's answers in your own documents using Gemini File Search — a fully managed RAG API. Upload once; the model retrieves relevant content automatically when the caller asks domain-specific questions.

---

## How it works

When the session starts, Samva declares a `search_knowledge_base(query)` tool to the Gemini Live model. During a call, when the caller asks something domain-specific, the model:

1. Emits a `tool_call` for `search_knowledge_base`
2. Your session handler calls the File Search API with the query
3. Gemini retrieves relevant chunks from your documents and returns a grounded answer
4. The Live model speaks the answer back to the caller

All of this happens within the live session — no extra latency from a separate retrieval service.

---

## Enable the knowledge base

KB is enabled by default (`SAMVA_ENABLE_KB=true`). Confirm it's on in your `.env`:

```env
SAMVA_ENABLE_KB=true
SAMVA_KB_STORE_NAME=samva-knowledge-base
SAMVA_SEARCH_MODEL=gemini-1.5-flash
```

---

## Upload your documents

```bash
# Upload a single file
uv run samva-setup-kb ./my-product-guide.pdf

# Upload everything in a folder
uv run samva-setup-kb ./docs/

# Check what's indexed
uv run samva-setup-kb ./docs/ --list
```

Supported formats: PDF, DOCX, XLSX, PPTX, TXT, MD, JSON, YAML, CSV, HTML, and 80+ more.

The store name defaults to `samva-knowledge-base` (set via `SAMVA_KB_STORE_NAME`). Re-run at any time to add new documents — existing ones stay indexed.

---

## Run

```bash
# Local mic — KB connects automatically
uv run samva-run

# Different store
uv run samva-run --store my-product-kb

# Phone calls
uv run samva-serve --public-host your-ngrok-host.ngrok-free.app
```

The model calls `search_knowledge_base` automatically whenever it decides the question needs domain knowledge. You don't configure when it searches — the model decides.

---

## Using in code

```python
import asyncio
from samva.agent import VoiceAgent
from samva.config import Config

config = Config()
# SAMVA_ENABLE_KB=true is the default, so no change needed
config.system_prompt = (
    "You are a support agent for Acme Corp. "
    "Always search the knowledge base before answering product questions. "
    "If the knowledge base has no relevant information, say so."
)

agent = VoiceAgent(config)

# Explicitly connect to the KB store and register the search tool
# (run() does this automatically if enable_kb=True and setup hasn't been called)
agent.setup_knowledge_base()

asyncio.run(agent.run())
```

`setup_knowledge_base()` connects to (or creates) the configured File Search store and registers `KnowledgeBaseTool` into `agent.tools`. From that point the model has access to `search_knowledge_base`.

---

## Using a different store per call (Twilio)

For phone calls you may want different knowledge bases for different departments. In `twilio_bridge/app.py`, the tool registry is built per call:

```python
def _build_tool_registry(kb, store_name):
    registry = ToolRegistry()
    registry.register(KnowledgeBaseTool(kb, store_name))
    registry.register(EscalateTool())
    registry.register(CollectInfoTool())
    return registry
```

Route to different stores based on the called number, IVR selection, or any other signal:

```python
store = "billing-kb" if called_number == "+15550001" else "support-kb"
registry = _build_tool_registry(kb, store)
```

---

## Customise when the model searches

The system prompt controls how aggressively the model uses the KB:

```python
# src/samva/prompts/support.py
PROMPT = (
    "You are a customer support agent for Acme Corp. "
    "For any question about products, pricing, return policies, or account issues, "
    "call search_knowledge_base first. Never guess on domain-specific details. "
    "If the search returns no relevant result, say: "
    "'I don't have that information right now — let me connect you with a specialist.'"
)
```

```bash
uv run samva-run --prompt-template support
```

---

## `.env` for KB mode

```env
GEMINI_API_KEY=your_key_here
SAMVA_ENABLE_KB=true
SAMVA_KB_STORE_NAME=acme-support-kb
SAMVA_SEARCH_MODEL=gemini-1.5-flash
SAMVA_LIVE_MODEL=gemini-3.1-flash-live-preview
SAMVA_VOICE=Kore
SAMVA_PROMPT_TEMPLATE=support
```

---

## Search timeout and fallback

KB searches have a 10-second timeout in `TwilioCallSession`. If the search takes too long, the model receives:

> "The operation timed out. Please answer from general knowledge and suggest the caller try again."

The call continues — the model answers from its training knowledge and the timeout is invisible to the caller beyond a slightly longer pause.

For local mic mode (`LiveVoiceSession`) there is no timeout — searches run to completion.
