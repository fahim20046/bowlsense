"""Bowler pose: YOLO+ByteTrack isolates the bowler box per frame, then MediaPipe Pose Landmarker
(heavy model == legacy model_complexity=2, 33 landmarks) runs on an upscaled crop with other people masked."""
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

from ..config import POSE_MODEL_PATH, POSE_MODEL_URL
from . import person_tracker as pt

CROP_SIZE = 512
MAX_INTERP_GAP = 7      # frames: interpolate bowler box across skipped (stride) frames and short dropouts


def ensure_model() -> Path:
    if not POSE_MODEL_PATH.exists():
        urllib.request.urlretrieve(POSE_MODEL_URL, POSE_MODEL_PATH)
    return POSE_MODEL_PATH


def _interp_boxes(path: dict, n: int) -> dict:
    out = dict(path)
    fs = sorted(path)
    for a, b in zip(fs, fs[1:]):
        if 1 < b - a <= MAX_INTERP_GAP + 1:
            for f in range(a + 1, b):
                w = (f - a) / (b - a)
                out[f] = tuple((1 - w) * np.array(path[a]) + w * np.array(path[b]))
    return out


def _crop(frame, box, others):
    """Square crop around box (25% margin), other people greyed out except where they overlap the bowler."""
    x0, y0, x1, y1 = box
    side = max(x1 - x0, y1 - y0) * 1.25
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    src = frame
    if others:
        src = frame.copy()
        for ox0, oy0, ox1, oy1 in others:
            src[max(int(oy0), 0):max(int(oy1), 0), max(int(ox0), 0):max(int(ox1), 0)] = 127
        ix0, iy0, ix1, iy1 = (max(int(v), 0) for v in box)
        src[iy0:iy1, ix0:ix1] = frame[iy0:iy1, ix0:ix1]
    s = int(round(side))
    X0, Y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    pad = cv2.copyMakeBorder(src, s, s, s, s, cv2.BORDER_CONSTANT, value=(127, 127, 127))
    crop = cv2.resize(pad[Y0 + s:Y0 + 2 * s, X0 + s:X0 + 2 * s], (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_CUBIC)
    return crop, X0, Y0, s


def run_pose(path: Path, progress: Optional[Callable[[float], None]] = None, arm: str = "right",
             hint: Optional[tuple[int, float, float]] = None):
    """Returns img (N,33,3)=[x_px,y_px,vis], world (N,33,3) m, info dict. NaN where bowler not found.
    hint = (frame, x_norm, y_norm): optional user click on the bowler."""
    cap = cv2.VideoCapture(str(path))
    n, W, H = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), int(cap.get(3)), int(cap.get(4))
    tracks = pt.track_people(path, (lambda p: progress(0.5 * p)) if progress else None, n)
    bpath, method = pt.select_bowler(tracks, n, W, H, hint)
    boxes = _interp_boxes(bpath, n)

    opts = vision.PoseLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(ensure_model())),
                                        running_mode=vision.RunningMode.IMAGE, num_poses=1,
                                        min_pose_detection_confidence=0.3, min_pose_presence_confidence=0.3)
    img, world = np.full((n, 33, 3), np.nan), np.full((n, 33, 3), np.nan)
    prev_small = None
    with vision.PoseLandmarker.create_from_options(opts) as lmk:
        for f in range(n):
            ok, frame = cap.read()
            if not ok:
                break
            small = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
            repeat = prev_small is not None and pt.is_repeat(prev_small, small)
            prev_small = small
            if repeat and f > 0:                          # duplicated frame: identical pose, skip the model
                img[f], world[f] = img[f - 1], world[f - 1]
            elif f in boxes:
                box = boxes[f]
                crop, X0, Y0, s = _crop(frame, box, pt.others_at(tracks, bpath, f))
                res = lmk.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
                if res.pose_landmarks:
                    lm = np.array([[X0 + p.x * s, Y0 + p.y * s, p.visibility] for p in res.pose_landmarks[0]])
                    hip = lm[[23, 24], :2].mean(0)
                    bw, bh = box[2] - box[0], box[3] - box[1]
                    # identity check: pose hips must lie inside the bowler box (margin 15%)
                    if box[0] - .15 * bw <= hip[0] <= box[2] + .15 * bw and box[1] - .15 * bh <= hip[1] <= box[3] + .15 * bh:
                        img[f] = lm
                        world[f] = [[p.x, p.y, p.z] for p in res.pose_world_landmarks[0]]
            if progress and f % 10 == 0:
                progress(0.5 + 0.5 * f / max(n, 1))
    cap.release()
    img[..., 2] = np.nan_to_num(img[..., 2], nan=0.0)
    info = {"selection": method, "bowler_box_frames": len(bpath), "people_tracked": len(tracks)}
    return img, world, info
