"""Metadata, browser-playable normalization and quality validation (DESIGN.md §2.1)."""
import subprocess
from pathlib import Path

import cv2
import numpy as np

from ..schemas import QualityReport, VideoMeta


class VideoError(Exception):
    pass


def probe(path: Path) -> VideoMeta:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoError("CORRUPT_VIDEO: cannot open file")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, _ = cap.read()
    cap.release()
    if not ok or fps <= 0 or n <= 0:
        raise VideoError("CORRUPT_VIDEO: no readable frames")
    return VideoMeta(fps=fps, width=w, height=h, total_frames=n, duration_s=n / fps)


def _fourcc(path: Path) -> str:
    cap = cv2.VideoCapture(str(path))
    v = int(cap.get(cv2.CAP_PROP_FOURCC))
    cap.release()
    return "".join(chr((v >> 8 * i) & 0xFF) for i in range(4)).lower()


def make_playable(src: Path, dst: Path) -> Path:
    """Ensure H.264 MP4 (browser-safe) with every source frame kept (passthrough timing).
    Analysis runs on the SAME file the browser plays so frame indices stay in sync."""
    if src.suffix.lower() == ".mp4" and _fourcc(src) in ("avc1", "h264"):
        src.rename(dst)
        return dst
    import imageio_ffmpeg
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(src), "-an", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough",
           "-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dst.exists():
        raise VideoError(f"CORRUPT_VIDEO: transcode failed ({r.stderr[-300:]})")
    src.unlink(missing_ok=True)
    return dst


def blur_variance(path: Path, samples: int = 20) -> float:
    """Median variance-of-Laplacian over evenly sampled frames (higher = sharper)."""
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vals = []
    for idx in np.linspace(0, max(n - 1, 0), samples).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, f = cap.read()
        if ok:
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            vals.append(cv2.Laplacian(g, cv2.CV_64F).var())
    cap.release()
    return float(np.median(vals)) if vals else 0.0


def duplicate_ratio(path: Path, samples: int = 40) -> float:
    """Fraction of sampled consecutive frame pairs that are identical (frame-rate-converted video)."""
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dups = tot = 0
    for idx in np.linspace(0, max(n - 2, 0), samples).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok1, a = cap.read()
        ok2, b = cap.read()
        if ok1 and ok2:
            tot += 1
            diff = cv2.absdiff(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.cvtColor(b, cv2.COLOR_BGR2GRAY))
            dups += int(np.count_nonzero(diff > 25)) < 3
    cap.release()
    return dups / tot if tot else 0.0


def quality(meta: VideoMeta, blur: float, mean_vis: float, det_rate: float, dup_ratio: float = 0.0) -> QualityReport:
    warn = []
    if dup_ratio > 0.1:
        warn.append(f"{dup_ratio * 100:.0f}% of frames are duplicates (frame-rate conversion): effective "
                    f"≈ {meta.fps * (1 - dup_ratio):.0f} fps; timing-based metrics are less precise.")
    res_ok = meta.width * meta.height >= 640 * 360
    fps_ok = meta.fps >= 50
    sharp_ok = blur >= 100
    if not res_ok:
        warn.append(f"Low resolution {meta.width}x{meta.height} (< 640x360).")
    if not fps_ok:
        warn.append(f"Frame rate {meta.fps:.0f} fps < 50: release-phase blur, reduced timing accuracy.")
    if not sharp_ok:
        warn.append(f"Image appears blurry (Laplacian variance {blur:.0f} < 100).")
    if mean_vis < 0.6:
        warn.append(f"Low landmark visibility (mean {mean_vis:.2f}).")
    if det_rate < 0.7:
        warn.append(f"Bowler detected in only {det_rate*100:.0f}% of frames.")
    clip = lambda v: float(np.clip(v, 0, 1))
    score = 100 * (0.30 * clip(meta.width * meta.height / (1280 * 720)) + 0.25 * clip(meta.fps / 120)
                   + 0.25 * clip(blur / 300) + 0.20 * clip(mean_vis * det_rate / 0.8))
    return QualityReport(score=round(score, 1), resolution_ok=res_ok, fps_ok=fps_ok, blur_variance=round(blur, 1),
                         sharp_ok=sharp_ok, mean_visibility=round(mean_vis, 3), detection_rate=round(det_rate, 3),
                         warnings=warn)
