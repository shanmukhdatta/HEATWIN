"""PID tuning correlations for positive-gain FOPDT models.

Parallel gains are returned as (Kp, Ki, Kd). Reaction-curve correlations
are meaningful only for positive effective dead time and lag.
"""

import numpy as np
from scipy.optimize import minimize


def tune(method, gain, tau, delay, closed_loop_tau=None):
    if (
        not np.all(np.isfinite([gain, tau, delay]))
        or gain <= 0
        or tau <= 0
        or delay < 0
    ):
        raise ValueError("positive process gain and lag and nonnegative delay required")
    if method == "imc":
        lam = max(tau, 3 * delay) if closed_loop_tau is None else closed_loop_tau
        if not np.isfinite(lam) or lam <= 0:
            raise ValueError("closed-loop time constant must be positive")
        kp = (tau + delay / 2) / (gain * (lam + delay / 2))
        ti = tau + delay / 2
        td = tau * delay / (2 * tau + delay)
    elif method == "zn":
        if delay <= 0:
            raise ValueError("Ziegler–Nichols requires positive delay")
        kp, ti, td = 1.2 * tau / (gain * delay), 2 * delay, 0.5 * delay
    elif method == "cohen-coon":
        if delay <= 0:
            raise ValueError("Cohen–Coon requires positive delay")
        r = delay / tau
        kp = (1 / gain) / r * (4 / 3 + r / 4)
        ti = delay * (32 + 6 * r) / (13 + 8 * r)
        td = delay * 4 / (11 + 2 * r)
    else:
        raise ValueError("unknown tuning method")
    return kp, kp / ti, kp * td


def optimize_gains(objective, initial=(0.04, 0.001, 0.08)):
    """Bounded derivative-free optimization; objective accepts three gains."""
    bounds = [(0.0, 0.5), (0.0, 0.05), (0.0, 5.0)]
    result = minimize(
        lambda x: float(objective(x)),
        initial,
        method="Nelder-Mead",
        bounds=bounds,
        options={"maxiter": 100, "xatol": 1e-4, "fatol": 1e-2},
    )
    return result
