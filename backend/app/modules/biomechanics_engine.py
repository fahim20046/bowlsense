"""Phase-dependent biomechanical metrics (DESIGN.md §7.1, table #1–#24)."""
from typing import Optional

import numpy as np

from ..config import VIS_THRESHOLD
from ..core import geometry as g
from ..core.smoothing import derivative
from ..schemas import BiomechanicsReport, Metric, PhaseMark
from .kinematics import Kin

REL = {"sagittal": {"side_on": "high", "front_on": "low", "rear": "low"},
       "frontal": {"side_on": "low", "front_on": "high", "rear": "high"},
       "transverse": {"side_on": "low", "front_on": "reduced", "rear": "reduced"},
       "any": {"side_on": "high", "front_on": "high", "rear": "high"}}       # in-image-plane sway, any view
UP = np.array([0.0, 1.0])
# Physiologically plausible ranges; values outside indicate tracking/projection error -> Unavailable.
PLAUSIBLE = {"trunk_lateral": (-75, 75), "trunk_lean": (-60, 85), "counter_rotation": (0, 90),
             "separation": (-90, 90), "pelvic_drop": (-30, 30), "front_knee_ffc": (60, 200), "front_knee_br": (60, 200),
             "front_knee_delta": (-90, 90), "back_knee": (60, 200),
             "elbow_angle": (40, 195), "shoulder_angle": (0, 180)}
FRAME_SERIES = ["elbow_bowl", "shoulder_bowl", "knee_front", "knee_back", "trunk_lean", "trunk_lateral",
                "front_arm_elev"]


def _signed_knee(k: Kin, leg: dict, theta):
    """Side-on only: knee behind the hip->ankle line (opposite travel) => hyperextension (360 - θ)."""
    if k.perspective != "side_on":
        return theta
    hip, kn, an = k.pt(leg["hip"]), k.pt(leg["kn"]), k.pt(leg["an"])
    c = g.cross2(an - hip, kn - hip)          # >0 * dx => knee forward of the line (normal flexion)
    return np.where(c * k.dx >= 0, theta, 360 - theta)


def series(k: Kin) -> dict[str, tuple[np.ndarray, list[int]]]:
    """name -> (per-frame value, landmark ids used for confidence)."""
    b, nb, f, kk = k.ids["b"], k.ids["nb"], k.ids["f"], k.ids["k"]
    p = k.pt
    T = k.mid(g.L_SH, g.R_SH) - k.mid(g.L_HIP, g.R_HIP)
    lat_sign = (1 if k.perspective == "front_on" else -1) * (1 if k.arm == "right" else -1)
    ground = np.fmin(p(g.L_HEEL)[:, 1], p(g.R_HEEL)[:, 1])
    axis = np.array([k.dx, 0.0]) if k.perspective == "side_on" else UP
    foot = p(f["fi"]) - p(f["heel"])
    sy, hy = g.yaw(k.W, g.R_SH, g.L_SH), g.yaw(k.W, g.R_HIP, g.L_HIP)
    trunk = [g.L_SH, g.R_SH, g.L_HIP, g.R_HIP]
    return {
        "elbow_bowl": (g.angle3(p(b["sh"]), p(b["el"]), p(b["wr"])), [b["sh"], b["el"], b["wr"]]),
        "shoulder_bowl": (g.angle3(p(b["el"]), p(b["sh"]), p(b["hip"])), [b["el"], b["sh"], b["hip"]]),
        "knee_front": (_signed_knee(k, f, g.angle3(p(f["hip"]), p(f["kn"]), p(f["an"]))), [f["hip"], f["kn"], f["an"]]),
        "knee_back": (_signed_knee(k, kk, g.angle3(p(kk["hip"]), p(kk["kn"]), p(kk["an"]))), [kk["hip"], kk["kn"], kk["an"]]),
        "trunk_lean": (np.degrees(np.arctan2(T[:, 0] * k.dx, T[:, 1])), trunk),
        "trunk_lateral": (np.degrees(np.arctan2(T[:, 0] * lat_sign, T[:, 1])), trunk),
        "front_arm_elev": (g.seg_angle(p(nb["el"]) - p(nb["sh"]), -UP), [nb["sh"], nb["el"]]),
        "shoulder_tilt": (g.tilt(p(g.R_SH), p(g.L_SH)), [g.L_SH, g.R_SH]),
        "hip_tilt": (g.tilt(p(g.R_HIP), p(g.L_HIP)), [g.L_HIP, g.R_HIP]),
        "shoulder_yaw": (sy, [g.L_SH, g.R_SH]),
        "hip_yaw": (hy, [g.L_HIP, g.R_HIP]),
        "separation": (g.wrap180(sy - hy), trunk),
        "release_height": ((p(b["wr"])[:, 1] - ground) / k.H, [b["wr"], g.L_HEEL, g.R_HEEL]),
        "wrist_offset": ((p(b["wr"])[:, 0] - p(f["an"])[:, 0]) * k.dx / k.H, [b["wr"], f["an"]]),
        # axis-agnostic: 0° = foot along pitch axis, 90° = perpendicular
        "foot_align": (90 - np.abs(90 - g.seg_angle(foot, axis)), [f["heel"], f["fi"]]),
    }


def com(k: Kin) -> np.ndarray:
    """Segmental centre of mass (Dempster-based weights, segment midpoints)."""
    p, m = k.pt, lambda a, b: (k.pt(a) + k.pt(b)) / 2
    parts = [(p(g.NOSE), .081), ((k.mid(g.L_SH, g.R_SH) + k.mid(g.L_HIP, g.R_HIP)) / 2, .497)]
    for sh, el, wr, hip, kn, an in [(11, 13, 15, 23, 25, 27), (12, 14, 16, 24, 26, 28)]:
        parts += [(m(sh, el), .028), (m(el, wr), .022), (m(hip, kn), .10), (m(kn, an), .061)]
    return sum(w * x for x, w in parts)


class _Builder:
    def __init__(self, k: Kin, ph: dict):
        self.k, self.ph = k, ph

    @staticmethod
    def _plausible(key, value):
        for prefix, (lo, hi) in PLAUSIBLE.items():
            if key.startswith(prefix):
                return lo <= value <= hi
        return True

    def conf(self, frame, ids):
        return float(np.min(self.k.vis[frame, ids]))

    def mk(self, key, label, unit, group, value, conf, phase=None, frame=None, perspective_ok=True):
        rel = REL[group][self.k.perspective]
        if not perspective_ok:
            st, v = "unavailable_perspective", None
        elif value is None or not np.isfinite(value):
            st, v = ("unavailable_not_detected" if conf >= VIS_THRESHOLD else "unavailable_low_confidence"), None
        elif conf < VIS_THRESHOLD or not self._plausible(key, value):
            st, v = "unavailable_low_confidence", None
        else:
            st, v = "ok", round(float(value), 2)
        return Metric(key=key, label=label, value=v, unit=unit, status=st, confidence=round(conf, 3),
                      reliability=rel, phase=phase, frame=frame)

    def at(self, key, label, s, phase, unit, group, perspective_ok=True):
        fr = self.ph.get(phase)
        if fr is None:
            return Metric(key=f"{key}_{phase}", label=label, unit=unit, status="unavailable_not_detected",
                          reliability=REL[group][self.k.perspective], phase=phase)
        vals, ids = s
        # release is often motion-blurred: use the nearest confident frame within ±2 (≈ ±0.07 s at 30 fps)
        if phase == "br" and self.conf(fr, ids) < VIS_THRESHOLD:
            near = [f for f in (fr - 1, fr + 1, fr - 2, fr + 2)
                    if 0 <= f < self.k.n and self.conf(f, ids) >= VIS_THRESHOLD and np.isfinite(vals[f])]
            if near:
                fr = near[0]
        return self.mk(f"{key}_{phase}", label, unit, group, vals[fr], self.conf(fr, ids), phase, fr, perspective_ok)

    def window(self, a, b):
        fa, fb = self.ph.get(a), self.ph.get(b)
        return (fa, fb) if fa is not None and fb is not None and fb > fa else None


def compute(k: Kin, phases: list[PhaseMark]) -> tuple[BiomechanicsReport, dict[str, np.ndarray]]:
    ph = {p.name: p.frame for p in phases}
    S = series(k)
    B = _Builder(k, ph)
    b, nb, f, kk = k.ids["b"], k.ids["nb"], k.ids["f"], k.ids["k"]
    side_on = k.perspective == "side_on"
    up, low, post = [], [], []

    # ---- upper body ----
    for phs in ("gather", "ffc", "br"):
        up.append(B.at("shoulder_angle", f"Bowling shoulder angle ({phs.upper()})", S["shoulder_bowl"], phs, "deg", "sagittal"))
    up.append(B.at("elbow_angle", "Bowling elbow angle (BR)", S["elbow_bowl"], "br", "deg", "sagittal"))
    up.append(B.at("release_height", "Release height / stature", S["release_height"], "br", "ratio", "sagittal"))
    up.append(B.at("wrist_offset", "Wrist ahead of front ankle / stature", S["wrist_offset"], "br", "ratio", "sagittal", side_on))
    for phs in ("ffc", "br"):
        up.append(B.at("front_arm_elev", f"Front arm elevation ({phs.upper()})", S["front_arm_elev"], phs, "deg", "sagittal"))
    w = B.window("ffc", "br")
    v = S["front_arm_elev"][0]
    up.append(B.mk("front_arm_pulldown", "Front arm pull-down Δ (FFC→BR)", "deg", "sagittal",
                   (v[w[0]] - v[w[1]]) if w else None,
                   min(B.conf(w[0], S["front_arm_elev"][1]), B.conf(w[1], S["front_arm_elev"][1])) if w else 0.0, "br", w[1] if w else None))
    for phs in ("bfc", "ffc", "br"):
        up.append(B.at("shoulder_tilt", f"Shoulder alignment tilt ({phs.upper()})", S["shoulder_tilt"], phs, "deg", "frontal"))
        up.append(B.at("shoulder_rot", f"Shoulder transverse rotation ({phs.upper()})", S["shoulder_yaw"], phs, "deg", "transverse"))
    if (w := B.window("ffc", "br")):
        v = k.pt(b["wr"]) - k.pt(b["sh"])
        ang = g.nan_unwrap(np.arctan2(v[:, 1], v[:, 0]))
        om = np.abs(derivative(ang, k.fps))
        lo, hi = max(w[1] - 3, 0), min(w[1] + 3, k.n - 1)
        seg = np.degrees(om[lo:hi + 1])
        up.append(B.mk("arm_ang_speed", "Peak bowling-arm angular speed (near BR)", "deg_s", "sagittal",
                       np.nanmax(seg) if np.isfinite(seg).any() else None, B.conf(w[1], [b["sh"], b["wr"]]), "br", w[1]))

    # ---- lower body ----
    for phs in ("ffc", "br"):
        low.append(B.at("front_knee", f"Front knee angle ({phs.upper()})", S["knee_front"], phs, "deg", "sagittal"))
    kv, kid = S["knee_front"]
    w = B.window("ffc", "br")
    low.append(B.mk("front_knee_delta", "Front knee Δ FFC→BR (+ = extension/brace)", "deg", "sagittal",
                    (kv[w[1]] - kv[w[0]]) if w else None,
                    min(B.conf(w[0], kid), B.conf(w[1], kid)) if w else 0.0, "br", w[1] if w else None))
    low.append(B.at("back_knee", "Back knee angle (BFC)", S["knee_back"], "bfc", "deg", "sagittal"))
    if (w := B.window("bfc", "ffc")):
        seg = S["knee_back"][0][w[0]:w[1] + 1]
        i = int(np.nanargmax(seg)) if np.isfinite(seg).any() else 0
        low.append(B.mk("back_knee_drive", "Back knee max extension (drive, BFC→FFC)", "deg", "sagittal",
                        seg[i] if np.isfinite(seg).any() else None, B.conf(w[0] + i, S["knee_back"][1]), "ffc", w[0] + i))
    for phs in ("bfc", "ffc", "br"):
        low.append(B.at("hip_tilt", f"Hip alignment tilt ({phs.upper()})", S["hip_tilt"], phs, "deg", "frontal"))
        low.append(B.at("hip_rot", f"Hip transverse rotation ({phs.upper()})", S["hip_yaw"], phs, "deg", "transverse"))
    low.append(B.at("foot_align", "Front foot alignment vs pitch axis (FFC)", S["foot_align"], "ffc", "deg", "frontal"))
    if (fr := ph.get("ffc")) is not None:
        ids = [f["an"], kk["an"]]
        stride = abs(k.pt(f["an"])[fr, 0] - k.pt(kk["an"])[fr, 0]) / k.H
        low.append(B.mk("stride_length", "Stride length / stature (FFC)", "ratio", "sagittal", stride, B.conf(fr, ids), "ffc", fr, side_on))
        bf = ph.get("bfc")
        lat = (k.pt(f["an"])[fr, 0] - k.pt(kk["an"])[bf, 0]) / k.H if bf is not None else None
        low.append(B.mk("foot_lateral", "Front foot lateral offset vs back foot / stature", "ratio", "frontal", lat,
                        B.conf(fr, ids), "ffc", fr, not side_on))

    # ---- posture ----
    for phs in ("ffc", "br"):
        # pure-plane trunk angles are not observable from the orthogonal view
        post.append(B.at("trunk_lean", f"Trunk forward lean ({phs.upper()})", S["trunk_lean"], phs, "deg", "sagittal", side_on))
        post.append(B.at("trunk_lateral", f"Trunk lateral flexion ({phs.upper()})", S["trunk_lateral"], phs, "deg", "frontal", not side_on))
    post.append(B.at("separation", "Hip-shoulder separation (FFC)", S["separation"], "ffc", "deg", "transverse"))
    post.append(B.at("separation", "Hip-shoulder separation (BFC)", S["separation"], "bfc", "deg", "transverse"))
    post.append(B.at("pelvic_drop", "Pelvic drop / hip line tilt (FFC)", S["hip_tilt"], "ffc", "deg", "frontal", not side_on))
    if (w := B.window("bfc", "ffc")):
        sy = S["shoulder_yaw"][0]
        d = np.abs(g.wrap180(sy[w[0]:w[1] + 1] - sy[w[0]]))
        post.append(B.mk("counter_rotation", "Shoulder counter-rotation (BFC→FFC)", "deg", "transverse",
                         np.nanmax(d) if np.isfinite(d).any() else None, B.conf(w[0], [g.L_SH, g.R_SH]), "ffc", w[1]))
    if (w := B.window("bfc", "br")):
        n_rel = k.pt(g.NOSE)[w[0]:w[1] + 1] - k.mid(g.L_HIP, g.R_HIP)[w[0]:w[1] + 1]
        sig = np.sqrt(np.nanvar(n_rel[:, 0]) + np.nanvar(n_rel[:, 1])) / k.H * 100
        post.append(B.mk("head_stability", "Head displacement σ BFC→BR (relative to pelvis)", "pct_height", "any",
                         sig, float(np.mean(k.vis[w[0]:w[1] + 1, g.NOSE])), "br", w[1]))
    c = com(k)
    cvx = derivative(c[:, 0], k.fps) * k.dx / k.H
    if (fr := ph.get("bfc")) is not None:
        hv = np.abs(derivative(k.mid(g.L_HIP, g.R_HIP)[:, 0], k.fps)) / k.H
        post.append(B.mk("runup_momentum", "Run-up momentum: hip speed at BFC", "height_per_s", "sagittal",
                         hv[fr], B.conf(fr, [g.L_HIP, g.R_HIP]), "bfc", fr, side_on))
    if (br := ph.get("br")) is not None:
        end = min(br + int(round(0.4 * k.fps)), k.n - 1)
        dt = (end - br) / k.fps
        ids = [g.L_HIP, g.R_HIP, g.L_SH, g.R_SH]
        post.append(B.mk("com_decel", "COM horizontal deceleration BR→+0.4 s", "height_per_s2", "sagittal",
                         (cvx[br] - cvx[end]) / dt if dt > 0 else None, B.conf(end, ids), "follow_through", end, side_on))
        base = k.mid(g.L_AN, g.R_AN)
        post.append(B.mk("balance_offset", "COM ahead of base of support (+0.4 s) / stature", "ratio", "sagittal",
                         (c[end, 0] - base[end, 0]) * k.dx / k.H, B.conf(end, ids + [g.L_AN, g.R_AN]),
                         "follow_through", end, side_on))

    table = {}
    for p in phases:
        if p.frame is None:
            continue
        row = {}
        for name, (vals, ids) in S.items():
            val = vals[p.frame]
            row[name] = round(float(val), 2) if np.isfinite(val) and B.conf(p.frame, ids) >= VIS_THRESHOLD else None
        table[p.name] = row
    return BiomechanicsReport(upper_body=up, lower_body=low, posture=post, phase_table=table), {n: s[0] for n, s in S.items()}


def frame_angles(k: Kin, S: dict[str, np.ndarray]) -> list[dict[str, Optional[float]]]:
    out = []
    for i in range(k.n):
        out.append({n: (round(float(S[n][i]), 1) if np.isfinite(S[n][i]) else None) for n in FRAME_SERIES})
    return out
