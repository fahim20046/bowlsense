"""YOLO person detection + ByteTrack, bowler-track selection and stitching.

Why: broadcast/match footage contains umpire, batters, fielders. MediaPipe Pose is a single-person
model, so we first isolate the bowler's bounding box per frame, then run pose on that crop."""
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..config import MODEL_DIR

YOLO_WEIGHTS = MODEL_DIR / "yolo11n.pt"
IMGSZ = 960            # 640 is ~2x faster but misses small, distant bowlers early in the run-up
STRIDE = 1             # every frame: skipping frames made ByteTrack lose fast, small bowlers (coverage 86% -> 40%)
DUP_PIXELS = 30        # a frame with fewer changed pixels than this (vs previous) is a repeat -> reuse results
Box = tuple[float, float, float, float]   # x0, y0, x1, y1 (px)


def _model():
    from ultralytics import YOLO
    from ultralytics.utils.downloads import attempt_download_asset
    if not YOLO_WEIGHTS.exists():
        attempt_download_asset(str(YOLO_WEIGHTS))
    return YOLO(str(YOLO_WEIGHTS))


def track_people(path: Path, progress: Optional[Callable[[float], None]] = None, n: int = 0) -> dict[int, dict[int, Box]]:
    """Returns {track_id: {frame: box}} for every tracked person."""
    import cv2
    tracks: dict[int, dict[int, Box]] = {}
    model = _model()
    cap = cv2.VideoCapture(str(path))
    prev_small, prev_boxes, f = None, [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
        if prev_small is not None and is_repeat(prev_small, small):
            boxes = prev_boxes                            # repeated frame (slow-motion conversion): reuse
        else:
            r = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0], conf=0.2,
                            imgsz=IMGSZ, verbose=False)[0]
            b = r.boxes
            boxes = list(zip(b.id.int().tolist(), b.xyxy.tolist())) if b is not None and b.id is not None else []
        for tid, xyxy in boxes:
            tracks.setdefault(tid, {})[f] = tuple(xyxy)
        prev_small, prev_boxes = small, boxes
        if progress and f % 10 == 0:
            progress(min(f / max(n, 1), 1.0))
        f += 1
    cap.release()
    return tracks


def is_repeat(a, b) -> bool:
    """True if downscaled grey frame b is (nearly) identical to a — a duplicated frame."""
    import cv2
    return int(np.count_nonzero(cv2.absdiff(a, b) > 12)) < DUP_PIXELS


def _c(b: Box):
    return np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])


def _h(b: Box):
    return b[3] - b[1]


def _motion(t: dict[int, Box]) -> tuple[list[int], np.ndarray]:
    """Per-frame box motion in body-heights/frame (centre shift + scale change, so depth motion counts)."""
    fs = sorted(t)
    c = np.array([_c(t[f]) for f in fs])
    h = np.array([_h(t[f]) for f in fs])
    dt = np.maximum(np.diff(fs), 1)
    m = (np.linalg.norm(np.diff(c, axis=0), axis=1) + np.abs(np.diff(h))) / h[1:] / dt
    return fs, m


def trim_static_prefix(t: dict[int, Box], thr: float = 0.012, win: int = 5) -> dict[int, Box]:
    """ByteTrack can hand a static person's ID (umpire) to the bowler running past. A bowler is moving
    throughout a delivery clip, so drop a long stationary prefix if the track moves afterwards."""
    fs, m = _motion(t)
    if len(m) < 2 * win:
        return t
    sm = np.convolve(m, np.ones(win) / win, mode="same")
    moving = np.flatnonzero(sm > thr)
    if len(moving) == 0 or moving[0] < win:
        return t
    start = fs[moving[0]]
    return {f: b for f, b in t.items() if f >= start}


def stitch(tracks: dict, seed: int | dict, max_gap: int = 20) -> dict[int, Box]:
    """Extend the seed track forward/backward with fragments (ByteTrack ID switches during occlusion)
    that start/end close in time, position and size."""
    path = dict(tracks[seed]) if isinstance(seed, int) else dict(seed)
    used = {seed} if isinstance(seed, int) else set()
    changed = True
    while changed:
        changed = False
        first, last = min(path), max(path)
        for tid, t in tracks.items():
            if tid in used:
                continue
            ts, te = min(t), max(t)
            if 0 < ts - last <= max_gap:            # continues after
                a, b, gap = path[last], t[ts], ts - last
            elif 0 < first - te <= max_gap:         # precedes
                a, b, gap = path[first], t[te], first - te
            else:
                continue
            h = max(_h(a), _h(b))
            if np.linalg.norm(_c(a) - _c(b)) < 0.35 * h * gap ** 0.5 and 0.6 < _h(b) / _h(a) < 1.6:
                for f, bx in t.items():
                    path.setdefault(f, bx)
                used.add(tid)
                changed = True
    return path


def _long_enough(t: dict, n: int) -> bool:
    return len(t) * STRIDE >= max(5, 0.1 * n)


def bowler_score(t: dict[int, Box], n: int, max_h: float | None = None) -> float:
    """Bowler = the main subject: present for most of the clip (coverage), large in frame (relative size),
    and moving (run-up across the image or toward/away from the camera). Image motion alone is not enough:
    when the camera pans to follow the bowler he stays centred while background people appear to move."""
    if not _long_enough(t, n):
        return -1.0
    fs = sorted(t)
    c = np.array([_c(t[f]) for f in fs])
    h = np.array([_h(t[f]) for f in fs])
    hm = np.median(h)
    travel = min(np.sum(np.linalg.norm(np.diff(c, axis=0), axis=1)) / hm, 10.0)
    depth = abs(np.log(np.median(h[: max(3, len(h) // 5)]) / np.median(h[-max(3, len(h) // 5):])))
    coverage = min(1.0, len(t) * STRIDE / n)                 # each detection stands for STRIDE frames
    size = hm / max_h if max_h else 1.0
    return coverage * size * (1 + 0.3 * travel + 2 * depth)


def select_bowler(tracks: dict, n: int, W: int, H: int, hint=None) -> tuple[dict[int, Box], str]:
    """hint = (frame, x_norm, y_norm). Returns (frame->box path, method)."""
    if not tracks:
        return {}, "none"
    if hint is not None:
        hf, hx, hy = hint[0], hint[1] * W, hint[2] * H

        def dist(item):
            t = item[1]
            f = min(t, key=lambda k: abs(k - hf))
            b = t[f]
            inside = b[0] <= hx <= b[2] and b[1] <= hy <= b[3]
            return (abs(f - hf) > 5, not inside, np.linalg.norm(_c(b) - [hx, hy]) / _h(b))
        seed = min(tracks.items(), key=dist)[0]
        path = stitch(tracks, seed)
        trimmed = trim_static_prefix(path)
        if min(trimmed) <= hf:            # never trim past the frame the user clicked
            path = stitch(tracks, trimmed)
        return path, "hint"
    long_tracks = [t for t in tracks.values() if _long_enough(t, n)]
    max_h = max(np.median([_h(b) for b in t.values()]) for t in long_tracks) if long_tracks else None
    seed = max(tracks, key=lambda k: bowler_score(trim_static_prefix(tracks[k]), n, max_h))
    return stitch(tracks, trim_static_prefix(stitch(tracks, seed))), "auto"


def others_at(tracks: dict, path: dict, f: int) -> list[Box]:
    """Boxes of all other people in frame f (for masking)."""
    mine = path.get(f)
    return [t[f] for t in tracks.values() if f in t and t[f] != mine]
