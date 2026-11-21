"""Post-release ball tracking (DESIGN.md §2.5): 3-frame differencing in the frames after ball release,
bowler body masked out, blob filtering by expected ball size, seed near the release hand, then
constant-velocity (alpha-beta / Kalman-lite) association. Returns detections + horizontal linearity R²."""
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .kinematics import Kin

DIFF_THR = 25
TRACK_SECONDS = 0.6
MIN_DET = 5
BALL_D_RATIO = 0.072 / 1.80      # ball diameter / typical stature


DUP_MAX_CHANGED = 3    # frames with fewer changed pixels (> DIFF_THR) than this are repeats of the previous


def _read(path: Path, f0: int, f1: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
    out = []
    for _ in range(f0, f1 + 1):
        ok, fr = cap.read()
        if not ok:
            break
        out.append(cv2.GaussianBlur(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (5, 5), 0))
    cap.release()
    return out


def distinct_mask(frames: list[np.ndarray]) -> np.ndarray:
    """True where a frame carries new content (frame-rate-converted video repeats frames)."""
    m = np.ones(len(frames), bool)
    for i in range(1, len(frames)):
        m[i] = int(np.count_nonzero(cv2.absdiff(frames[i], frames[i - 1]) > DIFF_THR)) >= DUP_MAX_CHANGED
    return m


def _body_mask(k: Kin, f: int, shape, height_px: int) -> Optional[tuple[int, int, int, int]]:
    """Bounding box of the bowler's body EXCLUDING the bowling forearm/hand (the ball leaves from there)."""
    b = k.ids["b"]
    hand = (17, 19, 21) if b["wr"] == 15 else (18, 20, 22)          # pinky / index / thumb of bowling hand
    ids = [i for i in range(33) if i not in (b["wr"], b["el"], *hand)]
    pts = k.P[f, ids]
    pts = pts[np.isfinite(pts).all(1)]
    if len(pts) < 6:
        return None
    x0, x1 = pts[:, 0].min(), pts[:, 0].max()
    y0, y1 = height_px - pts[:, 1].max(), height_px - pts[:, 1].min()     # back to image coords
    m = 0.08 * k.H
    return int(max(x0 - m, 0)), int(max(y0 - m, 0)), int(min(x1 + m, shape[1])), int(min(y1 + m, shape[0]))


def candidates(prev, cur, nxt, r: float, mask_box=None) -> list[tuple[float, float]]:
    d = np.minimum(cv2.absdiff(cur, prev), cv2.absdiff(nxt, cur))
    _, bw = cv2.threshold(d, DIFF_THR, 255, cv2.THRESH_BINARY)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    if mask_box:
        x0, y0, x1, y1 = mask_box
        bw[y0:y1, x0:x1] = 0
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    a_min, a_max = max(2.0, 0.25 * np.pi * (0.5 * r) ** 2), 6 * np.pi * (2.5 * r) ** 2   # blur streaks allowed
    out = []
    for c in cnts:
        a = cv2.contourArea(c)
        if not a_min <= a <= a_max:
            continue
        (cx, cy), (w, h), _ = cv2.minAreaRect(c)
        if min(w, h) > 0 and max(w, h) / min(w, h) > 8:       # long thin = bat/limb edge, not ball
            continue
        out.append((cx, cy))
    return out


def track(path: Path, k: Kin, br: Optional[int], height_px: int) -> tuple[list[tuple[int, float, float]], Optional[float], list[str]]:
    notes: list[str] = []
    if br is None or not np.isfinite(k.H):
        return [], None, ["Ball release frame or bowler scale unavailable."]
    f0, f1 = max(br - 1, 0), min(br + int(TRACK_SECONDS * k.fps) + 1, k.n - 1)
    frames = _read(path, f0, f1)
    if len(frames) < 4:
        return [], None, ["Not enough frames after release."]
    r = BALL_D_RATIO * k.H / 2                                        # expected ball radius (px)
    wr = k.pt(k.ids["b"]["wr"])
    wf = next((f for f in (br, br - 1, br - 2, br + 1) if 0 <= f < k.n and np.isfinite(wr[f]).all()), None)
    if wf is None:
        return [], None, ["Release hand position not visible; cannot seed ball search."]
    hand = np.array([wr[wf, 0], height_px - wr[wf, 1]])

    uniq = np.flatnonzero(distinct_mask(frames))          # difference only between frames with new content
    if len(uniq) < len(frames) * 0.9:
        notes.append(f"Duplicated frames detected: effective ≈ {k.fps * len(uniq) / len(frames):.0f} fps "
                     f"(container says {k.fps:.0f}).")
    cands = {}
    for a, i, c in zip(uniq, uniq[1:], uniq[2:]):
        f = f0 + i
        cands[f] = candidates(frames[a], frames[i], frames[c], r, _body_mask(k, min(f, k.n - 1), frames[i].shape, height_px))

    # seed: candidate closest to the hand within 0.6 stature in the first 3 frames after release
    seed = None
    for f in range(br, min(br + 3, f1)):
        for c in cands.get(f, []):
            dd = np.linalg.norm(np.array(c) - hand)
            if dd < 0.6 * k.H and (seed is None or dd < seed[0]):
                seed = (dd, f, np.array(c))
    if seed is None:
        return [], None, ["No moving ball-sized object found near the release hand (motion blur / low frame rate)."]
    trk = [(seed[1], seed[2])]
    vel, miss = None, 0
    f = seed[1] + 1
    while f < f1 and miss <= 2:
        if f not in cands:          # duplicated frame: no new information, not a miss
            f += 1
            continue
        last_f, last_p = trk[-1]
        dt = f - last_f
        if vel is None:      # 2nd point: displacement consistent with 40–170 km/h (≈ 6–26 statures/s), fps-scaled
            lo, hi = 0.5 * 6 * k.H / k.fps * dt, 1.5 * 26 * k.H / k.fps * dt
            opts = [np.array(c) for c in cands.get(f, []) if lo < np.linalg.norm(np.array(c) - last_p) < hi
                    and (k.perspective != "side_on" or (c[0] - last_p[0]) * k.dx > 0)]   # side-on: ball travels with the bowler
            pick = min(opts, key=lambda c: abs(c[1] - last_p[1]), default=None)
        else:
            pred = last_p + vel * dt
            gate = 0.15 * k.H + 0.3 * np.linalg.norm(vel) * dt
            opts = [np.array(c) for c in cands.get(f, []) if np.linalg.norm(np.array(c) - pred) < gate]
            pick = min(opts, key=lambda c: np.linalg.norm(c - pred), default=None)
        if pick is None:
            miss += 1
        else:
            nv = (pick - last_p) / dt
            vel = nv if vel is None else 0.5 * vel + 0.5 * nv            # alpha-beta velocity update
            trk.append((f, pick))
            miss = 0
        f += 1

    out = [(int(fr), round(float(p[0]), 1), round(float(p[1]), 1)) for fr, p in trk]
    if len(out) < MIN_DET:
        notes.append(f"Only {len(out)} ball detections (need ≥ {MIN_DET}).")
        return out, None, notes
    t = np.array([o[0] for o in out], float)
    x = np.array([o[1] for o in out])
    A = np.vstack([t, np.ones_like(t)]).T
    res = x - A @ np.linalg.lstsq(A, x, rcond=None)[0]
    ss = np.sum((x - x.mean()) ** 2)
    r2 = float(1 - np.sum(res ** 2) / ss) if ss > 0 else 0.0
    return out, round(r2, 4), notes
