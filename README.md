# BBH Video Context Pipeline API

https://pixel-perfect-clone-1368.lovable.app

FastAPI backend that turns long-form videos into contextual, audience-aware overlays.

This project analyzes a source video, detects references that may be unclear to a target audience, generates short visual explainer clips, removes their green background, and overlays them back on the original video timeline.

---

## Why this project

International audiences often miss local political, cultural, or institutional references in podcasts and commentary videos.  
This API solves that by automatically adding contextual explainer segments at the right timestamps.

Core value:
- Adapts to viewer profile (`informed`, `curious`, `newcomer`)
- Controls explanation density (`subtle`, `immersive`)
- Produces timeline-aligned contextual overlays automatically

---

## Tech stack

- **Backend**: FastAPI
- **LLM / Video understanding**: Google Gemini (multimodal)
- **Image retrieval**: Tavily (intelligent web search, first-image selection)
- **Video generation**: Hera API
- **Background removal**: custom OpenCV/ImageIO chroma-key pipeline
- **Compositing**: MoviePy overlays on source timeline
- **Frontend**: built with **Lovable** (separate repo/app)

---

## High-level pipeline

1. Analyze video with Gemini using viewer profile + density
2. Get timestamped gaps (`title`, short `content`, interval)
3. Search an image per gap with Tavily
4. Generate visual explainer clips with Hera
5. Poll Hera until each clip is ready
6. Remove green background from generated clips
7. Overlay all clips on the source video at gap timestamps
8. Return final video URL + detailed processing metadata

---

## API overview

### Health
- `GET /`  
Basic health check.

### Analysis
- `POST /analyze-video`  
Analyze a YouTube URL or uploaded MP4 and return explanation gaps.

### Image search
- `GET /search-image?query=...`  
Returns first image URL from Tavily results.

### Hera generation
- `POST /generate-video`  
Generate one explainer clip from template-driven prompt inputs (`title`, `body_text`, `seconds`, colors, image URL).
- `GET /generate-video/{video_id}`  
Check Hera generation status and retrieve output URL when ready.

### Background removal
- `POST /remove-background`  
Upload a clip and return transparent WebM output URL.

### Overlay composition
- `POST /compose-overlay`  
Overlay one or multiple transparent clips over a background video using timestamp intervals.

### End-to-end prototype
- `POST /pipeline-prototype`  
Runs full orchestration synchronously and returns final composed video URL + diagnostics.

### Async job orchestration (frontend-friendly)
- `POST /pipeline-jobs`  
Start full pipeline in background, returns `job_id`.
- `GET /pipeline-jobs/{job_id}`  
Returns status/stage/progress + final result when completed.

---

## Environment variables

Required:
- `GEMINI_API_KEY`
- `HERA_API_KEY`
- `TAVILY_API_KEY`

Optional:
- `GEMINI_MODEL` (default `gemini-3-flash-preview`)
- `MAX_VIDEO_MB`
- `YTDLP_COOKIES_TXT_B64` or `YTDLP_COOKIES_TXT` (for YouTube anti-bot protected downloads)

---

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000 --env-file .env --reload
```

Open docs:
- `http://127.0.0.1:8000/docs`

---

## Deployment

Configured for Railway with:
- `Dockerfile`
- `railway.toml`

Recommended production hardening:
- Persist job state in Redis (instead of in-memory)
- Store media in object storage (S3/R2) instead of local disk

---

## Frontend integration (Lovable)

Lovable can:
- Start jobs via `POST /pipeline-jobs`
- Poll progress via `GET /pipeline-jobs/{job_id}`
- Display stage-based loading animations (`analyzing`, `search_generate`, `poll_generation`, `remove_background`, `compose`, `done`)
- Show final output with `result.final_video_url`

