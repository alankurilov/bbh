#!/usr/bin/env python3
"""Advanced chroma key helper for plain green background videos."""

from dataclasses import dataclass
from pathlib import Path

import cv2
import imageio
import numpy as np


@dataclass
class ChromaKeyConfig:
    top_cutoff: float = 0.65
    hue_tol: int = 20
    val_min_top: int = 120
    val_max_bottom: int = 160
    green_dom: int = 40
    crf: int = 20


def detect_green_hue(top_bgr: np.ndarray) -> int:
    hsv = cv2.cvtColor(top_bgr, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 0] > 30) & (hsv[:, :, 0] < 90) & (hsv[:, :, 1] > 40)
    return int(np.median(hsv[:, :, 0][mask])) if mask.any() else 60


def smart_mask(bgr: np.ndarray, green_hue: int, h: int, w: int, config: ChromaKeyConfig) -> np.ndarray:
    """Build a two-zone alpha mask for tricky green-screen and fade-in sections."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = np.zeros((h, w), dtype=np.uint8)
    split = int(h * config.top_cutoff)

    # Top zone: remove bright green aggressively.
    top = cv2.inRange(
        hsv[:split, :],
        (max(0, green_hue - config.hue_tol), 50, config.val_min_top),
        (min(179, green_hue + config.hue_tol), 255, 255),
    )
    mask[:split, :] = cv2.bitwise_not(top)

    # Bottom zone: preserve dark foreground during fades.
    bot_hsv = hsv[split:, :]
    bot_bgr = bgr[split:, :]
    bright_green = cv2.inRange(
        bot_hsv,
        (max(0, green_hue - config.hue_tol), 30, config.val_min_top),
        (min(179, green_hue + config.hue_tol), 255, 255),
    )

    g = bot_bgr[:, :, 1].astype(int)
    r = bot_bgr[:, :, 0].astype(int)
    b = bot_bgr[:, :, 2].astype(int)
    rgb_green = (g - r > config.green_dom) & (g - b > config.green_dom) & (g > config.val_min_top)
    dark = bot_hsv[:, :, 2] < config.val_max_bottom
    kill = ((bright_green > 0) | (rgb_green > 0)) & (~dark)
    mask[split:, :] = np.where(kill, 0, 255).astype(np.uint8)

    return mask


def despill(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Clamp green spill around foreground edges."""
    fg = mask > 0
    avg = (bgr[:, :, 0].astype(int) + bgr[:, :, 2].astype(int)) // 2
    g = bgr[:, :, 1].astype(int)
    spill = (g > avg + 15) & fg
    out = bgr.copy()
    out[:, :, 1][spill] = avg[spill].astype(np.uint8)
    return out


def remove_background_video(
    input_video: str | Path,
    output_webm: str | Path,
    config: ChromaKeyConfig | None = None,
) -> str:
    """Remove green/plain background and write transparent VP9 WebM."""
    cfg = config or ChromaKeyConfig()
    input_path = Path(input_video)
    output_path = Path(output_webm)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reader = imageio.get_reader(str(input_path), format="ffmpeg")
    meta = reader.get_meta_data()
    fps = meta.get("fps", 24)
    first = reader.get_next_data()
    first_bgr = cv2.cvtColor(first, cv2.COLOR_RGB2BGR)
    h, w = first_bgr.shape[:2]
    green_hue = detect_green_hue(first_bgr[: int(h * cfg.top_cutoff), :])
    reader.close()

    reader = imageio.get_reader(str(input_path), format="ffmpeg")
    writer = imageio.get_writer(
        str(output_path),
        format="ffmpeg",
        codec="libvpx-vp9",
        fps=fps,
        pixelformat="yuva420p",
        ffmpeg_params=["-crf", str(cfg.crf), "-b:v", "0", "-auto-alt-ref", "0"],
    )

    prev_mask = None
    for frame in reader:
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        mask = smart_mask(bgr, green_hue, h, w, cfg)
        if prev_mask is not None:
            # Blend a bit of previous mask to reduce flicker.
            mask = cv2.addWeighted(prev_mask, 0.2, mask, 0.8, 0)
            _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        prev_mask = mask.copy()

        bgr = despill(bgr, mask)
        rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
        rgba[:, :, 3] = mask
        writer.append_data(rgba)

    reader.close()
    writer.close()
    return str(output_path)


if __name__ == "__main__":
    # Minimal CLI fallback for local manual testing.
    src = "input.mp4"
    dst = "output.webm"
    print(f"Processing {src} -> {dst}")
    remove_background_video(src, dst)
    print("Done.")