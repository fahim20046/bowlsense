"""Measured ball speed (calibrated ball tracking or manual frame timing) and the SEPARATE
biomechanical speed-potential indicator (DESIGN.md §7.3)."""
from pathlib import Path
from typing import Optional

import numpy as np

from ..schemas import BiomechanicsReport, Calibration, ManualTiming, Metric, SpeedPotential, SpeedResult
from . import ball_tracker
from .kinematics import Kin

MIN_R2 = 0.95
PLAUSIBLE_KMH = (40.0, 170.0)
RELEASE_AHEAD_M = 0.8      # typical release point in front of the bowler's popping crease (approx., ±0.5 m)


def _scale(c: Calibration):
    p1, p2 = np.array(c.p1), np.array(c.p2)
    d = np.linalg.norm(p2 - p1)
    return (c.distance_m / d, (p2 - p1) / d) if d > 0 else (None, None)


def measure(path: Path, k: Kin, br: Optional[int], height_px: int, calib: Optional[Calibration],
            manual: Optional[ManualTiming]) -> SpeedResult:
    trk, r2, notes = ball_tracker.track(path, k, br, height_px)
    res = SpeedResult(track=trk, detections=len(trk), fit_r2=r2, calibration=calib, manual=manual, notes=notes)

    # ---- 1) calibrated ball tracking (side-on only) ----
    if k.perspective != "side_on":
        res.status = "unavailable_perspective"
        res.notes.append("Ball-tracking speed needs a side-on view (ball path perpendicular to the camera).")
    elif calib is None:
        res.status = "unavailable_no_calibration"
        res.notes.append("Add the 2-point pitch calibration (click both popping creases) to convert pixels to metres.")
    elif len(trk) < ball_tracker.MIN_DET or r2 is None or r2 < MIN_R2:
        res.status = "unavailable_tracking_failed"
        res.notes.append(f"Ball track rejected (detections {len(trk)}, linearity R² {r2}). Need ≥ {ball_tracker.MIN_DET} and R² ≥ {MIN_R2}.")
    else:
        s, e = _scale(calib)
        pts = np.array([[x, y] for _, x, y in trk[:7]])
        fr = np.array([f for f, _, _ in trk[:7]], float)
        v = np.abs((np.diff(pts, axis=0) @ e) * s / (np.diff(fr) / k.fps))
        kmh = float(np.median(v) * 3.6)
        if PLAUSIBLE_KMH[0] <= kmh <= PLAUSIBLE_KMH[1]:
            res.measured_kmh, res.method, res.status = round(kmh, 1), "ball_tracking", "ok"
            res.notes.append("Speed from the first post-release detections (≈ release speed).")
        else:
            res.status = "unavailable_tracking_failed"
            res.notes.append(f"Computed {kmh:.0f} km/h is outside the plausible range {PLAUSIBLE_KMH} — rejected.")

    # ---- 2) manual frame timing (any view) ----
    if manual is not None:
        dt = (manual.arrival_frame - manual.release_frame) / k.fps
        if dt <= 0:
            res.notes.append("Manual timing: arrival frame must be after release frame.")
        else:
            wr = k.pt(k.ids["b"]["wr"])[manual.release_frame] if 0 <= manual.release_frame < k.n else np.array([np.nan, np.nan])
            if calib is not None and k.perspective == "side_on" and np.isfinite(wr).all():
                s, e = _scale(calib)
                hand = np.array([wr[0], height_px - wr[1]])
                dist = float(abs((np.array(calib.p2) - hand) @ e) * s)
                how = "release point → batter's crease from calibration"
            else:
                dist = 17.68 - RELEASE_AHEAD_M
                how = f"assumed 17.68 m − {RELEASE_AHEAD_M} m release offset (approx. ±5%)"
            kmh = dist / dt * 3.6
            if PLAUSIBLE_KMH[0] <= kmh <= PLAUSIBLE_KMH[1]:
                res.manual_kmh = round(kmh, 1)
                if res.method == "none":
                    res.method = "manual_timing"
                res.notes.append(f"Manual timing: {dist:.2f} m in {dt:.3f} s ({how}); average speed over the flight "
                                 f"(includes drag/bounce, typically 10–15% below release speed). "
                                 f"Frame quantisation: ±{100 / max(manual.arrival_frame - manual.release_frame, 1):.0f}%.")
            else:
                res.notes.append(f"Manual timing gives {kmh:.0f} km/h — implausible, check the two frames.")
    return res


# ---------------- speed potential (qualitative, separate from measurement) ----------------
def _band(v, lo0, lo1, hi1=None, hi0=None):
    """0 at lo0, 1 between lo1 and hi1, back to 0 at hi0 (piecewise linear)."""
    if v < lo1:
        return float(np.clip((v - lo0) / (lo1 - lo0), 0, 1))
    if hi1 is not None and v > hi1:
        return float(np.clip((hi0 - v) / (hi0 - hi1), 0, 1))
    return 1.0


RULES = [  # metric key, sub-score fn, description
    ("runup_momentum", lambda v: _band(v, 0.5, 1.6), "Run-up momentum (hip speed at BFC, target ≥ 1.6 heights/s)"),
    ("front_knee_delta", lambda v: _band(v, -20, 0), "Front-leg brace (knee Δ FFC→BR, target ≥ 0°)"),
    ("separation_ffc", lambda v: _band(abs(v), 0, 30, 45, 75), "Hip-shoulder separation at FFC (target 30–45°)"),
    ("release_height_br", lambda v: _band(v, 0.9, 1.15), "Release height / stature (target ≥ 1.15)"),
]


def potential(bio: BiomechanicsReport) -> SpeedPotential:
    metrics = {m.key: m for m in bio.upper_body + bio.lower_body + bio.posture}
    comps, scores = [], {}
    for key, fn, desc in RULES:
        m = metrics.get(key)
        if m is None:
            continue
        comps.append(m.model_copy(update={"label": desc}))
        scores[key] = round(fn(m.value), 2) if m.status == "ok" and m.reliability != "low" else None
    avail = [s for s in scores.values() if s is not None]
    if len(avail) < 2:
        return SpeedPotential(level="Unavailable", components=comps, scores=scores)
    mean = float(np.mean(avail))
    level = "High" if mean >= 0.7 else "Moderate" if mean >= 0.4 else "Low"
    return SpeedPotential(level=level, components=comps, scores=scores)
