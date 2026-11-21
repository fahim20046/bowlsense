"""Shared kinematic context: smoothed y-up coords, stature, travel direction."""
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..core import geometry as g
from ..core.smoothing import smooth_landmarks


@dataclass
class Kin:
    P: np.ndarray        # (N,33,2) smoothed, y-UP pixel coords (NaN = unavailable)
    vis: np.ndarray      # (N,33) raw visibility
    W: np.ndarray        # (N,33,3) smoothed world landmarks (m, MediaPipe axes)
    fps: float
    arm: str
    perspective: str
    H: float             # stature estimate (px)
    dx: float            # +1 / -1 direction of travel along image x
    ids: dict
    dropped: int = 0     # frames removed because the skeleton jumped to another person
    swapped: Optional[tuple] = None   # (first, last) frames where left/right labels were corrected
    br_source: Optional[tuple] = None  # ('model'|'rule', model peak probability) for the release frame
    auto_view: Optional[tuple] = None  # (selected, detected) when the camera view was auto-corrected

    @property
    def n(self):
        return len(self.P)

    def pt(self, j):
        return self.P[:, j]

    def mid(self, a, b):
        return (self.P[:, a] + self.P[:, b]) / 2


def estimate_view(k: "Kin") -> Optional[str]:
    """Guess the camera view from the run-up (first 60% of tracked frames):
    side-on  -> the bowler crosses the image (hip travel > 0.8 stature) or shoulders overlap (< 0.06);
    front-on -> person's LEFT shoulder (11) appears on the image RIGHT (facing the camera);
    rear     -> left shoulder on the image left (back to the camera)."""
    valid = np.flatnonzero(np.isfinite(k.P[:, [g.L_SH, g.R_SH, g.L_HIP, g.R_HIP], 0]).all(1))
    if len(valid) < 10 or not np.isfinite(k.H):
        return None
    run = valid[: max(10, int(0.6 * len(valid)))]
    q = max(3, len(run) // 5)
    hx = (k.P[run, g.L_HIP, 0] + k.P[run, g.R_HIP, 0]) / 2
    travel = abs(np.median(hx[-q:]) - np.median(hx[:q])) / k.H
    dxs = k.P[run, g.L_SH, 0] - k.P[run, g.R_SH, 0]
    if travel > 0.8 or np.median(np.abs(dxs)) / k.H < 0.06:
        return "side_on"
    return "front_on" if np.median(dxs) > 0 else "rear"


JUMP_WINDOW = 7          # ± frames for the rolling-median identity reference
JUMP_DIST = 1.0          # hip-centre deviation > 1.0 × torso length from the local median = other person
JUMP_SIZE = (0.6, 1.6)   # torso length ratio vs local median outside this = other person


def drop_identity_jumps(xy: np.ndarray, vis: np.ndarray) -> int:
    """Remove frames where the skeleton jumps to another person (umpire / batter / fielder).
    Reference = rolling median of the hip centre and torso length over ±7 frames, so brief switches
    (≤ 7 frames) stand out. Modifies xy/vis in place; returns number of frames dropped."""
    hip = (xy[:, g.L_HIP] + xy[:, g.R_HIP]) / 2
    sh = (xy[:, g.L_SH] + xy[:, g.R_SH]) / 2
    torso = np.linalg.norm(sh - hip, axis=1)
    valid = np.isfinite(hip).all(1) & np.isfinite(torso) & (torso > 0)
    idx = np.flatnonzero(valid)
    bad = []
    for i in idx:
        nb = idx[(idx >= i - JUMP_WINDOW) & (idx <= i + JUMP_WINDOW)]
        if len(nb) < 5:
            continue
        mc, ms = np.median(hip[nb], axis=0), np.median(torso[nb])
        if np.linalg.norm(hip[i] - mc) > JUMP_DIST * ms or not JUMP_SIZE[0] < torso[i] / ms < JUMP_SIZE[1]:
            bad.append(i)
    xy[bad] = np.nan
    vis[bad] = 0.0
    return len(bad)


def build(img: np.ndarray, world: np.ndarray, fps: float, height_px: int, arm: str, perspective: str) -> Kin:
    vis = img[..., 2].copy()
    xy = img[..., :2].copy()
    dropped = drop_identity_jumps(xy, vis)
    world = world.copy()
    world[vis.max(axis=1) == 0] = np.nan
    xy[..., 1] = height_px - xy[..., 1]                      # flip to y-up
    P = smooth_landmarks(xy, vis, fps)
    W = smooth_landmarks(world, vis, fps)
    ids = g.side(arm)

    # stature: (thigh + shank + hip-shoulder) ≈ 0.779 H (Drillis-Contini); take 90th pct (least foreshortened)
    seg = []
    for s in ("L", "R"):
        hip, kn, an = (g.L_HIP, g.L_KN, g.L_AN) if s == "L" else (g.R_HIP, g.R_KN, g.R_AN)
        sh = g.L_SH if s == "L" else g.R_SH
        seg.append(np.linalg.norm(P[:, hip] - P[:, kn], axis=1) + np.linalg.norm(P[:, kn] - P[:, an], axis=1)
                   + np.linalg.norm(P[:, sh] - P[:, hip], axis=1))
    seg = np.nanmax(np.vstack(seg), axis=0) if np.isfinite(seg).any() else np.array([np.nan])
    H = float(np.nanpercentile(seg, 90) / 0.779) if np.isfinite(seg).any() else float("nan")

    hx = (P[:, g.L_HIP, 0] + P[:, g.R_HIP, 0]) / 2
    valid = np.flatnonzero(np.isfinite(hx))
    dx = 1.0
    if len(valid) > 1:
        net = hx[valid[-1]] - hx[valid[0]]
        dx = 1.0 if net >= 0 else -1.0
    return Kin(P=P, vis=vis, W=W, fps=fps, arm=arm, perspective=perspective, H=H, dx=dx, ids=ids, dropped=dropped)
