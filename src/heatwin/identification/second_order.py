"""Stable overdamped two-real-pole empirical model (no oscillatory forcing)."""

import numpy as np


def response(time_s, gain: float, tau1_s: float, tau2_s: float, *,
             step_time_s: float, delta_u: float, baseline_c: float = 0.0) -> np.ndarray:
    vals = [gain, tau1_s, tau2_s, step_time_s, delta_u, baseline_c]
    if not np.isfinite(vals).all() or min(tau1_s, tau2_s) <= 0:
        raise ValueError("Second-order model requires finite parameters and positive time constants")
    t = np.asarray(time_s, dtype=float)
    if t.ndim != 1 or not np.isfinite(t).all():
        raise ValueError("time_s must be a finite one-dimensional array")
    elapsed = np.maximum(0.0, t - step_time_s)
    if abs(tau1_s - tau2_s) < 1e-5 * max(tau1_s, tau2_s):
        tau = (tau1_s + tau2_s) / 2
        rise = 1.0 - np.exp(-elapsed / tau) * (1.0 + elapsed / tau)
    else:
        rise = 1.0 - (tau1_s * np.exp(-elapsed / tau1_s)
                       - tau2_s * np.exp(-elapsed / tau2_s)) / (tau1_s - tau2_s)
    return baseline_c + gain * delta_u * rise
