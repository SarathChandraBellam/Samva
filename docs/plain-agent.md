# Plain Voice Agent — No Knowledge Base

Run Samva as a pure conversational voice agent. No documents to upload, no RAG queries — just a voice personality talking with the caller using Gemini's own knowledge.

---

## When to use this

- Prototyping a voice experience before adding domain data
- General-purpose assistant where Gemini's training is sufficient
- Demos, internal tooling, or any case where you control what gets asked

---

## Disable the knowledge base

The primary way is your `.env` file:

```env
SAMVA_ENABLE_KB=false
```

That's it. No code changes. The `search_knowledge_base` tool is never registered and the model answers entirely from its own knowledge and your system prompt.

Other options that do the same thing:

```bash
# CLI flag
uv run samva-run --no-kb

# Inline env override (without editing .env)
SAMVA_ENABLE_KB=false uv run samva-run
```

In code:

```python
config = Config()
config.enable_kb = False
```

---

## Set a personality via prompt

Combine with `--prompt-template` (or `SAMVA_PROMPT_TEMPLATE` in `.env`) to give the agent a specific role:

```python
# src/samva/prompts/aria.py
PROMPT = (
    "You are Aria, a friendly voice assistant for Acme Corp. "
    "Answer questions conversationally and concisely. "
    "If you don't know something, say so honestly."
)
```

```bash
uv run samva-run --no-kb --prompt-template aria
```

Or inline:

```bash
uv run samva-run --no-kb --prompt "You are Aria, a friendly assistant for Acme Corp."
```

---

## Phone calls without KB

Add `SAMVA_ENABLE_KB=false` to `.env` before starting the Twilio server — the same env var controls both modes:

```bash
uv run samva-serve \
  --public-host your-ngrok-host.ngrok-free.app \
  --prompt-template aria
```

---

## What changes when there's no KB

| With KB | Without KB |
|---------|-----------|
| Model calls `search_knowledge_base` tool | No tools exposed — model answers directly |
| Answers grounded in uploaded documents | Answers from Gemini training + system prompt |
| Caller hears "One moment please" during search | Responses are immediate |
| Requires `GEMINI_API_KEY` + File Search quota | Requires only `GEMINI_API_KEY` |

---

## `.env` for plain mode

```env
GEMINI_API_KEY=your_key_here
SAMVA_ENABLE_KB=false
SAMVA_VOICE=Kore
SAMVA_PROMPT_TEMPLATE=aria
```

No `SAMVA_KB_STORE_NAME` or `SAMVA_SEARCH_MODEL` needed.
