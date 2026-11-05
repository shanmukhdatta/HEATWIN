"""Unit-safe prediction error metrics; never silently divide by zero."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ErrorMetrics:
    mae: float
    rmse: float
    max_abs_error: float
    fit_percent: float | None


def error_metrics(reference, prediction) -> ErrorMetrics:
    true = np.asarray(reference, dtype=float)
    predicted = np.asarray(prediction, dtype=float)
    if true.ndim != 1 or true.shape != predicted.shape or not len(true):
        raise ValueError("Predictions and references must have matching nonempty 1D shapes")
    if not np.isfinite(true).all() or not np.isfinite(predicted).all():
        raise ValueError("Prediction and reference must be finite")
    diff = true - predicted
    denominator = np.linalg.norm(true - true.mean())
    fit_percent = None if denominator <= 1e-12 else 100.0 * (1 - np.linalg.norm(diff)/denominator)
    return ErrorMetrics(mae=float(np.mean(np.abs(diff))),
                        rmse=float(np.sqrt(np.mean(diff**2))),
                        max_abs_error=float(np.max(np.abs(diff))),
                        fit_percent=None if fit_percent is None else float(fit_percent))
