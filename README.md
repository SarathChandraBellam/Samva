# Samva — AI Voice Call Agent

A real-time voice call agent powered by **Gemini 3.1 Flash Live** and **Gemini File Search (RAG)**. Call a real phone number, speak naturally, and the agent searches your knowledge base and answers in human-like voice — all in real time.

Built on two Gemini capabilities launched in 2025:
- **[Gemini 3.1 Flash Live](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-3-1-flash-live/)** — low-latency bidirectional voice streaming with barge-in, VAD, and 90+ language support
- **[Gemini File Search](https://blog.google/innovation-and-ai/technology/developers-tools/file-search-gemini-api/)** — fully managed RAG: upload documents, query semantically with a single API call

---

## What We Built

### The Idea
Use the two new Gemini APIs together: **Live API** for real-time phone call audio, and **File Search** as a grounded knowledge base. When a caller asks a question, the Live model detects it needs domain knowledge, calls `search_knowledge_base`, gets a RAG answer, and speaks it back — all within the conversation flow.

### Architecture

```
📞 Caller dials Twilio number
         │
         ▼  POST /voice (TwiML)
   FastAPI server
         │  wss://.../media (bidirectional WebSocket)
         ▼
  TwilioCallSession
  ┌──────────────────────────────────────────────┐
  │  Twilio audio (µ-law 8kHz base64)            │
  │    → ulaw2lin → ratecv 8k→16k               │
  │    → Gemini Live (PCM 16kHz)                 │
  │                                              │
  │  Gemini Live (gemini-3.1-flash-live-preview) │
  │    ↕  function call: search_knowledge_base   │
  │         → Gemini File Search RAG             │
  │           (gemini-2.0-flash + your docs)     │
  │                                              │
  │  Gemini audio out (PCM 24kHz)               │
  │    → ratecv 24k→8k → lin2ulaw              │
  │    → Twilio (µ-law 8kHz base64)             │
  └──────────────────────────────────────────────┘
         │
         ▼
   📞 Caller hears the answer
```

### Two Modes

| Mode | Command | Use case |
|------|---------|----------|
| **Local mic** | `samva-run` | Test on your laptop with mic + speakers |
| **Phone call** | `samva-serve` | Real phone calls via Twilio |

---

## Technology Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Voice conversation | Gemini 3.1 Flash Live | Real-time bidirectional audio, VAD, barge-in |
| Knowledge base | Gemini File Search | Managed RAG, 100+ file formats, semantic search |
| Audio RAG search | gemini-2.0-flash | Fast, stable, supports File Search tool |
| Phone calls | Twilio Media Streams | WebSocket audio bridge for PSTN calls |
| Web server | FastAPI + Uvicorn | Async WebSocket handling for concurrent calls |
| Audio conversion | audioop (stdlib) | µ-law ↔ PCM, 8/16/24kHz resampling |
| Package manager | uv | Fast Python dependency management |

---

## Project Structure

```
samva/
├── src/samva/
│   ├── config.py               # All settings, env-var driven
│   ├── agent/
│   │   └── agent.py            # VoiceAgent: wires KB + Live session (local mode)
│   ├── live/
│   │   ├── audio.py            # PyAudio mic capture + speaker playback
│   │   └── session.py          # Gemini Live session (local mode)
│   ├── knowledge_base/
│   │   ├── manager.py          # Create/upload/search File Search stores
│   │   └── loader.py           # Discover supported files in a directory
│   ├── twilio_bridge/
│   │   ├── app.py              # FastAPI: POST /voice (TwiML) + WS /media
│   │   ├── call_session.py     # Per-caller Gemini Live session + KB tool
│   │   └── audio_conv.py       # µ-law ↔ PCM conversion (stateful)
│   └── cli/
│       ├── setup_kb.py         # samva-setup-kb
│       ├── run.py              # samva-run
│       └── serve.py            # samva-serve
├── knowledge/
│   └── sample_kb.txt           # Sample knowledge base document
├── scripts/
│   └── setup_twilio.py         # Buy & configure a Twilio phone number
├── .env.example
└── pyproject.toml
```

---

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — `pip install uv`
- **[Gemini API key](https://aistudio.google.com/app/apikey)** — from Google AI Studio
- **[PortAudio](https://www.portaudio.com/)** — for local mic mode: `brew install portaudio`
- *(Phone mode)* **[Twilio account](https://twilio.com)** — Account SID + Auth Token + a purchased phone number
- *(Phone mode)* **[ngrok](https://ngrok.com)** — `brew install ngrok` — to expose local server

---

## Setup

### 1. Install

```bash
git clone <repo-url> && cd samva
uv sync
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
GEMINI_API_KEY=your_key_here
SAMVA_LIVE_MODEL=gemini-3.1-flash-live-preview
SAMVA_SEARCH_MODEL=gemini-2.0-flash

# Phone mode only
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
```

### 3. Seed the Knowledge Base

Upload your documents (PDF, TXT, MD, DOCX, etc.):

```bash
# Single file
uv run samva-setup-kb ./my-document.pdf

# Entire directory
uv run samva-setup-kb ./docs/

# Check what's indexed
uv run samva-setup-kb ./knowledge/ --list
```

The first call creates a File Search store in your Gemini project. Subsequent calls add to the same store — you only need to re-run this when you want to add new documents.

---

## Running — Local Mic Mode

```bash
uv run samva-run
```

Speak into your microphone. The agent listens, searches the KB, and responds through your speakers.

```bash
# Options
uv run samva-run --voice Puck           # change voice
uv run samva-run --store my-store       # use a named KB store
uv run samva-run --verbose              # debug logging
```

Press **Ctrl+C** to stop.

---

## Running — Phone Call Mode

### Step 1 — Start ngrok (keep this terminal open)

```bash
ngrok http 8000
# Copy the https://xxxx.ngrok-free.app URL
```

### Step 2 — Buy a Twilio number and wire the webhook (one-time)

```bash
uv run python scripts/setup_twilio.py --ngrok-url https://xxxx.ngrok-free.app
```

Output:
```
Purchasing +1XXXXXXXXXX …
  Purchased: +1XXXXXXXXXX
  Webhook set to: https://xxxx.ngrok-free.app/voice
```

If you already own a number and just need to update the webhook after ngrok restarts:
```bash
uv run python scripts/setup_twilio.py --ngrok-url https://new-url.ngrok-free.app --update-only
```

### Step 3 — Start the server

```bash
uv run samva-serve --public-host xxxx.ngrok-free.app
```

### Step 4 — Call the number

Dial the Twilio number from your phone. You'll hear the agent greet you. Ask anything — it searches the KB and responds in real time.

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *(required)* | Google AI Studio API key |
| `SAMVA_LIVE_MODEL` | `gemini-3.1-flash-live-preview` | Gemini Live model for conversation |
| `SAMVA_SEARCH_MODEL` | `gemini-2.0-flash` | Model used for File Search RAG queries |
| `SAMVA_KB_STORE_NAME` | `samva-knowledge-base` | File Search store display name |
| `SAMVA_VOICE` | `Kore` | Agent voice |
| `SAMVA_SYSTEM_PROMPT` | *(see config.py)* | System instructions for the agent |
| `SAMVA_PUBLIC_HOST` | `localhost:8000` | Public host for TwiML stream URL |
| `TWILIO_ACCOUNT_SID` | — | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | — | Twilio auth token |

### Available Voices

| Voice | Style |
|-------|-------|
| `Kore` | Neutral, clear (default) |
| `Puck` | Upbeat |
| `Charon` | Informative |
| `Fenrir` | Excitable |
| `Aoede` | Breezy |

---

## How the Audio Bridge Works

Twilio and Gemini use incompatible audio formats. `audio_conv.py` converts between them on every chunk:

```
Twilio in:   base64( µ-law, 8kHz, 8-bit )
                ↓  base64.b64decode
                ↓  audioop.ulaw2lin(2)      → PCM 16-bit @ 8kHz
                ↓  audioop.ratecv(8k→16k)   → PCM 16-bit @ 16kHz
Gemini in:   raw bytes, PCM 16kHz 16-bit

Gemini out:  raw bytes, PCM 24kHz 16-bit
                ↓  audioop.ratecv(24k→8k)   → PCM 16-bit @ 8kHz
                ↓  audioop.lin2ulaw(2)       → µ-law 8-bit @ 8kHz
                ↓  base64.b64encode
Twilio out:  base64( µ-law, 8kHz, 8-bit )
```

The converter is stateful — it maintains `audioop.ratecv` filter state across chunks for smooth resampling without artefacts.

---

## How the KB Tool Call Works

The Live model has one tool declared: `search_knowledge_base(query: str)`.

When the caller asks something domain-specific, the model emits a tool call. The session handler:
1. Sends `"One moment please."` as text input so Gemini speaks a hold phrase
2. Calls `KnowledgeBaseManager.search()` which runs `generate_content` with the `file_search` tool against your store
3. Returns the RAG answer as a `FunctionResponse`
4. Gemini speaks the grounded answer

The search has a **10-second timeout** — if the model is overloaded it falls back to general knowledge and the call continues.

---

## Issues We Hit and Fixed

| Problem | Cause | Fix |
|---------|-------|-----|
| `AttributeError: result` on upload | `UploadToFileSearchStoreOperation` has no `.result()` | Poll with `client.operations.get(op)` until `op.done` |
| Call connects but drops immediately | `"LOW"` is not a valid `EndSensitivity` value | Use `types.EndSensitivity.END_SENSITIVITY_LOW` |
| Agent speaks but ignores caller | Both inbound + outbound Twilio tracks were sent to Gemini | Filter to `track == "inbound"` only |
| Audio queue fills, drops all speech | `put_nowait` with maxsize=300 filled during agent output | Unbounded `asyncio.Queue()` with blocking `await put()` |
| 42-second KB search kills the call | `gemini-3-flash-preview` preview model overloaded | Switch search model to `gemini-2.0-flash` + 10s timeout |
| Caller hears silence during KB search | No feedback while waiting for RAG result | Inject `"One moment please."` text before search starts |

---

## Supported File Types for Knowledge Base

PDF · DOCX · XLSX · PPTX · TXT · MD · JSON · YAML · CSV · HTML · XML · Python · JavaScript · TypeScript · Java · Go · Rust · C/C++ · Shell · and 80+ more formats via Gemini File Search.

---

## Dependencies

```toml
google-genai    # Gemini Live API + File Search
pyaudio         # Mic/speaker I/O (local mode)
fastapi         # Async HTTP + WebSocket server
uvicorn         # ASGI server
twilio          # Twilio REST SDK
python-dotenv   # .env loading
rich            # Terminal UI
audioop-lts     # audioop backport for Python 3.13+
```
