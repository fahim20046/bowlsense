"""Orchestrates the processing job. Pose runs once (cached .npz); edits re-run only downstream modules."""
import json
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .config import STORAGE_DIR
from .db import Repo
from .modules import kinematics, pose_estimator, report_generator, video_processor
from .schemas import AnalysisReport, Calibration, ManualElbow, ManualTiming, QualityReport, VideoMeta

log = logging.getLogger("bowlsense")
executor = ThreadPoolExecutor(max_workers=1)


def sdir(sid: str) -> Path:
    return STORAGE_DIR / sid


def _save_outputs(sid: str, k, meta: VideoMeta, q: QualityReport, manual: dict) -> AnalysisReport:
    with Repo() as r:
        s = r.get(sid)
        calib = Calibration.model_validate_json(s.calibration) if s.calibration else None
        timing = ManualTiming.model_validate_json(s.manual_timing) if s.manual_timing else None
        elbow = ManualElbow.model_validate_json(s.manual_elbow) if s.manual_elbow else None
        locked = s.view_locked == "1"
    # camera view chosen at upload is often wrong (e.g. front-on uploaded as side-on); unless the user locked it
    # in Overview, analyse with the view detected from the video
    detected = kinematics.estimate_view(k)
    if not locked and detected and detected != k.perspective:
        k.auto_view = (k.perspective, detected)
        k.perspective = detected
    rep, S = report_generator.analyse(sid, k, meta, q, manual, sdir(sid) / "video.mp4", calib, timing, elbow)
    d = sdir(sid)
    (d / "report.json").write_text(rep.model_dump_json(), encoding="utf-8")
    (d / "pose.json").write_text(report_generator.pose_json(k, meta, S).model_dump_json(), encoding="utf-8")
    with Repo() as r:
        r.update(sid, legality_class=rep.legality.final_classification, technique_score=rep.score.total)
    return rep


def process(sid: str):
    d = sdir(sid)
    try:
        with Repo() as r:
            s = r.update(sid, status="processing", stage="normalizing video", progress=0.02)
            arm, persp = s.bowling_arm, s.perspective
            hint = tuple(json.loads(s.bowler_hint)) if s.bowler_hint else None
        src = next(d.glob("upload.*"), None)
        # re-processing an existing session: the browser-safe video is already there
        video = video_processor.make_playable(src, d / "video.mp4") if src else d / "video.mp4"
        meta = video_processor.probe(video)
        blur = video_processor.blur_variance(video)

        def prog(p):
            with Repo() as r:
                r.update(sid, stage="pose estimation", progress=round(0.05 + 0.85 * p, 3))

        if hint:   # [time_s, x_norm, y_norm] -> (frame, x, y)
            hint = (min(int(round(hint[0] * meta.fps)), meta.total_frames - 1), hint[1], hint[2])
        img, world, info = pose_estimator.run_pose(video, prog, arm, hint)
        log.info("session %s bowler tracking: %s", sid, info)
        detected = ~np.isnan(img[:, 0, 0])
        if detected.mean() < 0.1:
            raise video_processor.VideoError("NO_BOWLER_DETECTED: pose found in <10% of frames")
        np.savez_compressed(d / "pose_raw.npz", img=img, world=world)
        key = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
        q = video_processor.quality(meta, blur, float(img[detected][:, key, 2].mean()), float(detected.mean()),
                                    video_processor.duplicate_ratio(video))
        (d / "meta.json").write_text(json.dumps({"meta": meta.model_dump(), "quality": q.model_dump()}), encoding="utf-8")

        with Repo() as r:
            r.update(sid, stage="biomechanics", progress=0.92)
        k = kinematics.build(img, world, meta.fps, meta.height, arm, persp)
        _save_outputs(sid, k, meta, q, {})
        with Repo() as r:
            r.update(sid, status="done", stage="done", progress=1.0)
    except Exception as e:  # noqa: BLE001 — surface any failure to the client
        log.error("session %s failed: %s", sid, traceback.format_exc())
        with Repo() as r:
            r.update(sid, status="failed", stage="failed", error=str(e)[:500])


def recompute(sid: str) -> AnalysisReport:
    """Re-run phase detection + biomechanics with manual phase overrides (no MediaPipe)."""
    d = sdir(sid)
    with Repo() as r:
        s = r.get(sid)
        manual, arm, persp = Repo.phases_of(s), s.bowling_arm, s.perspective
    raw = np.load(d / "pose_raw.npz")
    mq = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    meta, q = VideoMeta(**mq["meta"]), QualityReport(**mq["quality"])
    k = kinematics.build(raw["img"], raw["world"], meta.fps, meta.height, arm, persp)
    return _save_outputs(sid, k, meta, q, manual)


def submit(sid: str):
    executor.submit(process, sid)
