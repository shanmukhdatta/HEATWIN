"""First-order step model without dead time, as a comparison to FOPDT."""

import numpy as np
from scipy.optimize import least_squares


def first_order(t, gain, tau):
    return gain * (1 - np.exp(-np.maximum(np.asarray(t), 0) / tau))


def fit_first_order(t, response):
    t, response = np.asarray(t, float), np.asarray(response, float)
    if (
        len(t) < 4
        or len(t) != len(response)
        or np.any(np.diff(t) <= 0)
        or not np.all(np.isfinite(t))
        or not np.all(np.isfinite(response))
    ):
        raise ValueError("invalid identification data")
    result = least_squares(
        lambda p: first_order(t - t[0], *p) - response,
        [response[-1], (t[-1] - t[0]) / 4],
        bounds=([-np.inf, 1e-6], [np.inf, np.inf]),
    )
    return result.x
