"""First-order zero-state *deviation* step responses and characteristic method."""

import numpy as np


def response(time_s, gain: float, tau_s: float, *, step_time_s: float,
             delta_u: float, baseline_c: float = 0.0) -> np.ndarray:
    """Absolute Tc prediction from ΔTc=K Δu (1-exp(-t/tau)), for t>=step."""
    if not np.isfinite([gain, tau_s, step_time_s, delta_u, baseline_c]).all() or tau_s <= 0:
        raise ValueError("FO parameters must be finite with tau_s > 0")
    t = np.asarray(time_s, dtype=float)
    if t.ndim != 1 or not np.isfinite(t).all():
        raise ValueError("time_s must be a finite one-dimensional array")
    elapsed = np.maximum(0.0, t - step_time_s)
    return baseline_c + gain * delta_u * (-np.expm1(-elapsed / tau_s))


def time_constant_632(time_s, output_c, *, step_time_s: float,
                      baseline_c: float | None = None, final_c: float | None = None) -> float:
    """Interpolate 63.2% crossing relative to the actual step event.

    Approximate on a higher-order response; invalid/nonmonotone responses
    that do not cross the expected level are rejected.
    """
    t = np.asarray(time_s, dtype=float)
    y = np.asarray(output_c, dtype=float)
    if t.ndim != 1 or y.shape != t.shape or len(t) < 4 or not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)) or np.any(np.diff(t) <= 0):
        raise ValueError("Expected aligned, ordered, finite time and output arrays")
    past = t < step_time_s
    after = t >= step_time_s
    if not np.any(past) or np.sum(after) < 3:
        raise ValueError("Missing baseline or post-step samples")
    y0 = float(y[past][-1]) if baseline_c is None else float(baseline_c)
    yf = float(y[-1]) if final_c is None else float(final_c)
    dy = yf - y0
    if abs(dy) < 1e-9:
        raise ValueError("Flat response: cannot determine a time constant")
    direction = np.sign(dy)
    y_post = y[after]
    if np.min(direction * np.diff(y_post)) < -1e-5 * abs(dy):
        raise ValueError("63.2% method requires a monotonic response")
    threshold = y0 + (1 - np.exp(-1)) * dy
    ta, ya = t[after], y_post
    crossed = np.flatnonzero(direction * (ya - threshold) >= 0)
    if not len(crossed) or crossed[0] == 0:
        raise ValueError("63.2% threshold was not crossed after the event")
    j = crossed[0]
    crossing = ta[j-1] + (threshold-ya[j-1])*(ta[j]-ta[j-1])/(ya[j]-ya[j-1])
    return float(crossing - step_time_s)
