"""Biomechanical stress screening (DESIGN.md §7.4). Each flag reports the exact measured value + thresholds.
Never computes injury probability."""
from typing import Optional

from .. import thresholds as T
from ..schemas import BiomechanicsReport, InjuryReport, Metric, StressFlag

STATUS_TXT = {"unavailable_low_confidence": "low landmark confidence",
              "unavailable_perspective": "not observable from this camera view",
              "unavailable_not_detected": "phase/landmarks not detected"}


def level(value: float, moderate: float, high: float, direction: str) -> str:
    if direction == ">":
        return "High concern" if value > high else "Moderate concern" if value > moderate else "Low concern"
    return "High concern" if value < high else "Moderate concern" if value < moderate else "Low concern"


def screen(bio: BiomechanicsReport, elbow_ext_velocity: Optional[float]) -> InjuryReport:
    metrics: dict[str, Metric] = {m.key: m for m in bio.upper_body + bio.lower_body + bio.posture}
    flags = []
    for region, key, label, (mod, high), direction, use_abs, why in T.INJURY_RULES:
        unit = "deg_s" if key == "elbow_ext_velocity" else "deg"
        if key == "elbow_ext_velocity":
            value, reason, rel = elbow_ext_velocity, "elbow not tracked from arm-horizontal to release", None
        else:
            m = metrics.get(key)
            value = m.value if m and m.status == "ok" else None
            reason = STATUS_TXT.get(m.status, "not measured") if m else "not measured"
            rel = m.reliability if m else None
        if value is None:
            flags.append(StressFlag(region=region, level="Unavailable", trigger_metric=label, measured=None, unit=unit,
                                    threshold_moderate=mod, threshold_high=high, explanation=f"Unavailable: {reason}."))
            continue
        v = abs(value) if use_abs else value
        lv = level(v, mod, high, direction)
        note = f" (view reliability: {rel})" if rel and rel != "high" else ""
        flags.append(StressFlag(region=region, level=lv, trigger_metric=label, measured=round(v, 1), unit=unit,
                                threshold_moderate=mod, threshold_high=high, explanation=why + note))
    return InjuryReport(flags=flags, disclaimer=T.INJURY_DISCLAIMER, implemented=True)
