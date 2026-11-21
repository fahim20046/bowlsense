"""Landmark gap-fill + Savitzky-Golay smoothing (DESIGN.md §2.3)."""
import numpy as np
from scipy.signal import savgol_filter

MAX_GAP = 3


def _runs(mask):
    """Yield (start, end_exclusive) of True runs."""
    idx = np.flatnonzero(np.diff(np.concatenate(([0], mask.astype(int), [0]))))
    return zip(idx[::2], idx[1::2])


def _fill_short_gaps(x):
    x = x.copy()
    nan = np.isnan(x)
    for s, e in _runs(nan):
        if s > 0 and e < len(x) and e - s <= MAX_GAP:
            x[s:e] = np.interp(np.arange(s, e), [s - 1, e], [x[s - 1], x[e]])
    return x


def window_for(fps: float, seconds: float = 0.10) -> int:
    w = max(5, int(round(fps * seconds)))
    return w if w % 2 else w + 1


def smooth_series(x, window: int, poly: int = 3):
    """Smooth a 1D series with NaN gaps: fill gaps <= MAX_GAP, filter each valid run separately."""
    x = _fill_short_gaps(np.asarray(x, float))
    out = x.copy()
    for s, e in _runs(~np.isnan(x)):
        n = e - s
        if n >= window:
            out[s:e] = savgol_filter(x[s:e], window, poly)
        elif n >= 5:
            w = n if n % 2 else n - 1
            out[s:e] = savgol_filter(x[s:e], w, min(poly, w - 1))
    return out


def smooth_landmarks(coords, vis, fps, thr=0.5):
    """coords (N,33,D), vis (N,33) -> smoothed coords with low-visibility points masked."""
    c = coords.astype(float).copy()
    c[vis < thr] = np.nan
    w = window_for(fps)
    for j in range(c.shape[1]):
        for d in range(c.shape[2]):
            c[:, j, d] = smooth_series(c[:, j, d], w)
    return c


def derivative(x, fps):
    """Central-difference derivative (NaN-propagating) per second."""
    return np.gradient(np.asarray(x, float), axis=0) * fps
