"""FastAPI entrypoint: `uvicorn app.main:app --reload` (from backend/)."""
import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from . import pipeline
from .config import ALLOWED_EXT, CORS_ORIGINS, MAX_UPLOAD_MB
from .db import BowlingSession, Repo
import numpy as np

from .schemas import (AnalysisReport, Arm, Calibration, ComparisonRow, ManualElbow, ManualTiming, PhaseUpdate, SessionSettings, TrendPoint, TrendSeries, Perspective, SessionCreated, SessionStatus,
                      SessionSummary)

app = FastAPI(title="BowlSense AI", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def resume_interrupted_jobs():
    """Sessions left 'queued'/'processing' by a server stop are re-queued so they never stay stuck."""
    with Repo() as r:
        stuck = [s.id for s in r.list() if s.status in ("queued", "processing")]
        for sid in stuck:
            r.update(sid, status="queued", progress=0.0, stage="resumed after restart")
    for sid in stuck:
        pipeline.submit(sid)


def err(status: int, code: str, detail: str):
    raise HTTPException(status, detail={"code": code, "detail": detail})


def _session(sid: str) -> BowlingSession:
    with Repo() as r:
        s = r.get(sid)
    if not s:
        err(404, "NOT_FOUND", "session not found")
    return s


def _ready(sid: str) -> Path:
    s = _session(sid)
    if s.status != "done":
        err(409, "NOT_READY", f"session status is {s.status}")
    return pipeline.sdir(sid)


@app.get("/api/health")
def health():
    return {"status": "ok"}


TRAINING_DIR = Path(__file__).resolve().parents[1] / "training"


@app.get("/api/validation")
def validation():
    """Saved evaluation results: legality vs expert labels, release-frame detector vs annotated releases."""
    def load(name):
        p = TRAINING_DIR / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return {
        "legality": load("legality_results.json"),
        "release": load("release_metrics.json"),
        "legality_dataset": {
            "name": "Illegal Bowling Action Detection dataset (expert-labelled)",
            "source": "https://github.com/Debopom/Illegal-Bowling-Action-Detection",
            "paper": "https://arxiv.org/abs/2610.07223",
            "license": "MIT",
        },
        "release_dataset": {"name": "Annotated broadcast archive (278 ball-release events, 40 videos)",
                            "split": "train/test by video"},
    }


@app.post("/api/sessions", response_model=SessionCreated, status_code=202)
async def create_session(file: UploadFile = File(...), bowling_arm: Arm = Form(...),
                         perspective: Perspective = Form(...), bowler_name: Optional[str] = Form(None),
                         hint_time: Optional[float] = Form(None), hint_x: Optional[float] = Form(None),
                         hint_y: Optional[float] = Form(None)):
    """hint_* = optional click on the bowler (normalized 0–1 coords) for multi-person footage."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        err(400, "INVALID_FILE", f"allowed: {sorted(ALLOWED_EXT)}")
    sid = str(uuid.uuid4())
    d = pipeline.sdir(sid)
    d.mkdir(parents=True)
    dst = d / f"upload{ext}"
    with dst.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    if dst.stat().st_size > MAX_UPLOAD_MB * 2**20:
        shutil.rmtree(d)
        err(400, "INVALID_FILE", f"file > {MAX_UPLOAD_MB} MB")
    with Repo() as r:
        r.add(BowlingSession(id=sid, bowler_name=(bowler_name or None), bowling_arm=bowling_arm,
                             perspective=perspective, filename=file.filename or dst.name,
                             bowler_hint=json.dumps([hint_time, hint_x, hint_y])
                             if None not in (hint_time, hint_x, hint_y) else None))
    pipeline.submit(sid)
    return SessionCreated(session_id=sid)


@app.get("/api/sessions", response_model=list[SessionSummary])
def list_sessions(bowler_name: Optional[str] = None):
    with Repo() as r:
        rows = r.list(bowler_name)
    return [SessionSummary(session_id=s.id, created_at=s.created_at, bowler_name=s.bowler_name,
                           bowling_arm=s.bowling_arm, perspective=s.perspective, status=s.status,
                           technique_score=s.technique_score, legality_class=s.legality_class) for s in rows]


@app.get("/api/sessions/{sid}", response_model=SessionStatus)
def get_status(sid: str):
    s = _session(sid)
    return SessionStatus(session_id=s.id, status=s.status, progress=s.progress, stage=s.stage, error=s.error)


@app.delete("/api/sessions/{sid}", status_code=204)
def delete_session(sid: str):
    _session(sid)
    with Repo() as r:
        r.delete(sid)
    shutil.rmtree(pipeline.sdir(sid), ignore_errors=True)
    return Response(status_code=204)


@app.get("/api/sessions/{sid}/video")
def video(sid: str):
    return FileResponse(_ready(sid) / "video.mp4", media_type="video/mp4")   # Starlette handles Range


@app.get("/api/sessions/{sid}/frames/{idx}.jpg")
def frame(sid: str, idx: int):
    cap = cv2.VideoCapture(str(_ready(sid) / "video.mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, f = cap.read()
    cap.release()
    if not ok:
        err(404, "NOT_FOUND", "frame out of range")
    return Response(cv2.imencode(".jpg", f)[1].tobytes(), media_type="image/jpeg")


@app.get("/api/sessions/{sid}/pose")
def pose(sid: str):
    return FileResponse(_ready(sid) / "pose.json", media_type="application/json")


@app.get("/api/sessions/{sid}/analysis", response_model=AnalysisReport)
def analysis(sid: str):
    return AnalysisReport.model_validate_json((_ready(sid) / "report.json").read_text(encoding="utf-8"))


@app.put("/api/sessions/{sid}/phases", response_model=AnalysisReport)
def update_phases(sid: str, body: PhaseUpdate):
    _ready(sid)
    with Repo() as r:
        s = r.get(sid)
        cur = Repo.phases_of(s)
        for k, v in body.phases.items():
            if v is None:
                cur.pop(k, None)          # null => revert to auto detection
            else:
                cur[k] = int(v)
        r.update(sid, manual_phases=json.dumps(cur))
    return pipeline.recompute(sid)


def _flat(rep: AnalysisReport) -> dict[str, tuple[str, str, Optional[float]]]:
    """key -> (label, unit, value) for comparison/trends (only 'ok' metrics carry values)."""
    out = {"technique_score": ("Technique score", "pts", rep.score.total),
           "elbow_net_extension": ("Net elbow extension", "deg", rep.legality.net_extension),
           "speed_kmh": ("Measured ball speed", "km_h", rep.speed.measured_kmh),
           "manual_kmh": ("Manual-timed ball speed", "km_h", rep.speed.manual_kmh)}
    for c in rep.score.components:
        out[f"score_{c.key}"] = (f"Score: {c.label}", "pts", c.score)
    b = rep.biomechanics
    for m in b.upper_body + b.lower_body + b.posture:
        out[m.key] = (m.label, m.unit, m.value if m.status == "ok" else None)
    return out


def _load(sid: str) -> AnalysisReport:
    return AnalysisReport.model_validate_json((_ready(sid) / "report.json").read_text(encoding="utf-8"))


@app.get("/api/compare", response_model=list[ComparisonRow])
def compare(a: str, b: str):
    """Side-by-side comparison of two deliveries; delta = b − a."""
    fa, fb = _flat(_load(a)), _flat(_load(b))
    rows = []
    for key in fa.keys() | fb.keys():
        label, unit, _ = fa.get(key) or fb[key]
        va = fa[key][2] if key in fa else None
        vb = fb[key][2] if key in fb else None
        if va is None and vb is None:
            continue
        rows.append(ComparisonRow(key=key, label=label, unit=unit, a=va, b=vb,
                                  delta=round(vb - va, 2) if va is not None and vb is not None else None))
    order = list(fa.keys())
    return sorted(rows, key=lambda r: order.index(r.key) if r.key in order else 999)


@app.get("/api/trends", response_model=list[TrendSeries])
def trends(metrics: str, bowler_name: Optional[str] = None):
    """Metric values over time for completed sessions (optionally one bowler)."""
    keys = [k for k in metrics.split(",") if k]
    with Repo() as r:
        rows = [s for s in r.list(bowler_name) if s.status == "done"]
    rows.sort(key=lambda s: s.created_at)
    series = {k: TrendSeries(key=k, label=k, unit="", points=[]) for k in keys}
    for s in rows:
        f = _flat(_load(s.id))
        for k in keys:
            if k in f:
                series[k].label, series[k].unit = f[k][0], f[k][1]
            series[k].points.append(TrendPoint(session_id=s.id, created_at=s.created_at, value=f.get(k, (0, 0, None))[2]))
    return list(series.values())


@app.post("/api/sessions/{sid}/reprocess", response_model=SessionStatus, status_code=202)
def reprocess(sid: str):
    """Re-run bowler tracking + pose on the stored video (e.g. after tracker improvements). Keeps settings/edits."""
    s = _session(sid)
    if s.status in ("queued", "processing"):
        err(409, "NOT_READY", "session is already processing")
    if not (pipeline.sdir(sid) / "video.mp4").exists():
        err(404, "NOT_FOUND", "stored video missing")
    with Repo() as r:
        r.update(sid, status="queued", progress=0.0, stage="queued", error=None)
    pipeline.submit(sid)
    return SessionStatus(session_id=sid, status="queued", progress=0.0, stage="queued")


@app.put("/api/sessions/{sid}/settings", response_model=AnalysisReport)
def update_settings(sid: str, body: SessionSettings):
    """Change camera view / bowling arm after upload; re-analyses from cached pose (no re-upload)."""
    _ready(sid)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "perspective" in fields:
        fields["view_locked"] = "1"          # explicit choice: don't auto-correct the view any more
    if fields:
        with Repo() as r:
            r.update(sid, **fields)
    return pipeline.recompute(sid)


@app.put("/api/sessions/{sid}/legality/manual", response_model=AnalysisReport)
def set_manual_elbow(sid: str, body: Optional[ManualElbow] = None):
    """Manually digitised shoulder/elbow/wrist on key frames (arm horizontal → release). Empty body clears."""
    _ready(sid)
    if body is not None:
        if len(body.points) < 2:
            err(400, "INVALID_MANUAL_ELBOW", "digitise at least 2 frames (arm horizontal and release)")
        for p in body.points:
            if min(np.hypot(*np.subtract(p.shoulder, p.elbow)), np.hypot(*np.subtract(p.wrist, p.elbow))) < 3:
                err(400, "INVALID_MANUAL_ELBOW", f"frame {p.frame}: points too close together")
    with Repo() as r:
        r.update(sid, manual_elbow=body.model_dump_json() if body else None)
    return pipeline.recompute(sid)


@app.put("/api/sessions/{sid}/calibration", response_model=AnalysisReport)
def set_calibration(sid: str, body: Optional[Calibration] = None):
    """2-point pitch calibration (popping creases, 17.68 m). Send null/empty body to clear."""
    _ready(sid)
    if body is not None and np.hypot(body.p2[0] - body.p1[0], body.p2[1] - body.p1[1]) < 20:
        err(400, "INVALID_CALIBRATION", "calibration points must be at least 20 px apart")
    with Repo() as r:
        r.update(sid, calibration=body.model_dump_json() if body else None)
    return pipeline.recompute(sid)


@app.post("/api/sessions/{sid}/speed/manual", response_model=AnalysisReport)
def manual_speed(sid: str, body: Optional[ManualTiming] = None):
    """Manual fallback: release frame -> frame the ball reaches the batter's crease. Empty body clears."""
    _ready(sid)
    if body is not None and body.arrival_frame <= body.release_frame:
        err(400, "INVALID_TIMING", "arrival_frame must be after release_frame")
    with Repo() as r:
        r.update(sid, manual_timing=body.model_dump_json() if body else None)
    return pipeline.recompute(sid)
