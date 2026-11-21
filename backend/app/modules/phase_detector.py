"""Kinematic heuristics for the 7 delivery phases (DESIGN.md §2.4). Manual overrides win."""
from typing import Optional

import numpy as np

from ..core import geometry as g
from ..core.smoothing import derivative
from ..schemas import PHASE_ORDER, PhaseMark
from .kinematics import Kin

STANCE_SPEED = 0.6      # foot speed threshold, statures / s
MIN_STANCE = 2          # frames


def _foot_point(k: Kin, leg: dict):
    return np.nanmean(np.stack([k.pt(leg["an"]), k.pt(leg["heel"]), k.pt(leg["fi"])]), axis=0)


def stance_onsets(k: Kin, leg: dict) -> list[int]:
    fp = _foot_point(k, leg)
    speed = np.linalg.norm(derivative(fp, k.fps), axis=1) / k.H
    still = np.nan_to_num(speed, nan=np.inf) < STANCE_SPEED
    idx = np.flatnonzero(np.diff(np.concatenate(([0], still.astype(int), [0]))))
    return [int(s) for s, e in zip(idx[::2], idx[1::2]) if e - s >= MIN_STANCE and s > 0]


ARM_VERTICAL_MIN = 0.6  # release requires the bowling arm to be near-vertical and extended


def arm_vertical_index(k: Kin) -> np.ndarray:
    """(W−S)_y / (|S−E| + |E−W|): ≈1 when the bowling arm is straight and vertical (release),
    ~0.3 when hands are tucked at the gather."""
    b = k.ids["b"]
    S, E, W = k.pt(b["sh"]), k.pt(b["el"]), k.pt(b["wr"])
    arm = np.linalg.norm(S - E, axis=1) + np.linalg.norm(E - W, axis=1)
    return (W[:, 1] - S[:, 1]) / np.where(arm > 0, arm, np.nan)


def wrist_heights(k: Kin) -> tuple[np.ndarray, np.ndarray]:
    """Height of the (bowling, non-bowling) wrist above the head, in statures. Head falls back to
    shoulder-mid + 0.18 stature when the head is out of frame."""
    head = k.pt(g.NOSE)[:, 1]
    top = np.where(np.isfinite(head), head, k.mid(g.L_SH, g.R_SH)[:, 1] + 0.18 * k.H)
    return ((k.pt(k.ids["b"]["wr"])[:, 1] - top) / k.H, (k.pt(k.ids["nb"]["wr"])[:, 1] - top) / k.H)


def side_on_confirmed(k: Kin) -> bool:
    """Side-on selected AND the video looks side-on (guards the side-on-only label corrections against a
    wrong view choice at upload)."""
    from .kinematics import estimate_view
    return k.perspective == "side_on" and estimate_view(k) in (None, "side_on")


def release_search_start(k: Kin) -> int:
    """Skip the early run-up: first 25% of the frames where the bowler is actually tracked
    (not of the whole clip — long follow-throughs / intros would push the window past the release)."""
    tracked = np.flatnonzero(np.isfinite(k.P[:, g.L_HIP, 0]))
    if len(tracked) < 10:
        return int(0.3 * k.n)
    return int(tracked[0] + 0.25 * (tracked[-1] - tracked[0]))


PAIRS = [(11, 12), (13, 14), (15, 16), (17, 18), (19, 20), (21, 22), (23, 24), (25, 26), (27, 28),
         (29, 30), (31, 32), (1, 4), (2, 5), (3, 6), (7, 8), (9, 10)]


def _swap_frame(k: Kin, f: int):
    for a, b_ in PAIRS:
        for arr in (k.P, k.W, k.vis):
            arr[f, [a, b_]] = arr[f, [b_, a]]


def fix_arm_label_swap(k: Kin, br: Optional[int]) -> bool:
    """Side-on only: MediaPipe sometimes mirrors left/right. Anchor = release, where the bowling arm is the
    raised one. Then walk backward and forward through the delivery window (≈ 0.6 s before, 0.4 s after) and,
    frame by frame, keep whichever labelling makes the bowling elbow+wrist continue smoothly from the previous
    (already corrected) frame. Handles flips that start mid-delivery. Returns True if any frame was relabelled."""
    if br is None or not side_on_confirmed(k):
        return False
    b, nb = k.ids["b"], k.ids["nb"]
    hb, hn = wrist_heights(k)
    lo, hi = max(0, br - 2), min(k.n, br + 3)
    peak = lambda h: float(np.nanmax(h[lo:hi])) if np.isfinite(h[lo:hi]).any() else -np.inf
    if peak(hn) > peak(hb) + 0.1:           # at release the raised arm carries the non-bowling label
        _swap_frame(k, br)
        swapped = [br]
    else:
        swapped = []
    # cover the whole legality window (arm-horizontal can be up to ~0.3 s before FFC, i.e. ~0.6–0.9 s before BR)
    w0, w1 = max(0, br - int(1.0 * k.fps)), min(k.n - 1, br + int(0.4 * k.fps))

    def arm(f, ids):
        return np.concatenate([k.P[f, ids["el"]], k.P[f, ids["wr"]]])

    for rng in (range(br - 1, w0 - 1, -1), range(br + 1, w1 + 1)):
        prev = br
        for f in rng:
            ref = arm(prev, b)
            keep, cross = arm(f, b), arm(f, nb)
            if not (np.isfinite(ref).all() and np.isfinite(keep).all() and np.isfinite(cross).all()):
                if np.isfinite(keep).all():
                    prev = f
                continue
            if np.linalg.norm(cross - ref) + 0.05 * k.H < np.linalg.norm(keep - ref):
                _swap_frame(k, f)
                swapped.append(f)
            prev = f
    if swapped:
        k.swapped = (min(swapped), max(swapped))
    return bool(swapped)


def detect_br(k: Kin) -> Optional[int]:
    """Release frame = rule-based detector for the rough location, refined by the trained model within
    ±0.5 s (the model was trained on 4.5 s windows around releases, so it is most reliable near one).
    If the rule finds nothing, the model searches all tracked frames. No model file -> rule only."""
    rule = detect_br_rule(k)
    if not USE_ML:
        return rule
    from ..ml import release_model
    p = release_model.release_probabilities(k)
    if p is None:
        return rule
    if rule is not None:
        r = int(round(0.5 * k.fps))
        lo, hi = max(0, rule - r), min(len(p), rule + r + 1)
    else:
        lo, hi = release_search_start(k), len(p)
    if hi <= lo:
        return rule
    f = lo + int(np.argmax(p[lo:hi]))
    if p[f] < release_model.MIN_PROB:
        k.br_source = ("rule", round(float(p[f]), 3))
        return rule
    k.br_source = ("model", round(float(p[f]), 3))
    return f


USE_ML = True


def _arm_omega(k: Kin, side: dict) -> np.ndarray:
    """Angular speed (deg/s) of the shoulder→wrist line, lightly smoothed."""
    v = k.pt(side["wr"]) - k.pt(side["sh"])
    w = np.abs(np.degrees(derivative(g.nan_unwrap(np.arctan2(v[:, 1], v[:, 0])), k.fps)))
    return np.convolve(np.nan_to_num(w, nan=0.0), np.ones(3) / 3, mode="same")


def detect_br_rule(k: Kin) -> Optional[int]:
    """Release = end of the LAST run of frames where the bowling wrist is clearly above the head
    (gather has hands near the chin; follow-through has the arm below the shoulder). If the hand then
    vanishes in motion blur, advance up to ~0.07 s into that gap. Head height falls back to
    shoulder-mid + 0.18 stature when the head is out of frame. Fallback: most vertical arm."""
    b = k.ids["b"]
    hb, hn = wrist_heights(k)
    # side-on: MediaPipe often mirrors left/right, so accept either wrist; other views: bowling wrist only
    if side_on_confirmed(k):
        # either wrist may be the bowling one (mirrored labels) — but the FRONT arm is also held high at the
        # gather/FFC. Release = the raised arm WHIPPING over: require high angular speed about the shoulder.
        height = np.fmax(hb, hn)
        use_b = np.nan_to_num(hb, nan=-9) >= np.nan_to_num(hn, nan=-9)
        omega = np.where(use_b, _arm_omega(k, k.ids["b"]), _arm_omega(k, k.ids["nb"]))
    else:
        height = hb
        omega = _arm_omega(k, b)
    up = height > 0.08
    up[: release_search_start(k)] = False
    if up.any() and np.isfinite(omega[up]).any():
        fast = omega >= 0.5 * np.nanmax(omega[up])          # front arm held up = slow; delivery arm = fast
        if (up & fast).any():
            up &= fast
    idx = np.flatnonzero(up)
    if len(idx):
        height = np.where(up, height, -np.inf)
        end = int(np.argmax(height))                          # straight arm at the top of the circle
        blur = (k.vis[:, b["wr"]] < 0.3) & (k.vis[:, b["sh"]] >= 0.5)
        g_ = 0
        while end + 1 + g_ < k.n and blur[end + 1 + g_] and g_ < max(1, int(round(0.07 * k.fps))):
            g_ += 1
        return end + (g_ + 1) // 2
    s = arm_vertical_index(k)
    s[: release_search_start(k)] = np.nan
    if not np.isfinite(s).any() or np.nanmax(s) < ARM_VERTICAL_MIN:
        return None
    return int(np.nanargmax(s))


def _conf(k: Kin, frame, ids):
    return float(np.min(k.vis[frame, ids])) if frame is not None else 0.0


def detect(k: Kin, manual: dict | None = None) -> list[PhaseMark]:
    manual = {p: f for p, f in (manual or {}).items() if f is not None}
    f, kk, b = k.ids["f"], k.ids["k"], k.ids["b"]
    auto: dict[str, Optional[int]] = {p: None for p in PHASE_ORDER}

    br = manual.get("br", detect_br(k))
    fix_arm_label_swap(k, br)
    auto["br"] = br
    if br is not None:
        ffc = manual["ffc"] if "ffc" in manual else next((s for s in reversed(stance_onsets(k, f)) if s <= br), None)
        auto["ffc"] = ffc
        if ffc is not None:
            bfc = manual["bfc"] if "bfc" in manual else next((s for s in reversed(stance_onsets(k, kk)) if s < ffc), None)
            auto["bfc"] = bfc
            if bfc is not None:
                lo = max(0, bfc - int(0.6 * k.fps))
                hy = k.mid(g.L_HIP, g.R_HIP)[lo:bfc, 1]
                auto["gather"] = int(lo + np.nanargmax(hy)) if bfc > lo and np.isfinite(hy).any() else None
            # MSR: peak shoulder transverse angular velocity in [FFC, BR]
            psi = g.nan_unwrap(np.radians(g.yaw(k.W, g.R_SH, g.L_SH)))
            w = np.abs(derivative(psi, k.fps))[ffc: br + 1]
            auto["msr"] = int(ffc + np.nanargmax(w)) if len(w) and np.isfinite(w).any() else None
    auto["run_up"] = 0
    auto["follow_through"] = min(br + 1, k.n - 1) if br is not None else None
    for p, fr in manual.items():
        auto[p] = fr

    conf_ids = {"run_up": [g.L_HIP, g.R_HIP], "gather": [g.L_HIP, g.R_HIP], "bfc": [kk["an"], kk["heel"]],
                "ffc": [f["an"], f["heel"]], "msr": [g.L_SH, g.R_SH], "br": [b["sh"], b["el"], b["wr"]],
                "follow_through": [g.L_HIP, g.R_HIP]}
    return [PhaseMark(name=p, frame=auto[p], t=round(auto[p] / k.fps, 3) if auto[p] is not None else None,
                      confidence=round(_conf(k, auto[p], conf_ids[p]), 3),
                      source="manual" if p in manual else "auto") for p in PHASE_ORDER]


def validate_order(phases: list[PhaseMark]) -> list[str]:
    seq = [(p.name, p.frame) for p in phases if p.name in ("gather", "bfc", "ffc", "msr", "br") and p.frame is not None]
    return [f"Phase order issue: {a} ({fa}) after {b_} ({fb})." for (a, fa), (b_, fb) in zip(seq, seq[1:]) if fa > fb]
