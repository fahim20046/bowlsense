"""Per-frame features for the release-frame detector, computed from the app's kinematic context (Kin), so
training (archive) and inference (user videos) use exactly the same pipeline. Scale-free (÷ stature) and
time-normalised (per second) so resolution and frame rate don't matter. Both arms are described ('raised'
= higher wrist) because side-on pose labels can mirror left/right."""
import numpy as np

from ..core import geometry as g
from ..core.smoothing import derivative
from ..modules.kinematics import Kin

OFFSETS = (-6, -4, -2, -1, 1, 2, 4, 6)          # temporal context (frames) stacked around each frame


def _arm(k: Kin, side: dict):
    S, E, W = k.pt(side["sh"]), k.pt(side["el"]), k.pt(side["wr"])
    head = k.pt(g.NOSE)[:, 1]
    top = np.where(np.isfinite(head), head, k.mid(g.L_SH, g.R_SH)[:, 1] + 0.18 * k.H)
    v = W - S
    ang = g.nan_unwrap(np.arctan2(v[:, 1], v[:, 0]))
    return {
        "wr_head": (W[:, 1] - top) / k.H,                      # wrist height above head
        "wr_sh_x": v[:, 0] * k.dx / k.H, "wr_sh_y": v[:, 1] / k.H,
        "el_sh_y": (E[:, 1] - S[:, 1]) / k.H,
        "elbow": g.angle3(S, E, W),
        "omega": np.abs(np.degrees(derivative(ang, k.fps))),   # arm angular speed (deg/s)
        "wr_speed": np.linalg.norm(derivative(W, k.fps), axis=1) / k.H,
        "wr_vis": k.vis[:, side["wr"]],
    }


def frame_features(k: Kin) -> tuple[np.ndarray, list[str]]:
    b, nb = _arm(k, k.ids["b"]), _arm(k, k.ids["nb"])
    raised_is_b = np.nan_to_num(b["wr_head"], nan=-9) >= np.nan_to_num(nb["wr_head"], nan=-9)
    raised = {key: np.where(raised_is_b, b[key], nb[key]) for key in b}
    other = {key: np.where(raised_is_b, nb[key], b[key]) for key in b}
    hip = k.mid(g.L_HIP, g.R_HIP)
    base = {**{f"r_{key}": v for key, v in raised.items()},
            **{f"o_{key}": v for key, v in other.items()},
            "hip_vx": derivative(hip[:, 0], k.fps) * k.dx / k.H,
            "hip_vy": derivative(hip[:, 1], k.fps) / k.H,
            "trunk_lean": np.degrees(np.arctan2((k.mid(g.L_SH, g.R_SH) - hip)[:, 0] * k.dx,
                                                (k.mid(g.L_SH, g.R_SH) - hip)[:, 1])),
            "feet_y": (np.fmin(k.pt(g.L_AN)[:, 1], k.pt(g.R_AN)[:, 1]) - hip[:, 1]) / k.H,
            "tracked": np.isfinite(hip[:, 0]).astype(float)}
    names = list(base)
    X0 = np.column_stack([base[nm] for nm in names])
    cols, out_names = [X0], list(names)
    ctx = ["r_wr_head", "r_omega", "r_wr_vis", "r_elbow", "r_wr_sh_y", "hip_vx"]
    ci = [names.index(c) for c in ctx]
    for o in OFFSETS:
        sh = np.full((len(X0), len(ci)), np.nan)
        if o < 0:
            sh[-o:] = X0[:o, ci]
        else:
            sh[:-o] = X0[o:, ci]
        cols.append(sh)
        out_names += [f"{c}@{o:+d}" for c in ctx]
    return np.column_stack(cols).astype(np.float32), out_names
