"""Technique Score 0–100 with a transparent weighted rubric (DESIGN.md §7.5).
Each component = mean of its available sub-scores; a sub-score maps a measured metric to 0..1 with a
piecewise-linear target band. Unavailable metrics are excluded (never guessed); weights renormalise."""
from typing import Callable, Optional

import numpy as np

from ..schemas import BiomechanicsReport, LegalityResult, Metric, ScoreComponent, TechniqueScore


def band(lo0, lo1, hi1=None, hi0=None) -> Callable[[float], float]:
    """0 at lo0 → 1 from lo1 to hi1 → 0 at hi0. lo0 > lo1 gives a 'lower is better' ramp."""
    def f(v):
        if hi1 is not None and v > hi1:
            return float(np.clip((hi0 - v) / (hi0 - hi1), 0, 1))
        if (lo1 >= lo0 and v >= lo1) or (lo1 < lo0 and v <= lo1):
            return 1.0
        return float(np.clip((v - lo0) / (lo1 - lo0), 0, 1))
    return f


# (metric key, scoring fn, use_abs, target text)
SUB = {
    "front_knee_ffc": (band(120, 160, 185, 200), False, "160–185° (firm landing)"),
    "front_knee_delta": (band(-20, 0), False, "≥ 0° (brace, no collapse)"),
    "separation_ffc": (band(0, 30, 45, 75), True, "30–45°"),
    "counter_rotation": (band(40, 10), True, "≤ 10°"),
    "trunk_lean_br": (band(-10, 15, 45, 70), False, "15–45° forward"),
    "trunk_lateral_br": (band(50, 20), True, "≤ 20°"),
    "release_height_br": (band(0.9, 1.15), False, "≥ 1.15 × stature"),
    "front_arm_elev_ffc": (band(60, 120), False, "≥ 120° (front arm high)"),
    "front_arm_pulldown": (band(0, 60), False, "≥ 60° pull-down"),
    "head_stability": (band(10, 3), False, "≤ 3 % of height"),
    "runup_momentum": (band(0.5, 1.6), False, "≥ 1.6 heights/s"),
    "back_knee_drive": (band(120, 160), False, "≥ 160° drive"),
    "balance_offset": (band(0.4, 0.1), True, "|offset| ≤ 0.1"),
    "elbow_net_extension": (band(15, 5), False, "≤ 5° net extension"),
    "pelvic_drop_ffc": (band(15, 5), True, "|hip tilt| ≤ 5°"),
    "foot_align_ffc": (band(45, 15), True, "≤ 15° to pitch axis"),
}

COMPONENTS = [  # key, label, weight, metric keys
    ("front_leg", "Front-leg brace", 20, ["front_knee_ffc", "front_knee_delta"]),
    ("hip_shoulder", "Hip-shoulder mechanics", 15, ["separation_ffc", "counter_rotation"]),
    ("trunk", "Trunk posture", 15, ["trunk_lean_br", "trunk_lateral_br"]),
    ("arm", "Arm action & release height", 15, ["release_height_br", "front_arm_elev_ffc", "front_arm_pulldown"]),
    ("head", "Head stability", 10, ["head_stability"]),
    ("runup", "Run-up & gather", 5, ["runup_momentum", "back_knee_drive"]),
    ("follow", "Follow-through & balance", 5, ["balance_offset"]),
    ("alignment", "Landing alignment (front/rear view)", 10, ["pelvic_drop_ffc", "foot_align_ffc"]),
    ("elbow", "Elbow action margin", 5, ["elbow_net_extension"]),
]


def metric_map(bio: BiomechanicsReport, legality: LegalityResult) -> dict[str, Metric]:
    m = {x.key: x for x in bio.upper_body + bio.lower_body + bio.posture}
    if legality.manual is not None and legality.manual.classification != "Unavailable":
        m["elbow_net_extension"] = Metric(key="elbow_net_extension", label="Net elbow extension (manually verified)",
                                          unit="deg", value=legality.manual.net_extension, status="ok", confidence=1.0,
                                          reliability="high", frame=legality.manual.br_frame)
    elif legality.net_extension is not None and legality.classification != "Unavailable":
        m["elbow_net_extension"] = Metric(key="elbow_net_extension", label="Net elbow extension", unit="deg",
                                          value=legality.net_extension, status="ok", confidence=1.0, reliability="reduced")
    return m


def sub_scores(metrics: dict[str, Metric]) -> dict[str, Optional[float]]:
    out = {}
    for key, (fn, use_abs, _) in SUB.items():
        m = metrics.get(key)
        # low view-reliability metrics (e.g. sagittal angles from a rear camera) never drive score or coaching
        usable = m and m.status == "ok" and m.reliability != "low"
        out[key] = round(fn(abs(m.value) if use_abs else m.value), 3) if usable else None
    return out


def score(bio: BiomechanicsReport, legality: LegalityResult) -> tuple[TechniqueScore, dict, dict]:
    metrics = metric_map(bio, legality)
    subs = sub_scores(metrics)
    comps, tot_w, acc = [], 0.0, 0.0
    for key, label, w, keys in COMPONENTS:
        avail = [k for k in keys if subs.get(k) is not None]
        based = [f"{metrics[k].label}: {metrics[k].value:g} → {subs[k]:.2f} (target {SUB[k][2]})" for k in avail]
        based += [f"{k}: {'low reliability from this camera view — excluded' if metrics.get(k) and metrics[k].status == 'ok' else 'Unavailable'}"
                  for k in keys if k not in avail]
        s = round(100 * float(np.mean([subs[k] for k in avail])), 1) if avail else None
        comps.append(ScoreComponent(key=key, label=label, weight=w, score=s, based_on=based))
        if s is not None:
            tot_w += w
            acc += w * s
    total = round(acc / tot_w, 1) if tot_w >= 40 else None
    return TechniqueScore(total=total, partial=tot_w < 60, available_weight=tot_w, components=comps), subs, metrics
