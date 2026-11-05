"""First-order-plus-effective-dead-time deviation step response."""

import numpy as np


def response(time_s, gain: float, tau_s: float, theta_s: float, *,
             step_time_s: float, delta_u: float, baseline_c: float = 0.0) -> np.ndarray:
    if (not np.isfinite([gain, tau_s, theta_s, step_time_s, delta_u, baseline_c]).all()
            or tau_s <= 0 or theta_s < 0):
        raise ValueError("FOPDT parameters must be finite; tau_s > 0, theta_s >= 0")
    t = np.asarray(time_s, dtype=float)
    if t.ndim != 1 or not np.isfinite(t).all():
        raise ValueError("time_s must be a finite one-dimensional array")
    age = np.maximum(0.0, t - step_time_s - theta_s)
    return baseline_c + gain * delta_u * (-np.expm1(-age / tau_s))
