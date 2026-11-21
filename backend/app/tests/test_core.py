import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.core import geometry as g
from app.core.smoothing import smooth_series


def test_angle3_right_angle():
    assert abs(g.angle3(np.array([1.0, 0]), np.array([0.0, 0]), np.array([0.0, 1])) - 90) < 1e-6


def test_angle3_straight():
    assert abs(g.angle3(np.array([-1.0, 0]), np.array([0.0, 0]), np.array([1.0, 0])) - 180) < 1e-6


def test_tilt_and_wrap():
    assert abs(g.tilt(np.array([1.0, 1]), np.array([0.0, 0])) - 45) < 1e-6
    assert g.wrap180(190) == -170


def test_smoothing_keeps_long_gaps_nan():
    x = np.sin(np.linspace(0, 3, 60))
    x[20:22] = np.nan   # short gap -> filled
    x[40:50] = np.nan   # long gap -> stays NaN
    y = smooth_series(x, 7)
    assert np.isfinite(y[20:22]).all() and np.isnan(y[40:50]).all()


def test_identity_jump_frames_dropped():
    from app.modules.kinematics import drop_identity_jumps
    n = 40
    xy = np.full((n, 33, 2), np.nan)
    for f in range(n):                      # bowler running right: hips at y=200, shoulders at y=100
        x = 100 + 5 * f
        xy[f, [23, 24]] = [[x - 5, 200], [x + 5, 200]]
        xy[f, [11, 12]] = [[x - 10, 100], [x + 10, 100]]
    xy[20:23, :, 0] += 400                  # 3 frames switched to an umpire 400 px away
    vis = np.ones((n, 33))
    assert drop_identity_jumps(xy, vis) == 3
    assert np.isnan(xy[20:23]).all() and vis[20:23].max() == 0 and np.isfinite(xy[19, [11, 12, 23, 24]]).all()


def test_overlap_identity_swap_is_repaired():
    """Bowler (moving right) runs past a standing batter; the tracker swaps IDs during the overlap.
    The repaired path must keep following the moving person, not the standing one."""
    from app.modules import person_tracker as pt
    box = lambda x: (x - 20.0, 100.0, x + 20.0, 300.0)
    bowler_x = lambda f: 100 + 5 * f
    t1, t2 = {}, {}
    for f in range(60):
        if f < 30:
            t1[f] = box(bowler_x(f))          # ID 1 = bowler ...
            t2[f] = box(250)                  # ID 2 = batter standing at x=250
        else:                                 # ... IDs swapped after they overlapped (around f=30)
            t1[f] = box(250)
            t2[f] = box(bowler_x(f))
    path, fixes = pt.resolve_overlap_swaps({1: t1, 2: t2}, dict(t1))
    assert fixes == 1
    assert pt._c(path[50])[0] == bowler_x(50)            # still on the moving bowler


def test_api_rejects_no_bowler(tmp_path):
    from app.main import app
    p = tmp_path / "blank.mp4"
    vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 360))
    for _ in range(30):
        vw.write(np.zeros((360, 640, 3), np.uint8))
    vw.release()
    c = TestClient(app)
    with p.open("rb") as fh:
        r = c.post("/api/sessions", files={"file": ("blank.mp4", fh, "video/mp4")},
                   data={"bowling_arm": "right", "perspective": "side_on"})
    assert r.status_code == 202
    sid = r.json()["session_id"]
    for _ in range(120):
        st = c.get(f"/api/sessions/{sid}").json()
        if st["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert st["status"] == "failed" and "NO_BOWLER_DETECTED" in st["error"]
    assert c.get(f"/api/sessions/{sid}/analysis").status_code == 409
    assert c.delete(f"/api/sessions/{sid}").status_code == 204
