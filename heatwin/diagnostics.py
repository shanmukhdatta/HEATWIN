"""Open-loop empirical prediction and residual monitoring."""
import numpy as np


def predict_twin(t, command, initial, gain, tau, delay):
    """FOPDT step superposition, assuming a constant initial operating point."""
    t, command = np.asarray(t, float), np.asarray(command, float)
    if len(t) != len(command) or not len(t) or np.any(np.diff(t) <= 0) or tau <= 0 or delay < 0:
        raise ValueError('invalid twin inputs')
    result = np.full(len(t), float(initial))
    for i in range(1, len(t)):
        delta = command[i]-command[i-1]
        if delta:
            elapsed = np.maximum(t[i:]-t[i]-delay, 0)
            result[i:] += gain*delta*(1-np.exp(-elapsed/tau))
    return result


def residual_alarm(residual, threshold=1., persistence=3):
    if threshold <= 0 or persistence < 1:
        raise ValueError('invalid alarm settings')
    count = 0
    alarms = []
    for value in residual:
        count = count+1 if abs(value) > threshold else 0
        alarms.append(count >= persistence)
    return np.array(alarms)
