"""Preliminary elbow-extension screening vs ICC 15° (DESIGN.md §7.2)."""
from typing import Optional

import numpy as np

from .. import thresholds as T
from ..config import VIS_THRESHOLD
from ..core import geometry as g
from ..core.smoothing import derivative
from ..schemas import ElbowPoint, LegalityResult, ManualElbow, ManualElbowPoint, ManualLegality, PhaseMark
from .kinematics import Kin

UNAV = "Unavailable"
VIEW_NOTE = ("Front/rear view – lower accuracy: the arm moves toward/away from the camera, so part of any elbow "
             "bend can be hidden (results tend toward 'Legal'). Side-on video is most accurate.")


def classify(delta: float, margin: float = 0.0, limit: float = T.ICC_ELBOW_LIMIT) -> str:
    """Simple project rule (requested): net elbow extension < 15° -> Legal, ≥ 15° -> Illegal.
    The error margin is still computed and shown for information but does not change the verdict."""
    return "Legal" if delta < limit else "Illegal"


def error_margin(perspective: str, mean_vis: float, fps: float) -> float:
    m = T.LEGALITY_MARGIN[perspective]
    if mean_vis < 0.7:
        m += T.LEGALITY_MARGIN_LOW_VIS
    if fps < 100:
        m += T.LEGALITY_MARGIN_LOW_FPS
    return m


def manual_angle(p: ManualElbowPoint) -> float:
    """Elbow angle from clicked shoulder/elbow/wrist (image px): θ = arccos((S−E)·(W−E)/(|S−E||W−E|))."""
    return float(g.angle3(np.array(p.shoulder, float), np.array(p.elbow, float), np.array(p.wrist, float)))


def manual_screen(pts: list[ManualElbowPoint], perspective: str, fps: float) -> ManualLegality:
    """Δθ = θ(last digitised frame = release) − min θ over digitised frames (arm horizontal → release)."""
    pts = sorted(pts, key=lambda p: p.frame)
    ang = [round(manual_angle(p), 1) for p in pts]
    margin = T.MANUAL_MARGIN + (T.LEGALITY_MARGIN_LOW_FPS if fps < 100 else 0.0)
    delta = round(ang[-1] - min(ang), 1)
    notes = [f"Manually digitised on {len(pts)} frames; error margin ±{margin:g}° (click precision"
             f"{' + frame timing at ' + format(fps, '.0f') + ' fps' if fps < 100 else ''})."]
    cls = classify(delta, margin)
    if perspective != "side_on":
        notes.append(VIEW_NOTE)
    return ManualLegality(points=[ElbowPoint(frame=p.frame, t=round(p.frame / fps, 3), angle=a) for p, a in zip(pts, ang)],
                          horizontal_frame=pts[0].frame, br_frame=pts[-1].frame, min_angle=min(ang), angle_at_br=ang[-1],
                          net_extension=delta, error_margin=margin, classification=cls, notes=notes, inputs=pts)


def screen(k: Kin, phases: list[PhaseMark], elbow: np.ndarray,
           manual: Optional[ManualElbow] = None) -> tuple[LegalityResult, Optional[float]]:
    """Automatic screening + optional manually verified result. Final verdict prefers the manual one."""
    res, peak = _auto_screen(k, phases, elbow)
    br = res.br_frame
    if br is not None:
        th = res.horizontal_frame if res.horizontal_frame is not None and res.horizontal_frame < br else max(0, br - int(0.2 * k.fps))
        res.suggested_frames = sorted({th, (th + br) // 2, br})
    if manual and len(manual.points) >= 2:
        res.manual = manual_screen(manual.points, k.perspective, k.fps)
        res.final_classification, res.final_source = res.manual.classification, "manual"
    else:
        res.final_classification, res.final_source = res.classification, "auto"
    return res, peak


def _auto_screen(k: Kin, phases: list[PhaseMark], elbow: np.ndarray) -> tuple[LegalityResult, Optional[float]]:
    """Returns (result, peak elbow extension velocity deg/s in [t_h, BR] for the injury screener)."""
    b = k.ids["b"]
    ph = {p.name: p.frame for p in phases}
    ids = [b["sh"], b["el"], b["wr"]]
    conf = k.vis[:, ids].min(axis=1)
    raw = elbow.copy()
    # arm segment lengths vs body proportions (upper arm 0.186 H, forearm 0.146 H, Drillis–Contini):
    # much shorter = arm pointing toward/away from the camera (foreshortened) or wrong landmarks; much longer = glitch
    up_len = np.linalg.norm(k.pt(b["el"]) - k.pt(b["sh"]), axis=1)
    fo_len = np.linalg.norm(k.pt(b["wr"]) - k.pt(b["el"]), axis=1)
    r_up = up_len / (0.186 * k.H) if np.isfinite(k.H) else np.ones(k.n)
    r_fo = fo_len / (0.146 * k.H) if np.isfinite(k.H) else np.ones(k.n)

    def mask(tier: str) -> np.ndarray:
        """Frames whose elbow angle is usable at a given trust tier."""
        vis_min, lo, hi = {
            "high": (VIS_THRESHOLD, T.MIN_SEGMENT_FRAC if k.perspective == "side_on" else T.MIN_SEGMENT_FRAC_FRONT,
                     T.MAX_SEGMENT_FRAC),
            "medium": (VIS_THRESHOLD, T.MIN_SEGMENT_FRAC, T.MAX_SEGMENT_FRAC),
            "low": (0.3, 0.35, 2.0),                                  # only gross glitches removed
        }[tier]
        with np.errstate(invalid="ignore"):
            return (np.isfinite(raw) & (conf >= vis_min) & (r_up >= lo) & (r_fo >= lo) & (r_up <= hi) & (r_fo <= hi))

    ok = mask("high")
    elbow = np.where(ok, raw, np.nan)
    timeline = [ElbowPoint(frame=i, t=round(i / k.fps, 3), angle=round(float(elbow[i]), 1) if ok[i] else None)
                for i in range(k.n)]
    res = LegalityResult(timeline=timeline, disclaimer=T.LEGALITY_DISCLAIMER, br_frame=ph.get("br"))
    notes = res.notes
    if k.perspective != "side_on":
        notes.append("Elbow flexion is best observed side-on; this view foreshortens the arm (larger error margin).")
    if k.fps < 100:
        notes.append(f"{k.fps:.0f} fps: the arm moves ~{int(1500 / k.fps)}° per frame near release; peak values may be missed.")

    br = ph.get("br")
    if br is None:
        res.classification, res.notes = UNAV, notes + ["Ball release frame not available — set it in Video Studio."]
        return res, None

    # truncated release: tracking drops out just after BR (occlusion / blur) -> the real release may not be seen.
    # A confirmed release needs continuous tracking into the follow-through (≥ 0.15 s after BR).
    win_after = range(br + 1, min(br + 1 + max(3, int(0.15 * k.fps)), k.n))
    missing = sum(1 for f in win_after if not np.isfinite(k.P[f, g.L_HIP]).all())
    if missing >= 2:
        notes.append(f"Partial: the bowler was not tracked in {missing} of the {len(win_after)} frames after frame {br} "
                     f"(occlusion or blur), so the verdict uses the arm action up to frame {br}; the real release may "
                     f"be later. Use Manual elbow verification to include it.")

    # upper arm horizontal on the upswing: elevation from hanging-down reaches ~90°
    elev = g.seg_angle(k.pt(b["el"]) - k.pt(b["sh"]), [0.0, -1.0])
    # search a fixed 0.7 s before release (not relative to FFC: a wrong FFC cut the window and hid the bent
    # elbow of a chucked delivery — measured 34° straightening became 0°)
    lo = max(0, br - int(round(T.HORIZONTAL_LOOKBACK_S * k.fps)))
    # ICC: from the point the upper arm reaches horizontal ON THE DELIVERY UPSWING = the LAST upward crossing of
    # horizontal before release. (The first raise in the window is often the gather/loading swing, where a bent
    # elbow is normal and must not count — it produced 35–55° fake 'straightening' on legal bowlers.)
    hz = T.UPPER_ARM_HORIZONTAL
    th = next((i for i in range(br, lo, -1)
               if np.isfinite(elev[i]) and np.isfinite(elev[i - 1]) and elev[i] >= hz > elev[i - 1]), None)
    if th is None:
        th = next((i for i in range(lo, br + 1) if np.isfinite(elev[i]) and elev[i] >= hz), None)
    if th is None:                          # not detected: use the last 0.2 s before release as the window
        th = max(0, br - int(round(0.2 * k.fps)))
        notes.append(f"Arm-horizontal frame not detected; window starts 0.2 s before release (frame {th}).")
    res.horizontal_frame = th

    # Use the most trustworthy elbow frames available; relax step by step instead of refusing.
    win = np.arange(th, br + 1)
    chosen = None
    for tier in ("high", "medium", "low"):
        m = mask(tier)
        valid = win[m[win]]
        br_eff = next((f for f in (br, br - 1, br + 1, br - 2, br + 2) if 0 <= f < k.n and m[f]), None)
        if br_eff is not None and len(valid) >= (T.MIN_ELBOW_FRAMES if tier != "low" else 2):
            chosen = tier
            break
    if chosen is None:
        res.classification = UNAV
        res.notes = notes + [f"No measurable elbow angle between frame {th} and release (frame {br}) — the arm is "
                             f"not visible. Use Manual elbow verification."]
        return res, None
    ok = mask(chosen)
    elbow = np.where(ok, raw, np.nan)
    res.timeline = [ElbowPoint(frame=i, t=round(i / k.fps, 3), angle=round(float(elbow[i]), 1) if ok[i] else None)
                    for i in range(k.n)]
    res.confidence_level = chosen
    excluded = int((np.isfinite(raw[win]) & ~ok[win]).sum())
    if excluded:
        notes.append(f"{excluded} frame(s) in the window excluded (foreshortened arm or landmark error).")
    if chosen != "high":
        notes.append(f"{'Medium' if chosen == 'medium' else 'Low'}-confidence estimate: too few clean elbow frames, so "
                     f"{'the standard arm-length check' if chosen == 'medium' else 'only obvious landmark errors were removed'}"
                     f" ({len(valid)} frames used). Verify with Manual elbow verification if it matters.")

    res.angle_at_horizontal = round(float(elbow[th]), 1) if ok[th] else None
    res.min_angle = round(float(np.min(elbow[valid])), 1)
    res.min_frame, res.br_used = int(valid[np.argmin(elbow[valid])]), int(br_eff)
    res.angle_at_br = round(float(elbow[br_eff]), 1)
    res.net_extension = round(res.angle_at_br - res.min_angle, 1)
    res.error_margin = error_margin(k.perspective, float(np.mean(conf[valid])), k.fps)
    res.classification = classify(res.net_extension, res.error_margin)
    if res.net_extension == 0 and res.min_frame == res.br_used:
        drop = (round(float(np.nanmax(elbow[valid])) - res.angle_at_br, 1)) if len(valid) else 0
        notes.append(f"No straightening: the elbow was most bent AT release ({res.angle_at_br}°). From arm-horizontal "
                     f"to release the measured angle fell by {drop}° (usually 2D foreshortening as the arm rotates), "
                     f"so net extension = 0°.")
    if k.perspective != "side_on":
        notes.append(VIEW_NOTE)
    if br_eff != br:
        notes.append(f"Release frame {br} not confidently visible; used frame {br_eff}.")
    res.notes = notes

    vel = np.abs(derivative(np.where(ok, elbow, np.nan), k.fps))[th:br_eff + 1]
    # elbow angle (and its speed) is only trustworthy side-on -> no elbow stress flag from other views
    peak = float(np.nanmax(vel)) if (k.perspective == "side_on" and chosen == "high"
                                      and np.isfinite(vel).any()) else None
    return res, peak
