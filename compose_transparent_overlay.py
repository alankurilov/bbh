"""Compose a transparent foreground video on top of a background video using MoviePy."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from moviepy import CompositeVideoClip, VideoFileClip


def _parse_timestamp_to_seconds(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid timestamp '{value}'. Expected HH:MM:SS.")
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp '{value}'. Expected HH:MM:SS with integers.") from exc

    if hours < 0 or minutes < 0 or seconds < 0:
        raise ValueError(f"Invalid timestamp '{value}'. Values must be non-negative.")
    if minutes > 59 or seconds > 59:
        raise ValueError(f"Invalid timestamp '{value}'. MM and SS must be between 00 and 59.")

    return float(hours * 3600 + minutes * 60 + seconds)


@dataclass
class ForegroundOverlay:
    foreground_video_path: str | Path
    start_time: str
    end_time: str | None = None


def _build_foreground_clip(
    foreground_video_path: str | Path,
    background_size: tuple[int, int],
    *,
    scale: float,
    start_time: str,
    end_time: str | None,
    match_background_size: bool,
) -> VideoFileClip:
    foreground = VideoFileClip(str(Path(foreground_video_path)), has_mask=True)
    start_seconds = _parse_timestamp_to_seconds(start_time)
    end_seconds = _parse_timestamp_to_seconds(end_time) if end_time is not None else None

    if start_seconds < 0:
        raise ValueError("start_time must be >= 0")
    if end_seconds is not None and end_seconds <= start_seconds:
        raise ValueError("end_time must be greater than start_time")

    if match_background_size:
        foreground = foreground.resized(background_size)
    elif scale != 1.0:
        foreground = foreground.resized(scale)

    if end_seconds is not None:
        window_duration = end_seconds - start_seconds
        fg_duration = min(foreground.duration, window_duration)
        foreground = foreground.subclipped(0, fg_duration)

    return foreground.with_start(start_seconds).with_position((0, 0))


def overlay_non_transparent_part(
    background_video_path: str | Path,
    foreground_video_path: str | Path,
    output_path: str | Path,
    *,
    scale: float = 1.0,
    start_time: str = "00:00:00",
    end_time: str | None = None,
    match_background_size: bool = True,
) -> str:
    """
    Overlay a transparent foreground clip over a background clip.

    The foreground's alpha channel is respected automatically, so only the
    non-transparent portion is drawn on top of the background.
    """
    bg_path = str(Path(background_video_path))
    fg_path = str(Path(foreground_video_path))
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    background = VideoFileClip(bg_path)
    if scale <= 0:
        raise ValueError("scale must be > 0")
    foreground = _build_foreground_clip(
        foreground_video_path=fg_path,
        background_size=background.size,
        scale=scale,
        start_time=start_time,
        end_time=end_time,
        match_background_size=match_background_size,
    )

    final_duration = background.duration
    composite = CompositeVideoClip([background, foreground], size=background.size).with_duration(final_duration)

    composite.write_videofile(
        str(out_path),
        codec="libx264",
        audio_codec="aac",
        fps=background.fps or 24,
        preset="medium",
    )

    background.close()
    foreground.close()
    composite.close()
    return str(out_path.resolve())


def overlay_multiple_non_transparent_parts(
    background_video_path: str | Path,
    overlays: list[ForegroundOverlay],
    output_path: str | Path,
    *,
    scale: float = 1.0,
    match_background_size: bool = True,
) -> str:
    """Overlay multiple transparent foreground clips over one background clip."""
    if not overlays:
        raise ValueError("At least one foreground overlay is required.")
    if scale <= 0:
        raise ValueError("scale must be > 0")

    background = VideoFileClip(str(Path(background_video_path)))
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    foreground_clips = []
    try:
        for overlay in overlays:
            clip = _build_foreground_clip(
                foreground_video_path=overlay.foreground_video_path,
                background_size=background.size,
                scale=scale,
                start_time=overlay.start_time,
                end_time=overlay.end_time,
                match_background_size=match_background_size,
            )
            foreground_clips.append(clip)

        composite = CompositeVideoClip([background, *foreground_clips], size=background.size).with_duration(background.duration)
        composite.write_videofile(
            str(out_path),
            codec="libx264",
            audio_codec="aac",
            fps=background.fps or 24,
            preset="medium",
        )
        composite.close()
    finally:
        for clip in foreground_clips:
            clip.close()
        background.close()

    return str(out_path.resolve())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Overlay transparent foreground video over background video.")
    parser.add_argument("--background", required=True, help="Path to background/base video.")
    parser.add_argument("--foreground", required=True, help="Path to transparent foreground video (e.g. webm with alpha).")
    parser.add_argument("--output", required=True, help="Path to output composed video.")
    parser.add_argument("--scale", type=float, default=1.0, help="Optional scale used only when --no-match-background-size is set.")
    parser.add_argument(
        "--match-background-size",
        action="store_true",
        default=True,
        help="Resize foreground to exactly background dimensions (default: enabled).",
    )
    parser.add_argument(
        "--no-match-background-size",
        dest="match_background_size",
        action="store_false",
        help="Keep original foreground dimensions instead of matching background size.",
    )
    parser.add_argument(
        "--start",
        type=str,
        default="00:00:00",
        help="Foreground start timestamp on background timeline (HH:MM:SS).",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="Optional foreground end timestamp on background timeline (HH:MM:SS).",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    output = overlay_non_transparent_part(
        background_video_path=args.background,
        foreground_video_path=args.foreground,
        output_path=args.output,
        scale=args.scale,
        start_time=args.start,
        end_time=args.end,
        match_background_size=args.match_background_size,
    )
    print(f"Done: {output}")


if __name__ == "__main__":
    main()
