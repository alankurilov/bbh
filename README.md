# BBH Turn culturally dense long-form video into self-explanatory content—for any audience, automatically.

Powered by Google Deepmind, Tavily, Lovable and Hera

**Live Frontend:** [pixel-perfect-clone-1368.lovable.app](https://pixel-perfect-clone-1368.lovable.app)

---

## The Problem

A political podcaster mentions "the filibuster." A sports commentator references a 1998 World Cup moment. A business analyst name-drops a regional regulator. To local viewers, these are shorthand. To international or younger audiences, they're dead ends.

**Context gaps kill engagement.** Viewers abandon videos when they feel lost, and manual annotation doesn't scale.

---

## The Solution

This pipeline automatically detects ambiguous references in long-form video, generates short visual explainers, and overlays them seamlessly onto the original timeline.

**Three levers of control:**
- **Audience profile:** `informed` · `curious` · `newcomer`
- **Explanation density:** `subtle` (brief popup) · `immersive` (full segment)
- **Zero manual editing:** Fully timestamped, generated, and composited

**What the output looks like:**
> At 04:32, the speaker says *"the CHIPS Act."* The pipeline detects this as a gap for a `newcomer` audience, generates a 6-second animated explainer with a sourced image, removes its green-screen background, and overlays it as a picture-in-picture contextual card. The viewer never leaves the video.

---

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Source Video │────▶│   Gemini     │────▶│  Timestamped │
│ (YT/MP4)     │     │  Multimodal  │     │  Context Gaps│
└──────────────┘     │  Analysis    │     └──────────────┘
                     └──────────────┘            │
                                                  ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Final Video  │◀────│   MoviePy    │◀────│ Transparent  │
│ (Composited) │     │  Overlay     │     │  WebM Clips  │
└──────────────┘     └──────────────┘     └──────────────┘
                                                  ▲
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Tavily Image │────▶│   Hera API   │────▶│ OpenCV       │
│   Search     │     │   Generation │     │ Chroma-Key   │
└──────────────┘     │   + Polling  │     │ Pipeline     │
                     └──────────────┘     └──────────────┘
```

---

## Tech Stack

| Layer | Technology | Why It Was Chosen |
|-------|-----------|-------------------|
| **Backend** | FastAPI | Async-native, auto-generated OpenAPI docs, production-grade |
| **Video Understanding** | Google Gemini 3 Flash (multimodal) | Native video comprehension + structured output for gap detection |
| **Knowledge Retrieval** | Tavily | Intelligent web search with automatic first-image ranking |
| **Video Generation** | Hera API | Template-driven motion graphics from text inputs |
| **Matting** | Custom OpenCV/ImageIO pipeline | Lightweight, server-side chroma-key without third-party SaaS costs |
| **Compositing** | MoviePy | Frame-accurate timeline overlays with alpha channel support |
| **Frontend** | Lovable | Separate no-code interface for job orchestration and preview |

---

## API Reference

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check + version metadata |

### Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/analyze-video` | Ingest a YouTube URL or uploaded MP4. Returns structured context gaps with `title`, `explanation_text`, and `interval` (start/end seconds), filtered by the requested audience profile and density. |

### Asset Production
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/search-image` | Intelligent image retrieval. Returns the highest-relevance image URL for a given query (e.g., *"CHIPS Act semiconductor factory"*) via Tavily. |
| `POST` | `/generate-video` | Submit a template-driven prompt to Hera (`title`, `body_text`, `duration`, `image_url`, brand colors). Returns a `video_id`. |
| `GET` | `/generate-video/{video_id}` | Poll for generation status. Returns `status` (`pending` \| `processing` \| `done`) and `output_url` when complete. |
| `POST` | `/remove-background` | Upload a generated clip (green-screen). Returns a transparent WebM with alpha channel, ready for compositing. |

### Composition
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/compose-overlay` | Accepts a background video + array of transparent clips with timestamp intervals. Returns the final composited video. |

### Orchestration
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/pipeline-prototype` | **Synchronous** end-to-end run. Useful for demos and testing. Returns `final_video_url` + full diagnostics trace. |
| `POST` | `/pipeline-jobs` | **Asynchronous** production entrypoint. Starts background job, immediately returns `job_id`. |
| `GET` | `/pipeline-jobs/{job_id}` | Poll for live progress. Returns current `stage`, `progress_pct`, per-stage diagnostics, and final `result` when done. |

**Production polling stages:** `analyzing` → `search_generate` → `poll_generation` → `remove_background` → `compose` → `done`

---

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `GEMINI_API_KEY` | Yes | — | Multimodal video analysis |
| `HERA_API_KEY` | Yes | — | Explainer clip generation |
| `TAVILY_API_KEY` | Yes | — | Contextual image search |
| `GEMINI_MODEL` | No | `gemini-3-flash-preview` | Model version override |
| `MAX_VIDEO_MB` | No | — | Upload size limit |
| `YTDLP_COOKIES_TXT_B64` / `YTDLP_COOKIES_TXT` | No | — | YouTube anti-bot bypass (base64 or raw path) |

---

## Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Run with hot-reload
uvicorn main:app --host 127.0.0.1 --port 8000 --env-file .env --reload
```

**Interactive docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Deployment

**Railway-ready** out of the box:
- `Dockerfile` included
- `railway.toml` pre-configured

**Production hardening checklist:**
- [ ] Replace in-memory job state with **Redis** (or Postgres) for horizontal scaling
- [ ] Move local disk media to **S3 / R2 / GCS** with presigned URLs
- [ ] Add rate limiting per `job_id` on polling endpoints
- [ ] Implement webhook callbacks from `/pipeline-jobs` instead of pure polling
- [ ] Add structured logging (JSON) and distributed tracing per pipeline stage

---

## Frontend Integration (Lovable)

The Lovable frontend is designed to treat this API as a managed video-rendering backend:

1. **Start:** `POST /pipeline-jobs` with the source URL and audience config
2. **Poll:** `GET /pipeline-jobs/{job_id}` every 2–3 seconds
3. **Animate:** Map `stage` names to branded loading states (e.g., "Analyzing context…" → "Generating visuals…" → "Compositing timeline…")
4. **Deliver:** Display the final player with `result.final_video_url`

---
