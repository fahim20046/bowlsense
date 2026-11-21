"""Vector geometry (DESIGN.md §7.1). All inputs are 2D points in y-UP coords; NaN-safe."""
import numpy as np

NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 0, 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN = 23, 24, 25, 26, 27, 28
L_HEEL, R_HEEL, L_FI, R_FI = 29, 30, 31, 32

CONNECTIONS = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
               (23, 25), (25, 27), (24, 26), (26, 28), (27, 29), (29, 31), (27, 31), (28, 30),
               (30, 32), (28, 32), (0, 11), (0, 12), (15, 17), (15, 19), (16, 18), (16, 20)]


def side(arm: str) -> dict:
    """Landmark ids for bowling side (b), non-bowling side (nb), front leg (f), back leg (k)."""
    R = dict(sh=R_SH, el=R_EL, wr=R_WR, hip=R_HIP, kn=R_KN, an=R_AN, heel=R_HEEL, fi=R_FI)
    L = dict(sh=L_SH, el=L_EL, wr=L_WR, hip=L_HIP, kn=L_KN, an=L_AN, heel=L_HEEL, fi=L_FI)
    b, nb = (R, L) if arm == "right" else (L, R)
    return {"b": b, "nb": nb, "f": nb, "k": b}   # right-arm bowler lands on left (front) foot


def angle3(a, b, c):
    """Unsigned joint angle at b: arccos((a-b)·(c-b)/(|a-b||c-b|)) in degrees. Works on (...,2) arrays."""
    u, v = np.asarray(a) - b, np.asarray(c) - b
    den = np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1)
    cos = np.sum(u * v, axis=-1) / np.where(den == 0, np.nan, den)
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


def seg_angle(v, r):
    """Angle between segment vector v and reference r (degrees)."""
    v = np.asarray(v)
    r = np.broadcast_to(np.asarray(r, float), v.shape)
    den = np.linalg.norm(v, axis=-1) * np.linalg.norm(r, axis=-1)
    cos = np.sum(v * r, axis=-1) / np.where(den == 0, np.nan, den)
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


def tilt(p_right, p_left):
    """Line tilt atan2(dy, dx) of left->right segment, wrapped to [-90, 90]."""
    d = np.asarray(p_right) - p_left
    a = np.degrees(np.arctan2(d[..., 1], d[..., 0]))
    return (a + 90) % 180 - 90


def nan_unwrap(rad):
    """np.unwrap that skips NaNs (plain unwrap turns everything after the first NaN into NaN)."""
    rad = np.asarray(rad, float)
    out = rad.copy()
    ok = np.isfinite(rad)
    out[ok] = np.unwrap(rad[ok])
    return out


def wrap180(a):
    return (np.asarray(a) + 180) % 360 - 180


def cross2(u, v):
    return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]


def yaw(world, right_id, left_id):
    """Transverse rotation from MediaPipe world landmarks: atan2(z_R - z_L, x_R - x_L)."""
    d = world[:, right_id] - world[:, left_id]
    return np.degrees(np.arctan2(d[:, 2], d[:, 0]))
