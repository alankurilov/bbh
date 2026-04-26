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
    banner_color_margin: float = 22.0
    banner_reference_scan_frames: int = 24
    crf: int = 20


def detect_green_hue(top_bgr: np.ndarray) -> int:
    hsv = cv2.cvtColor(top_bgr, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 0] > 30) & (hsv[:, :, 0] < 90) & (hsv[:, :, 1] > 40)
    return int(np.median(hsv[:, :, 0][mask])) if mask.any() else 60


def detect_banner_reference(
    first_bgr: np.ndarray,
    green_hue: int,
    config: ChromaKeyConfig,
) -> tuple[np.ndarray, float]:
    """Estimate banner color profile from non-green pixels in bottom zone."""
    h = first_bgr.shape[0]
    split = int(h * config.top_cutoff)
    bot_hsv = cv2.cvtColor(first_bgr[split:, :], cv2.COLOR_BGR2HSV)
    bot_lab = cv2.cvtColor(first_bgr[split:, :], cv2.COLOR_BGR2LAB).astype(np.float32)
    hue = bot_hsv[:, :, 0].astype(np.int16)
    sat = bot_hsv[:, :, 1]
    val = bot_hsv[:, :, 2]
    hue_dist = np.minimum(np.abs(hue - green_hue), 180 - np.abs(hue - green_hue))
    # Ignore near-black pixels so "fade from black" is not learned as banner color.
    non_green = ((hue_dist > config.hue_tol + 8) & (val > 28)) | ((sat < 40) & (val > 40))
    if np.any(non_green):
        samples = bot_lab[non_green]
    else:
        samples = bot_lab.reshape(-1, 3)

    banner_lab = np.median(samples, axis=0)
    distances = np.linalg.norm(samples - banner_lab, axis=1)
    adaptive_thresh = float(np.percentile(distances, 75) + config.banner_color_margin)
    # Clamp to sane range to avoid over/under-masking.
    adaptive_thresh = float(np.clip(adaptive_thresh, 18.0, 55.0))
    return banner_lab, adaptive_thresh


def _banner_presence_score(
    frame_bgr: np.ndarray,
    green_hue: int,
    config: ChromaKeyConfig,
) -> int:
    """Score frame by how much non-green content appears in banner zone."""
    h = frame_bgr.shape[0]
    split = int(h * config.top_cutoff)
    bot_hsv = cv2.cvtColor(frame_bgr[split:, :], cv2.COLOR_BGR2HSV)
    hue = bot_hsv[:, :, 0].astype(np.int16)
    sat = bot_hsv[:, :, 1]
    val = bot_hsv[:, :, 2]
    hue_dist = np.minimum(np.abs(hue - green_hue), 180 - np.abs(hue - green_hue))
    non_green = ((hue_dist > config.hue_tol + 8) & (val > 28)) | ((sat < 40) & (val > 40))
    return int(np.count_nonzero(non_green))


def _select_banner_reference_frame(
    candidate_frames_bgr: list[np.ndarray],
    green_hue: int,
    config: ChromaKeyConfig,
) -> np.ndarray:
    """Pick early frame where banner is most visible (avoids black/fade first frame bias)."""
    best_idx = 0
    best_score = -1
    for idx, frame_bgr in enumerate(candidate_frames_bgr):
        score = _banner_presence_score(frame_bgr, green_hue, config)
        if score > best_score:
            best_score = score
            best_idx = idx
    return candidate_frames_bgr[best_idx]


def smart_mask(
    bgr: np.ndarray,
    green_hue: int,
    banner_lab_ref: np.ndarray,
    banner_dist_thresh: float,
    h: int,
    w: int,
    config: ChromaKeyConfig,
) -> np.ndarray:
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
    bot_lab = cv2.cvtColor(bot_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    bright_green = cv2.inRange(
        bot_hsv,
        (max(0, green_hue - config.hue_tol), 30, config.val_min_top),
        (min(179, green_hue + config.hue_tol), 255, 255),
    )

    b = bot_bgr[:, :, 0].astype(int)
    g = bot_bgr[:, :, 1].astype(int)
    r = bot_bgr[:, :, 2].astype(int)
    rgb_green = (g - r > config.green_dom) & (g - b > config.green_dom) & (g > config.val_min_top)

    # Adaptive protection for any banner color (not only dark):
    # preserve pixels that are close to sampled banner color profile.
    hue = bot_hsv[:, :, 0].astype(np.int16)
    sat = bot_hsv[:, :, 1]
    hue_dist = np.minimum(np.abs(hue - green_hue), 180 - np.abs(hue - green_hue))
    lab_dist_to_banner = np.linalg.norm(bot_lab - banner_lab_ref, axis=2)
    near_banner_color = lab_dist_to_banner < banner_dist_thresh
    low_sat_non_green = (sat < 45) & (hue_dist > config.hue_tol + 3)
    banner_safe = near_banner_color | low_sat_non_green

    kill = ((bright_green > 0) | (rgb_green > 0)) & (~banner_safe)
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
    candidate_frames_bgr: list[np.ndarray] = []
    first = reader.get_next_data()
    first_bgr = cv2.cvtColor(first, cv2.COLOR_RGB2BGR)
    candidate_frames_bgr.append(first_bgr)
    h, w = first_bgr.shape[:2]
    green_hue = detect_green_hue(first_bgr[: int(h * cfg.top_cutoff), :])

    for i, frame in enumerate(reader):
        if i >= max(0, cfg.banner_reference_scan_frames - 1):
            break
        candidate_frames_bgr.append(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

    banner_reference_bgr = _select_banner_reference_frame(candidate_frames_bgr, green_hue, cfg)
    banner_lab_ref, banner_dist_thresh = detect_banner_reference(banner_reference_bgr, green_hue, cfg)
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
        mask = smart_mask(bgr, green_hue, banner_lab_ref, banner_dist_thresh, h, w, cfg)
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