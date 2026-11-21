import cv2
import numpy as np

from app.modules import ball_tracker, speed_analyzer as sa
from app.schemas import BiomechanicsReport, Calibration, Metric


def _m(key, value, status="ok"):
    return Metric(key=key, label=key, value=value, unit="deg", status=status, confidence=0.9, reliability="high")


def test_band():
    assert sa._band(1.6, 0.5, 1.6) == 1.0 and sa._band(0.5, 0.5, 1.6) == 0.0
    assert sa._band(60, 0, 30, 45, 75) == 0.5


def test_calibration_scale():
    s, e = sa._scale(Calibration(frame=0, p1=(100, 300), p2=(1100, 300)))
    assert abs(s - 17.68 / 1000) < 1e-9 and np.allclose(e, [1, 0])


def test_potential_needs_two_components():
    one = BiomechanicsReport(upper_body=[_m("release_height_br", 1.2)], lower_body=[], posture=[], phase_table={})
    assert sa.potential(one).level == "Unavailable"
    two = BiomechanicsReport(upper_body=[_m("release_height_br", 1.2)], lower_body=[_m("front_knee_delta", 5)],
                             posture=[_m("separation_ffc", None, "unavailable_perspective")], phase_table={})
    p = sa.potential(two)
    assert p.level == "High" and p.scores["separation_ffc"] is None


def test_end_to_end_synthetic_side_on_speed(tmp_path):
    """Synthetic side-on clip: static 'bowler' landmarks + a ball leaving the hand at a known speed.
    100 fps, calibration 1000 px = 17.68 m, ball 12 px/frame -> 12*0.01768*100*3.6 = 76.4 km/h."""
    from app.modules.kinematics import Kin
    from app.core import geometry as g
    n, fps, H_img, W_img = 60, 100.0, 400, 1200
    P = np.full((n, 33, 2), np.nan)
    pose = {0: (300, 330), 11: (290, 300), 12: (310, 300), 13: (285, 260), 14: (315, 330), 15: (280, 230),
            16: (320, 345), 23: (292, 220), 24: (308, 220), 25: (292, 140), 26: (308, 140), 27: (292, 60),
            28: (308, 60), 29: (290, 55), 30: (306, 55), 31: (300, 50), 32: (316, 50)}
    for j, (x, y) in pose.items():
        P[:, j] = (x, y)                                    # y-up coords
    vis = np.zeros((n, 33)); vis[:, list(pose)] = 0.95
    k = Kin(P=P, vis=vis, W=np.zeros((n, 33, 3)), fps=fps, arm="right", perspective="side_on", H=330.0, dx=1.0,
            ids=g.side("right"))
    br, hand = 20, (320, H_img - 345)                       # right wrist (16) in image coords
    path = tmp_path / "syn.mp4"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W_img, H_img))
    for f in range(n):
        im = np.full((H_img, W_img, 3), 70, np.uint8)
        if f > br:
            cv2.circle(im, (int(hand[0] + 12 * (f - br)), hand[1] + (f - br)), 4, (255, 255, 255), -1)
        vw.write(im)
    vw.release()
    calib = Calibration(frame=br, p1=(100, 380), p2=(1100, 380))
    res = sa.measure(path, k, br, H_img, calib, None)
    assert res.status == "ok", res.notes
    assert abs(res.measured_kmh - 76.4) < 3
    assert res.fit_r2 > 0.99


def test_candidates_find_moving_ball():
    frames = [np.full((200, 400), 60, np.uint8) for _ in range(3)]
    for i, f in enumerate(frames):
        cv2.circle(f, (100 + 60 * i, 100), 4, 255, -1)
    c = ball_tracker.candidates(*frames, r=4)
    assert any(abs(x - 160) < 3 and abs(y - 100) < 3 for x, y in c)
