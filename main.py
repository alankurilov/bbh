import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv()
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Video Explanation Gap Analyzer",
    description="Analyze a YouTube link or MP4 file and find video segments with concepts not fully explained.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 🔥 allow all (for development)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GapSegment(BaseModel):
    title: str = Field(..., description="Short segment title")
    content: str = Field(..., description="What is not explained in this segment")
    start_timestamp: str = Field(..., description="Timestamp where the gap starts. Format HH:MM:SS")
    end_timestamp: str = Field(..., description="Timestamp where the gap ends. Format HH:MM:SS")


class AnalysisResponse(BaseModel):
    video_title: str
    gaps: list[GapSegment]


ViewerProfile = Literal["informed", "curious", "newcomer"]
CaptionDensity = Literal["subtle", "immersive"]


def _profile_instruction(viewer_profile: ViewerProfile) -> str:
    if viewer_profile == "informed":
        return "Audience already knows most U.S. political context. Flag only advanced or niche unexplained references."
    if viewer_profile == "curious":
        return "Audience has moderate context. Flag references that are not broadly known internationally."
    return "Audience is new to U.S. context. Flag references that likely need quick explanation for international viewers."


def _density_instruction(caption_density: CaptionDensity) -> str:
    if caption_density == "subtle":
        return "Keep output concise. Include only top missing references, ideally around one per minute."
    return "Be more comprehensive. Include most meaningful unexplained references while avoiding trivial items."


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
""".strip()


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