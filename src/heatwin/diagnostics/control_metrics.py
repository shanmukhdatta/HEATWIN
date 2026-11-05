"""Numerically defined tracking and effort metrics on an observed time window.

IAE [deg C*s], ISE [deg C^2*s], ITAE [deg C*s^2]. ITAE starts at
window_start_s, not absolute simulation time. Saturation duration uses the
zero-order-held interval status; other integrals use trapezoidal quadrature.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.integrate import trapezoid


@dataclass(frozen=True)
class ControlMetrics:
    iae_c_s: float
    ise_c2_s: float
    itae_c_s2: float
    overshoot_c: float | None
    undershoot_c: float | None
    rise_time_s: float | None
    settling_time_s: float | None
    observed_final_error_c: float
    max_command: float
    total_command_movement: float
    total_valve_movement: float
    saturation_duration_s: float

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_control(data: pd.DataFrame, *, window_start_s: float = 0.0,
                     reference_initial_c: float | None = None,
                     band_c: float = 0.10) -> ControlMetrics:
    """Windowed metrics. Settling requires staying within band to final sample.

    Setpoint-step overshoot/undershoot are signed relative to step direction;
    undefined for a zero step. For varying references, rise/settling/overshoot
    are intentionally left undefined (None), not misleading summary values.
    """
    needed = {"time_s", "error_c", "setpoint_c", "tc_c", "u", "xv", "saturated"}
    if not needed.issubset(data.columns):
        raise ValueError("Missing required control columns")
    if not np.isfinite([window_start_s, band_c]).all() or band_c <= 0:
        raise ValueError("Invalid metric window or tolerance")
    window = data.loc[data.time_s >= window_start_s]
    if len(window) < 2:
        raise ValueError("Metrics require at least two samples in the window")
    columns = ["time_s", "error_c", "setpoint_c", "tc_c", "u", "xv"]
    x = window[columns].to_numpy(dtype=float)
    if not np.isfinite(x).all() or np.any(np.diff(x[:, 0]) <= 0):
        raise ValueError("Metrics require finite, strictly increasing samples")
    if (window.saturated.isna().any()
            or not window.saturated.isin([True, False]).all()):
        raise ValueError("Saturation status must be Boolean")
    t, e, sp, y, u, xv = x.T
    elapsed = t - float(window_start_s)
    iae = float(trapezoid(np.abs(e), t))
    ise = float(trapezoid(e**2, t))
    itae = float(trapezoid(elapsed * np.abs(e), t))
    # Match the piecewise-constant command behavior of the closed-loop engine.
    sat_duration = float(np.sum(np.diff(t) * window.saturated.to_numpy(dtype=bool)[:-1]))
    over = under = rise = settle = None
    if np.allclose(sp, sp[0], atol=1e-10) and reference_initial_c is not None:
        if not np.isfinite(reference_initial_c):
            raise ValueError("reference_initial_c must be finite")
        magnitude = sp[0] - reference_initial_c
        if abs(magnitude) > 1e-9:
            direction = np.sign(magnitude)
            deviations = direction * (y - sp[0])
            over = float(max(0.0, np.max(deviations)))
            under = float(max(0.0, -np.min(deviations)))
            # Rise time is the 10-to-90% crossing interval after a setpoint change.
            progress = direction * (y - reference_initial_c) / abs(magnitude)
            crosses = []
            for threshold in (0.1, 0.9):
                ids = np.flatnonzero(progress >= threshold)
                if len(ids):
                    j = int(ids[0])
                    if j == 0:
                        crossing = t[0]
                    else:
                        crossing = float(t[j-1] + (threshold - progress[j-1])
                                         * (t[j] - t[j-1]) / (progress[j] - progress[j-1]))
                    crosses.append(crossing)
            if len(crosses) == 2:
                rise = crosses[1] - crosses[0]
        outside = np.flatnonzero(np.abs(y - sp) > band_c)
        if not len(outside):
            settle = 0.0
        elif outside[-1] < len(t) - 1:
            settle = float(t[outside[-1] + 1] - window_start_s)
    return ControlMetrics(
        iae, ise, itae, over, under, rise, settle, float(e[-1]),
        float(np.max(u)), float(np.sum(np.abs(np.diff(u)))),
        float(np.sum(np.abs(np.diff(xv)))), sat_duration,
    )
