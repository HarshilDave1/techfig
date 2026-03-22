# TechFig Web Demo — Deployment Plan

> **Architecture:** Juno (ICP static frontend) + Railway (Python FastAPI backend)
> **Goal:** A public demo site where non-coding scientists can try TechFig via a chat-like interface, see generated graphics in a preview panel, and download results.

---

## Critical Analysis

### Is a static site okay?

**Yes — with one caveat.** "Static" on Juno means no server-side rendering; the HTML/JS/CSS is served from the ICP blockchain as-is. But JavaScript in the browser can still make API calls to Railway. This is how most modern SPAs work (React, Vue apps on Vercel are "static" in exactly the same way). The chat interface, preview window, and download buttons all work perfectly as client-side JavaScript.

**The caveat:** There's no server-side session management on Juno. Each generation request is stateless — the browser sends a prompt, Railway returns an SVG. This is actually fine for a demo; you don't need persistent chat history server-side. Chat history lives in the browser's memory (or localStorage) for the duration of the session.

### What the user actually experiences

```
┌─────────────────────────────────────────────────────┐
│  TechFig Demo                               [Logo]  │
│─────────────────────────────────────────────────────│
│                                                     │
│  ┌─ Chat Panel ──────┐  ┌─ Preview Panel ────────┐ │
│  │                    │  │                        │ │
│  │  You: "Draw an    │  │   ┌────┐    ┌────┐    │ │
│  │   optical bench    │  │   │Laser│───▶│Lens│   │ │
│  │   with laser,      │  │   └────┘    └────┘    │ │
│  │   lens, and        │  │                │      │ │
│  │   detector"        │  │            ┌────┐    │ │
│  │                    │  │            │ CCD │    │ │
│  │  TechFig: ✓ Done!  │  │            └────┘    │ │
│  │                    │  │                        │ │
│  │  [Download SVG]    │  │  [Download SVG] [PNG]  │ │
│  │  [Download PNG]    │  │                        │ │
│  └────────────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### Cost analysis (personal funds)

| Component | Cost | Notes |
|---|---|---|
| **Juno (ICP)** | ~$0/mo | Free tier covers static serving for demo traffic |
| **Railway** | ~$0–5/mo | $5 credit on starter plan; pure Python calls are cheap (~10ms CPU each) |
| **Venice text** (chat → diagram) | ~$0.001–0.01/call | Qwen3 VL 30B: $0.25/$0.90 per 1M tokens |
| **Venice vision** (sketch → diagram) | ~$0.01–0.03/call | Qwen 2.5VL 72B for image understanding |
| **Venice image gen** (pretty render) | ~$0.10–0.29/call | Flux 2 Max ($0.09) or Recraft V4 Pro ($0.29) |

> [!NOTE]
> **Why Venice, not Google Cloud?** The $1k Google Cloud "GenAI App Builder" credits [cannot be used for standard Gemini API calls](https://www.reddit.com/r/googlecloud/comments/1ldj0uf/). They only work with the enterprise RAG service, not direct model inference. Venice AI is the better fit:
> - **Privacy-first** — no data logging, aligns perfectly with the ICP/Juno decentralized philosophy
> - **OpenAI-compatible API** — works with `litellm` out of the box (just change the model string)
> - **Vision + text + image gen** all from one provider
> - **Diem credits** (1 Diem = $1 of API inference) — pay-as-you-go or stake VVV tokens

**Budget math:** Venice Pro ($18/mo) includes 1,000 Diem credits. At ~$0.01/call average, that's ~100,000 text calls. Pure Python endpoints cost nothing.

> [!IMPORTANT]
> **Credit protection strategy:** Rate limit AI endpoints to 5 requests/minute per IP. Pure Python endpoints (templates, diagrams from spec) are unlimited.

### Security concerns

1. **CORS** — Railway API must whitelist the Juno domain only
2. **Rate limiting** — Without it, someone could abuse the API and run up Railway bills. Simple: 10 requests/minute per IP
3. **Input validation** — The `validate_spec()` function already exists; reuse it
4. **No file system exposure** — Railway generates SVGs in memory, returns them as strings, never writes to disk
5. **No API key exposure** — Browser never sees any secrets; keys live on Railway

---

## Architecture

```
User's Browser
    │
    │  1. Text prompt:   POST /api/chat    → LLM → JSON spec → SVG
    │  2. Image upload:  POST /api/sketch  → LLM Vision → JSON spec → SVG
    │  3. Template pick: POST /api/reconstruct → (no LLM) → SVG
    │
    ├───────────────────────────────────────────┐
    │                                           ▼
Juno Satellite (ICP)                    Railway (Python + FastAPI)
├── index.html                          ├── main.py
├── app.js (chat UI + image upload)     │   ├── /api/chat        (LLM: Venice text)
├── style.css                           │   ├── /api/sketch      (LLM: Venice vision)
└── assets/                             │   ├── /api/reconstruct (pure Python)
                                        │   ├── /api/diagram     (pure Python)
                                        │   ├── /api/chart       (pure Python)
                                        │   └── /api/templates   (static JSON)
                                        ├── techfig/  (engine code)
                                        └── Procfile
```

**Key design decisions:**
- Browser calls Railway directly — no Juno serverless functions needed (simpler, cheaper, lower latency)
- LLM calls happen server-side on Railway; Venice API key is an env var, never exposed to browser
- **Full privacy stack:** ICP blockchain frontend (no centralized host) + Venice API (no data logging) = zero data retention anywhere
- TechFig already uses `litellm` which routes to Venice (OpenAI-compatible) via `openai/model-name` with a custom `api_base`

---

## Phase 1: Deliverables

### 1. FastAPI Backend (Railway)

**New file:** `web/api/main.py`

#### Free Tier Endpoints (no LLM, unlimited)

| Endpoint | Method | Input | Output |
|---|---|---|---|
| `POST /api/diagram` | POST | JSON diagram spec (elements + connections) | SVG string |
| `POST /api/chart` | POST | JSON data + chart_type + style | SVG string (base64) |
| `POST /api/reconstruct` | POST | JSON spec from template picker | SVG string |
| `GET /api/templates` | GET | — | List of built-in template specs |
| `GET /api/styles` | GET | — | List of style presets |
| `GET /api/health` | GET | — | `{ "status": "ok" }` |

#### AI-Powered Endpoints (LLM, rate-limited: 5 req/min per IP)

| Endpoint | Method | Input | Output | LLM |
|---|---|---|---|---|
| `POST /api/chat` | POST | `{ "message": "Draw an optical bench..." }` | JSON spec + SVG string | Venice (Qwen3 VL 30B) |
| `POST /api/sketch` | POST | multipart form: image file + optional description | JSON spec + SVG string | Venice (Qwen 2.5VL 72B) |

**How `/api/chat` works:**
1. User types natural language ("Draw an optical bench with laser, lens, and detector")
2. FastAPI sends the message + TechFig's `SKETCH_PROMPT` to Venice via `litellm` (OpenAI-compatible endpoint)
3. Venice returns a JSON diagram spec
4. FastAPI validates it with `validate_spec()`, renders SVG with `render_from_spec()`
5. Returns both the spec (for further editing) and the SVG string to the browser

**How `/api/sketch` works:**
1. User uploads a photo of a whiteboard sketch
2. FastAPI encodes it as base64, sends to Venice vision model with the `SKETCH_PROMPT`
3. Same flow as above: JSON spec → validate → render → return SVG

**`litellm` config for Venice** (env vars on Railway):
```
VENICE_API_KEY=your_key
VENICE_API_BASE=https://api.venice.ai/api/v1
```
Model strings: `openai/qwen3-vl-30b-a3b` (text+vision), `openai/qwen-2.5-vl-72b` (vision)

All endpoints return the SVG as a string in the JSON response. The browser renders it inline. Downloads use a Blob URL.

**New file:** `web/api/requirements.txt` — Stripped-down dependencies (no `mcp`, no `manim`, no `playwright`), plus `litellm` for LLM calls

**New file:** `web/api/Procfile` — `web: uvicorn main:app --host 0.0.0.0 --port ${PORT}`

### 2. Static Frontend (Juno)

**New directory:** `web/frontend/`

| File | Purpose |
|---|---|
| `index.html` | Landing page + demo section |
| `style.css` | Design system (dark mode, glassmorphism, vibrant gradients) |
| `app.js` | Chat interface logic, API calls, SVG preview, download handlers |
| `templates.js` | Built-in demo templates (optical bench, cell diagram, etc.) |

**Features:**

- **Chat panel** (left): User types natural language descriptions → LLM generates diagram. Messages appear conversationally with loading states
- **Image upload**: Drag-and-drop or click to upload a sketch photo → LLM vision reconstructs it as SVG
- **Preview panel** (right): Renders the generated SVG inline; pinch-to-zoom, dark/light toggle
- **Template gallery**: 3–5 pre-built specs the user can "try now" with one click (optical bench, flowchart, circuit schematic) — these use the free pure-Python endpoint
- **Edit & re-generate**: After the LLM returns a spec, user can say "make the boxes blue" or "add a detector" and the LLM refines the existing spec
- **Download buttons**: SVG, PNG (converted client-side via canvas)
- **Style picker**: Toggle between `nature`, `science`, `dark`, `minimal` styles
- **Mobile responsive**: Stack panels vertically on small screens

### 3. Configuration & Deploy

**New file:** `web/api/railway.json` — Railway deploy config
**New file:** `web/frontend/juno.config.ts` — Juno satellite config

---

## Deferred to Phase 2

- Pretty rendering via Venice image gen (Flux 2 Max at $0.09/img or Recraft V4 Pro at $0.29/img)
- Juno serverless functions (HTTPS outcalls to Railway for fully on-chain pipeline)
- User accounts / saved diagrams (Juno Datastore)
- PPTX generation + download (binary file handling is more complex)

---

## Directory Structure

```
web/
├── api/                      # → deploys to Railway
│   ├── main.py               # FastAPI app
│   ├── requirements.txt      # Stripped deps
│   ├── Procfile
│   └── railway.json
│
└── frontend/                 # → deploys to Juno
    ├── index.html
    ├── style.css
    ├── app.js
    └── templates.js
```

The `web/api/` directory imports from `techfig` — which means we either:
- **(A)** Copy the `techfig/` package into `web/api/` for isolated Railway deploy, or
- **(B)** Deploy the entire repo to Railway and just point at `web/api/main.py`

**Recommendation:** Option B. Railway can deploy the whole repo; we just set the start command to `cd web/api && uvicorn main:app`. This way the `techfig` package stays in sync automatically.

---

## Verification Plan

### Automated Tests

1. **Backend API tests** — Run the existing test suite to make sure nothing is broken:
   ```bash
   cd /Users/lobby/Documents/agent-zero/projects/graphic_agent
   python -m pytest tests/test_diagrams.py tests/test_figures.py tests/test_sketch_interpreter.py -v
   ```

2. **API endpoint tests** — Start the FastAPI server locally and test each endpoint:
   ```bash
   cd /Users/lobby/Documents/agent-zero/projects/graphic_agent
   python -m uvicorn web.api.main:app --port 8000 &
   # Test health
   curl http://localhost:8000/api/health
   # Test diagram generation
   curl -X POST http://localhost:8000/api/diagram \
     -H "Content-Type: application/json" \
     -d '{"elements":[{"type":"box","id":"a","x":0,"y":0,"text":"Hello"}],"connections":[]}'
   # Test template listing
   curl http://localhost:8000/api/templates
   ```

3. **AI endpoint tests** — Test the LLM-powered endpoints (requires `VENICE_API_KEY` + `VENICE_API_BASE` env vars):
   ```bash
   # Test chat-to-diagram
   curl -X POST http://localhost:8000/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "Draw a simple flowchart with Start, Process, and End boxes"}'
   # Test sketch upload (use a test image)
   curl -X POST http://localhost:8000/api/sketch \
     -F "image=@tests/fixtures/sample_sketch.png"
   ```

4. **Frontend browser test** — Open the local frontend in a browser and:
   - Click a template → verify SVG renders in preview
   - Type "Draw an optical bench" in chat → verify LLM response + SVG preview
   - Upload a sketch image → verify SVG reconstruction appears
   - Click "Download SVG" → verify file downloads
   - Toggle styles → verify SVG re-renders with new colors

### Manual Verification (for you to do)

1. Deploy backend to Railway (`railway up`)
2. Deploy frontend to Juno (`juno deploy`)
3. Visit the Juno URL, try 2–3 templates, download an SVG, check it opens in Inkscape
4. Test on mobile (responsive layout)
