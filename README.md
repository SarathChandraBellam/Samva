# Samva — Real-Time Voice Agent on Gemini

Samva is a framework for building voice agents that handle real phone calls. You give it a personality, optionally a knowledge base and tools, and it handles the rest: listening, thinking, and speaking — all in real time.

It is built on two Gemini capabilities:

- **Gemini Live API** — bidirectional audio streaming with voice activity detection, barge-in support, and 90+ languages. The model hears the caller speak and responds in natural voice without any intermediate speech-to-text or text-to-speech pipeline.
- **Gemini File Search** — fully managed RAG. Upload your documents once; query them with a single API call. No vector database, no embeddings code, no retrieval plumbing to maintain.

---

## Core Idea

Traditional voice bots work like this: speech → STT → NLP → response → TTS → speech. Latency compounds at every step.

Gemini Live API collapses the entire pipeline. The model receives raw audio, reasons over it, and returns raw audio. When it needs domain knowledge it calls a tool (`search_knowledge_base`), gets the RAG answer back, and speaks a grounded response — all within a single live session.

```
Caller
  │  raw audio (PCM / µ-law)
  ▼
Gemini Live API  ──── function call ───▶  Gemini File Search
  │                                              │
  │  ◀──────────────── RAG answer ──────────────┘
  │
  ▼  raw audio response
Caller hears the answer
```

The two Gemini APIs communicate server-to-server. No audio is ever converted to text by your code — the model handles transcription, reasoning, and synthesis natively.

---

## What Can You Build

| Mode | How | Use case |
|------|-----|----------|
| Plain voice agent | `samva-run` | Conversational assistant, demo, prototype |
| Knowledge-grounded agent | Add KB store | FAQ bot, product support, internal helpdesk |
| Agent with custom tools | Register any tool | Appointment booking, CRM lookup, order status |
| Phone call agent | `samva-serve` + Twilio | Real inbound/outbound calls over PSTN |

Read the guides in [`docs/`](docs/) to see each mode with minimal code changes.

---

## How Gemini APIs Are Used

### Gemini Live API (`gemini-3.1-flash-live-preview`)

The session opens a persistent WebSocket to `client.aio.live.connect(model, config)`. Once connected:

- Your code streams raw PCM audio chunks from the microphone (or Twilio) via `session.send_realtime_input(audio=...)`.
- The model streams audio back in `message.server_content.model_turn.parts` as raw PCM.
- Voice activity detection and turn management are handled by the model — you do not need to segment speech or detect silence.
- Tool declarations are passed in `LiveConnectConfig.tools` at session start. When the model decides to call a tool, it emits a `tool_call` message. Your code executes the tool and calls `session.send_tool_response(...)`.

### Gemini File Search (RAG)

Documents are uploaded once with `client.files.upload()` and indexed into a File Search store. At query time:

```python
response = client.models.generate_content(
    model="gemini-1.5-flash",
    contents=query,
    config=types.GenerateContentConfig(
        tools=[types.Tool(file_search=types.FileSearch(file_ids=[...]))]
    ),
)
```

The model retrieves relevant chunks, reasons over them, and returns a grounded answer. No local retrieval code needed.

### How They Connect

The Live API model is configured with a `search_knowledge_base` function declaration. When the caller asks a domain-specific question, the Live model emits a function call. The session handler calls the File Search API, gets the answer, and sends it back as a `FunctionResponse`. The Live model then speaks the grounded answer.

---

## Architecture

```
Local mic mode
──────────────
  Microphone
      │ PCM 16kHz
      ▼
  AudioCapture (sounddevice)
      │ echo-gated PCM chunks
      ▼
  LiveVoiceSession  ──── tool call ───▶  KnowledgeBaseTool
      │                                        │
      │  ◀──────────── RAG answer ────────────┘
      ▼
  AudioPlayer (sounddevice)
      │ PCM 24kHz
      ▼
  Speakers


Phone call mode
───────────────
  Caller dials Twilio number
      │ POST /voice
      ▼
  FastAPI (samva-serve)  →  TwiML: connect WebSocket
      │ wss://.../media
      ▼
  TwilioCallSession
      │ µ-law 8kHz  ──▶  AudioConverter  ──▶  PCM 16kHz
      │                                           │
      │                                    Gemini Live API
      │                                           │
      │ µ-law 8kHz  ◀──  AudioConverter  ◀──  PCM 24kHz
      ▼
  Caller hears the answer
```

---

## Project Layout

```
src/samva/
├── agent/          VoiceAgent — wires everything together for local mic mode
├── cli/            samva-run, samva-serve, samva-setup-kb commands
├── config/         Config, ModelConfig, AudioConfig — env-var driven
├── knowledge_base/ Upload documents, manage File Search stores
├── live/           AudioCapture, AudioPlayer, LiveVoiceSession
├── prompts/        System prompt templates (plain .py modules with PROMPT string)
├── providers/      LLMProvider protocol + GeminiProvider implementation
├── tools/          BaseTool protocol, ToolRegistry, built-in tools
└── twilio_bridge/  FastAPI app, TwilioCallSession, µ-law↔PCM audio converter
```

Tools are plug-in / plug-out at runtime via `ToolRegistry.register()` and `.unregister()`. Prompts are swappable via `--prompt-template`. The LLM provider is behind a protocol — swap Gemini for any other backend without touching session code.

---

## Quickstart

### Prerequisites

- Python 3.11+
- `uv` — `pip install uv`
- [Gemini API key](https://aistudio.google.com/app/apikey)
- PortAudio (for local mic): `brew install portaudio`

### Install

```bash
git clone <repo-url> && cd samva
uv sync
```

### Configure

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY
```

### Run

```bash
# Local mic — speaks back through your speakers
uv run samva-run

# Phone calls via Twilio
uv run samva-serve --public-host your-ngrok-host.ngrok-free.app
```

---

## Guides

| Guide | What it covers |
|-------|---------------|
| [Plain voice agent](docs/plain-agent.md) | Run without a knowledge base — just a voice personality |
| [With knowledge base](docs/with-knowledge-base.md) | Ground answers in your documents |
| [Custom tools](docs/custom-tools.md) | Add appointment booking or any other tool |

---

## Available Voices

`Kore` (default) · `Puck` · `Charon` · `Fenrir` · `Aoede`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | required | Google AI Studio API key |
| `SAMVA_LIVE_MODEL` | `gemini-3.1-flash-live-preview` | Live conversation model |
| `SAMVA_SEARCH_MODEL` | `gemini-1.5-flash` | Model for KB RAG queries |
| `SAMVA_ENABLE_KB` | `true` | Set to `false` to disable knowledge base entirely |
| `SAMVA_KB_STORE_NAME` | `samva-knowledge-base` | File Search store name |
| `SAMVA_VOICE` | `Kore` | Agent voice |
| `SAMVA_SYSTEM_PROMPT` | — | Override system prompt inline |
| `SAMVA_PROMPT_TEMPLATE` | `default` | Template name from `prompts/` |
| `SAMVA_PUBLIC_HOST` | `localhost:8000` | Public host for Twilio stream URL |
