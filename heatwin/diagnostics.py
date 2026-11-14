"""Open-loop empirical prediction and residual monitoring."""

import numpy as np


def predict_twin(t, command, initial, gain, tau, delay):
    """FOPDT step superposition, assuming a constant initial operating point."""
    t, command = np.asarray(t, float), np.asarray(command, float)
    if (
        len(t) != len(command)
        or not len(t)
        or np.any(np.diff(t) <= 0)
        or not np.all(np.isfinite(t))
        or not np.all(np.isfinite(command))
        or not np.all(np.isfinite([initial, gain, tau, delay]))
        or tau <= 0
        or delay < 0
    ):
        raise ValueError("invalid twin inputs")
    result = np.full(len(t), float(initial))
    for i in range(1, len(t)):
        delta = command[i] - command[i - 1]
        if delta:
            elapsed = np.maximum(t[i:] - t[i] - delay, 0)
            result[i:] += gain * delta * (1 - np.exp(-elapsed / tau))
    return result


def residual_alarm(residual, threshold=1.0, persistence=3):
    residual = np.asarray(residual, float)
    if (
        not np.all(np.isfinite(residual))
        or not np.isfinite(threshold)
        or threshold <= 0
        or not isinstance(persistence, int)
        or persistence < 1
    ):
        raise ValueError("invalid alarm settings")
    count = 0
    alarms = []
    for value in residual:
        count = count + 1 if abs(value) > threshold else 0
        alarms.append(count >= persistence)
    return np.array(alarms)


def detection_metrics(t, alarms, fault_time):
    """Report pre-injection alarm-sample fraction and first post-injection delay."""
    t, alarms = np.asarray(t, float), np.asarray(alarms, bool)
    if len(t) != len(alarms) or not len(t) or np.any(np.diff(t) <= 0):
        raise ValueError("invalid alarm history")
    before = t < fault_time
    after = t >= fault_time
    hits = t[after & alarms]
    return {
        "false_alarm_fraction": float(np.mean(alarms[before]))
        if before.any()
        else None,
        "detection_delay_s": float(hits[0] - fault_time) if len(hits) else None,
    }


def safety_limits(measurements, low=25.0, high=65.0):
    """Boolean process alarm based on observed temperatures, not hidden plant state."""
    values = np.asarray(measurements, dtype=float)
    if (
        not np.all(np.isfinite(values))
        or not np.all(np.isfinite([low, high]))
        or low >= high
    ):
        raise ValueError("invalid safety limits or measurements")
    return (values < low) | (values > high)
