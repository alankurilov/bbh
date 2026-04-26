import os
import uuid
import json
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv()
from fastapi.middleware.cors import CORSMiddleware

from compose_transparent_overlay import ForegroundOverlay, overlay_multiple_non_transparent_parts
from remove_background import remove_background_video
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(
    title="Video Explanation Gap Analyzer",
    description="Analyze a YouTube link or MP4 file and find video segments with concepts not fully explained.",
)
<<<<<<< HEAD
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 🔥 allow all (for development)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
=======

MEDIA_DIR = Path("media")
UPLOADS_DIR = MEDIA_DIR / "uploads"
OUTPUTS_DIR = MEDIA_DIR / "outputs"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
HERA_PROMPT_TEMPLATE_PATH = Path(__file__).with_name("PROMPT_HERA.md")

>>>>>>> d8abb51178a69fc50d28f771398f280004f252a9

class GapSegment(BaseModel):
    title: str = Field(..., description="Short segment title")
    content: str = Field(..., description="What is not explained in this segment")
    start_timestamp: str = Field(..., description="Timestamp where the gap starts. Format HH:MM:SS")
    end_timestamp: str = Field(..., description="Timestamp where the gap ends. Format HH:MM:SS")


class AnalysisResponse(BaseModel):
    video_title: str
    gaps: list[GapSegment]


class BackgroundRemovalResponse(BaseModel):
    output_video_url: str
    output_video_path: str


class HeraVideoCreateResponse(BaseModel):
    video_id: str
    project_url: str | None = None


class HeraVideoStatusResponse(BaseModel):
    status: str
    video_id: str | None = None
    video_url: str | None = None
    response: dict | None = None


class ComposeIntervalItem(BaseModel):
    foreground_video_url: str
    start_timestamp: str = Field(..., description="Start timestamp in HH:MM:SS")
    end_timestamp: str | None = Field(default=None, description="Optional end timestamp in HH:MM:SS")


class ComposeOverlayRequest(BaseModel):
    background_video_url: str
    overlays: list[ComposeIntervalItem]


class ComposeOverlayResponse(BaseModel):
    output_video_url: str
    output_video_path: str


ViewerProfile = Literal["informed", "curious", "newcomer"]
CaptionDensity = Literal["subtle", "immersive"]


def _profile_instruction(viewer_profile: ViewerProfile) -> str:
    if viewer_profile == "informed":
        return (
            "Knowledge baseline: follows major U.S. political actors/institutions and headline events.\n"
            "Include only high-value gaps: niche people, acronyms, process details, or historical references that block deep understanding.\n"
            "Do NOT include obvious basics (president, congress, Democrats vs Republicans)."
        )
    if viewer_profile == "curious":
        return (
            "Knowledge baseline: recognizes common U.S. political terms but misses insider context.\n"
            "Include medium/high-impact gaps: policy acronyms, non-obvious public figures, institutions, and events assumed by speakers.\n"
            "Skip very basic civics unless the reference is used in a specialized way."
        )
    return (
        "Knowledge baseline: little U.S. political context; likely international newcomer.\n"
        "Include any reference that is required to follow the conversation: people, acronyms, media brands, institutions, election mechanics, key events.\n"
        "Prefer clear plain-language explanations over insider jargon."
    )


def _density_instruction(caption_density: CaptionDensity) -> str:
    if caption_density == "subtle":
        return (
            "Selection policy: high precision only.\n"
            "Return only the most important gaps (roughly 1 meaningful gap per 60-120s of discussion).\n"
            "Merge repeated references into one interval and avoid near-duplicates."
        )
    return (
        "Selection policy: high recall with quality control.\n"
        "Return most meaningful gaps (roughly 1 meaningful gap per 20-45s when references are dense).\n"
        "Include secondary references if they improve comprehension, but still avoid trivial/name-only mentions."
    )


def _global_quality_criteria() -> str:
    return """
Quality criteria for identifying a "not explained" gap:
1) Dependency test: Without this explanation, an international viewer would miss the point or implication.
2) Explanation test: The speaker does not define it clearly in the nearby context.
3) Specificity test: The missing context can be explained concretely in 1-2 sentences.
4) Impact test: Prioritize references that affect interpretation, argument strength, or factual understanding.

Timestamp and dedup rules:
- Use precise intervals where the unexplained reference is introduced/discussed.
- If a reference repeats throughout the video, keep the earliest high-signal interval unless a later segment adds a new unexplained angle.
- Avoid overlapping intervals unless two distinct gaps truly co-occur.

Content writing rules:
- title: short noun phrase (who/what is missing).
- content: explain what it is + why that context matters in this discussion.
- Do not invent facts; if uncertain, keep wording cautious.
""".strip()


def _build_analysis_prompt(viewer_profile: ViewerProfile, caption_density: CaptionDensity) -> str:
    return f"""
You are analyzing a video for explanation gaps.
Find intervals where a concept, idea, person, or reference appears but is not clearly explained.

Rules:
- Keep title concise and specific.
- content must explain the missing explanation.
- Timestamps must match the real interval.
- If no gaps, return "gaps": [].
- Viewer profile: {viewer_profile}
- Profile guidance: {_profile_instruction(viewer_profile)}
- Caption density: {caption_density}
- Density guidance: {_density_instruction(caption_density)}
- Apply this global rubric exactly:
{_global_quality_criteria()}
""".strip()


def _download_url_to_path(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to download URL '{url}': {exc.reason}") from exc

    if not data:
        raise HTTPException(status_code=400, detail=f"Downloaded file is empty: {url}")
    destination.write_bytes(data)
    return destination


def _guess_extension_from_url(url: str, fallback: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".mp4", ".webm", ".mov", ".mkv"}:
        return suffix
    return fallback


def _build_hera_prompt(title: str, body_text: str, seconds: int) -> str:
    if not HERA_PROMPT_TEMPLATE_PATH.exists():
        raise HTTPException(status_code=500, detail="Missing PROMPT_HERA.md template file.")

    template = HERA_PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    required_placeholders = {"{{TITLE}}", "{{BODY_TEXT}}", "{{SECONDS}}"}
    missing = [token for token in required_placeholders if token not in template]
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"PROMPT_HERA.md is missing placeholders: {', '.join(missing)}",
        )

    prompt = (
        template.replace("{{TITLE}}", title)
        .replace("{{BODY_TEXT}}", body_text)
        .replace("{{SECONDS}}", str(seconds))
    )
    return prompt


def _run_gemini_analysis(
    video_part: types.Part,
    fallback_video_title: str,
    viewer_profile: ViewerProfile,
    caption_density: CaptionDensity,
) -> AnalysisResponse:
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Missing GEMINI_API_KEY environment variable.",
        )

    client = genai.Client(api_key=api_key)

    prompt = _build_analysis_prompt(viewer_profile=viewer_profile, caption_density=caption_density)
    response = client.models.generate_content(
        model=model_name,
        contents=[prompt, video_part],
        config={
            "response_mime_type": "application/json",
            "response_json_schema": AnalysisResponse.model_json_schema(),
        },
    )
    if not getattr(response, "text", None):
        raise HTTPException(status_code=502, detail="Gemini returned an empty response.")

    try:
        result = AnalysisResponse.model_validate_json(response.text)
        if not result.video_title:
            result.video_title = fallback_video_title
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini JSON schema validation failed: {exc}",
        ) from exc


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Video analyzer is running"}


@app.post("/analyze-video", response_model=AnalysisResponse)
async def analyze_video(
    youtube_url: str | None = Form(default=None),
    video_url: str | None = Form(default=None),
    video_file: UploadFile | None = File(default=None),
    viewer_profile: ViewerProfile = Form(default="newcomer"),
    caption_density: CaptionDensity = Form(default="subtle"),
) -> AnalysisResponse:
    provided_urls = [url for url in [youtube_url, video_url] if url]
    if len(provided_urls) > 1:
        raise HTTPException(
            status_code=400,
            detail="Provide only one URL field: youtube_url or video_url.",
        )
    source_url = provided_urls[0] if provided_urls else None

    if bool(source_url) == bool(video_file):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one video input: URL (youtube_url/video_url) or video_file.",
        )

    if source_url:
        video_part = types.Part(
            file_data=types.FileData(file_uri=source_url),
        )
        return _run_gemini_analysis(
            video_part=video_part,
            fallback_video_title="youtube-video",
            viewer_profile=viewer_profile,
            caption_density=caption_density,
        )

    if video_file is None:
        raise HTTPException(status_code=400, detail="video_file is required.")
    if video_file.content_type != "video/mp4":
        raise HTTPException(status_code=400, detail="Only MP4 file uploads are supported.")

    content = await video_file.read()
    max_mb = int(os.getenv("MAX_VIDEO_MB", "50"))
    max_bytes = max_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded file too large ({len(content) // (1024 * 1024)} MB). Maximum is {max_mb} MB.",
        )

    video_part = types.Part.from_bytes(data=content, mime_type="video/mp4")
    video_title = Path(video_file.filename or "uploaded-video.mp4").stem
    return _run_gemini_analysis(
        video_part=video_part,
        fallback_video_title=video_title,
        viewer_profile=viewer_profile,
        caption_density=caption_density,
    )
@app.post("/find_image")
def find_image(image_description: str):
    query = f"{image_description} {gap.content[:120]} reference image explanation"
    response = clientTavily.search(
        query=query,
        search_depth="advanced",
        include_images=True,
        max_results=5,
    )

    images = response.get("images", [])

    if not images:
        raise HTTPException(status_code=404, detail="No image found")

    return {"image": images[0]}

@app.post("/remove-background", response_model=BackgroundRemovalResponse)
async def remove_background_endpoint(
    request: Request,
    video_file: UploadFile = File(...),
) -> BackgroundRemovalResponse:
    if video_file.content_type not in {"video/mp4", "video/webm", "video/quicktime"}:
        raise HTTPException(status_code=400, detail="Supported formats: mp4, webm, mov.")

    suffix = Path(video_file.filename or "video.mp4").suffix or ".mp4"
    input_name = f"{uuid.uuid4().hex}{suffix}"
    output_name = f"{Path(input_name).stem}_transparent.webm"
    input_path = UPLOADS_DIR / input_name
    output_path = OUTPUTS_DIR / output_name

    content = await video_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    input_path.write_bytes(content)

    try:
        await run_in_threadpool(
            remove_background_video,
            str(input_path),
            str(output_path),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Background removal failed: {exc}") from exc

    output_url = str(request.base_url).rstrip("/") + f"/media/outputs/{output_name}"
    return BackgroundRemovalResponse(
        output_video_url=output_url,
        output_video_path=str(output_path.resolve()),
    )


@app.post("/generate-video", response_model=HeraVideoCreateResponse)
async def generate_video_with_hera(
    title: str = Form(...),
    body_text: str = Form(...),
    seconds: int = Form(...),
    asset_image_url: str = Form(...),
) -> HeraVideoCreateResponse:
    hera_api_key = os.getenv("HERA_API_KEY") 
    if not hera_api_key:
        raise HTTPException(status_code=500, detail="Missing HERA_API_KEY environment variable.")
    if seconds < 1 or seconds > 60:
        raise HTTPException(status_code=400, detail="seconds must be between 1 and 60.")

    prompt = _build_hera_prompt(title=title, body_text=body_text, seconds=seconds)

    payload = {
        "prompt": prompt,
        "assets": [
            {
                "type": "image",
                "url": asset_image_url,
            }
        ],
        "duration_seconds": seconds,
        "outputs": [
            {
                "format": "mp4",
                "aspect_ratio": "16:9",
                "fps": "24",
                "resolution": "1080p",
            }
        ],
    }

    request = urllib.request.Request(
        url="https://api.hera.video/v1/videos",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": hera_api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(
            status_code=502,
            detail=f"Hera API HTTP error {exc.code}: {error_body or exc.reason}",
        ) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Hera API connection error: {exc.reason}") from exc

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid JSON from Hera API: {exc.msg}") from exc

    video_id = parsed.get("video_id")
    if not video_id:
        raise HTTPException(status_code=502, detail="Hera API response missing video_id.")

    return HeraVideoCreateResponse(
        video_id=video_id,
        project_url=parsed.get("project_url"),
    )


@app.get("/generate-video/{video_id}", response_model=HeraVideoStatusResponse)
async def get_generated_video_status(video_id: str) -> HeraVideoStatusResponse:
    hera_api_key = os.getenv("HERA_API_KEY")
    if not hera_api_key:
        raise HTTPException(status_code=500, detail="Missing HERA_API_KEY environment variable.")

    request = urllib.request.Request(
        url=f"https://api.hera.video/v1/videos/{video_id}",
        headers={
            "x-api-key": hera_api_key,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed_error = json.loads(error_body) if error_body else {"error": exc.reason}
        except json.JSONDecodeError:
            parsed_error = {"error": error_body or exc.reason}
        return HeraVideoStatusResponse(
            status="error",
            video_id=video_id,
            response=parsed_error,
        )
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Hera API connection error: {exc.reason}") from exc

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid JSON from Hera API: {exc.msg}") from exc

    status = parsed.get("status")
    if status == "success":
        outputs = parsed.get("outputs", [])
        video_url = None
        for output in outputs:
            if output.get("status") == "success" and output.get("file_url"):
                video_url = output["file_url"]
                break
        if video_url:
            return HeraVideoStatusResponse(
                status="success",
                video_id=parsed.get("video_id", video_id),
                video_url=video_url,
            )
        return HeraVideoStatusResponse(
            status="error",
            video_id=parsed.get("video_id", video_id),
            response=parsed,
        )

    if status == "in-progress":
        return HeraVideoStatusResponse(
            status="in-progress",
            video_id=parsed.get("video_id", video_id),
        )

    # For failed or any unexpected status, return full Hera response.
    return HeraVideoStatusResponse(
        status="error",
        video_id=parsed.get("video_id", video_id),
        response=parsed,
    )


@app.post("/compose-overlay", response_model=ComposeOverlayResponse)
async def compose_overlay_video(
    request: Request,
    payload: ComposeOverlayRequest,
) -> ComposeOverlayResponse:
    if not payload.overlays:
        raise HTTPException(status_code=400, detail="At least one overlay item is required.")

    compose_id = uuid.uuid4().hex
    bg_ext = _guess_extension_from_url(payload.background_video_url, ".mp4")
    background_path = UPLOADS_DIR / f"{compose_id}_background{bg_ext}"
    output_name = f"{compose_id}_composed.mp4"
    output_path = OUTPUTS_DIR / output_name

    _download_url_to_path(payload.background_video_url, background_path)

    overlays: list[ForegroundOverlay] = []
    for index, item in enumerate(payload.overlays):
        fg_ext = _guess_extension_from_url(item.foreground_video_url, ".webm")
        foreground_path = UPLOADS_DIR / f"{compose_id}_fg_{index}{fg_ext}"
        _download_url_to_path(item.foreground_video_url, foreground_path)
        overlays.append(
            ForegroundOverlay(
                foreground_video_path=str(foreground_path),
                start_time=item.start_timestamp,
                end_time=item.end_timestamp,
            )
        )

    try:
        await run_in_threadpool(
            overlay_multiple_non_transparent_parts,
            str(background_path),
            overlays,
            str(output_path),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Overlay composition failed: {exc}") from exc

    output_url = str(request.base_url).rstrip("/") + f"/media/outputs/{output_name}"
    return ComposeOverlayResponse(
        output_video_url=output_url,
        output_video_path=str(output_path.resolve()),
    )