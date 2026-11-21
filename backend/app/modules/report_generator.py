"""Assembles AnalysisReport + PoseData JSON. Sections for later milestones stay 'Unavailable' (no fake numbers)."""
import numpy as np

from ..core.geometry import CONNECTIONS
from ..schemas import AnalysisReport, PoseData, PoseFrame, QualityReport, VideoMeta
from . import biomechanics_engine as bio
from . import coaching_engine, injury_screener, legality_screener, performance_scorer, phase_detector, speed_analyzer
from .kinematics import Kin, estimate_view


def pose_json(k: Kin, meta: VideoMeta, S) -> PoseData:
    angles = bio.frame_angles(k, S)
    frames = []
    for i in range(k.n):
        row = k.P[i]
        if np.isnan(row).all():
            frames.append(PoseFrame(i=i, t=round(i / k.fps, 4), lm=None, angles=angles[i]))
            continue
        lm = [(round(float(x), 1) if np.isfinite(x) else -1.0,
               round(float(meta.height - y), 1) if np.isfinite(y) else -1.0,
               round(float(k.vis[i, j]), 3) if np.isfinite(x) else 0.0) for j, (x, y) in enumerate(row)]
        frames.append(PoseFrame(i=i, t=round(i / k.fps, 4), lm=lm, angles=angles[i]))
    return PoseData(meta=meta, frames=frames, connections=CONNECTIONS)


def analyse(sid: str, k: Kin, meta: VideoMeta, q: QualityReport, manual: dict, video=None, calib=None, timing=None,
            manual_elbow=None):
    phases = phase_detector.detect(k, manual)
    biomech, S = bio.compute(k, phases)
    warnings = list(q.warnings) + phase_detector.validate_order(phases)
    if not np.isfinite(k.H):
        warnings.append("Stature could not be estimated; normalized metrics unavailable.")
    missing = [p.name for p in phases if p.frame is None]
    if missing:
        warnings.append(f"Phases not detected: {', '.join(missing)} — set them manually in Video Studio.")
    if k.br_source and k.br_source[0] == "model" and not manual.get("br"):
        warnings.append(f"Ball release located by the trained release-detection model (confidence {k.br_source[1]:.2f}).")
    if k.swapped:
        warnings.append(f"Left/right arm labels corrected for frames {k.swapped[0]}–{k.swapped[1]} "
                        f"(the pose model had mirrored the bowling arm around release).")
    if k.dropped:
        warnings.append(f"{k.dropped} frame(s) removed where the skeleton jumped to another person (umpire/batter).")
    view = estimate_view(k)
    names = {"side_on": "Side-on", "front_on": "Front-on", "rear": "Rear"}
    if k.auto_view:
        warnings.insert(0, f"Camera view auto-corrected: uploaded as {names[k.auto_view[0]]}, but the video looks "
                           f"{names[k.auto_view[1]]}, so it was analysed as {names[k.auto_view[1]]}. "
                           f"Change it in Overview if this is wrong.")
    elif view and view != k.perspective:
        warnings.insert(0, f"CAMERA VIEW MISMATCH: the video looks {names[view]}, but {names[k.perspective]} was selected. "
                           f"Many metrics depend on the view — change it in Overview to re-analyse.")
    if k.perspective == "side_on":
        warnings.append("Side-on view: transverse rotation metrics use estimated depth (low reliability).")
    legality, elbow_vel = legality_screener.screen(k, phases, S["elbow_bowl"], manual_elbow)
    injury = injury_screener.screen(biomech, elbow_vel)
    br = next((p.frame for p in phases if p.name == "br"), None)
    speed = speed_analyzer.measure(video, k, br, meta.height, calib, timing) if video else None
    tscore, subs, metrics = performance_scorer.score(biomech, legality)
    perf = coaching_engine.coach(subs, metrics, injury)
    rep = AnalysisReport(session_id=sid, bowling_arm=k.arm, perspective=k.perspective, meta=meta, quality=q,
                         phases=phases, biomechanics=biomech, legality=legality, injury=injury, warnings=warnings,
                         speed_potential=speed_analyzer.potential(biomech), score=tscore, performance=perf,
                         detected_perspective=view,
                         **({"speed": speed} if speed else {}))
    return rep, S
