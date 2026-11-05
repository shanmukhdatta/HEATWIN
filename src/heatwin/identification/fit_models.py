"""Bounded, deterministic SciPy least-squares fits on *training data only*.

The caller passes a single-step observation frame; no PlantParameters or
hidden reference-plant coefficients enter the empirical fit.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from heatwin.identification import first_order, fopdt, second_order
from heatwin.identification.validation import error_metrics

ModelKind = Literal["fo", "fopdt", "second_order"]


@dataclass(frozen=True)
class FitResult:
    model: ModelKind
    process_gain: float  # deg C / unit valve fraction
    tau1_s: float
    tau2_s: float | None
    theta_s: float
    training_rmse_c: float
    baseline_c: float
    training_step_amplitude: float
    training_step_time_s: float
    samples_used: int
    optimizer_message: str

    def predict(self, time_s, *, delta_u: float | None = None,
                step_time_s: float | None = None, baseline_c: float | None = None) -> np.ndarray:
        """Predict a *new* single-step experiment in deviation coordinates."""
        du = self.training_step_amplitude if delta_u is None else delta_u
        ts = self.training_step_time_s if step_time_s is None else step_time_s
        base = self.baseline_c if baseline_c is None else baseline_c
        if self.model == "fo":
            return first_order.response(time_s, self.process_gain, self.tau1_s,
                                        step_time_s=ts, delta_u=du, baseline_c=base)
        if self.model == "fopdt":
            return fopdt.response(time_s, self.process_gain, self.tau1_s, self.theta_s,
                                  step_time_s=ts, delta_u=du, baseline_c=base)
        if self.model == "second_order":
            assert self.tau2_s is not None
            return second_order.response(time_s, self.process_gain, self.tau1_s, self.tau2_s,
                                         step_time_s=ts, delta_u=du, baseline_c=base)
        raise ValueError(f"Unknown model: {self.model}")

    def coefficients(self) -> dict:
        """Continuous-time transfer function; FOPDT delay is a separate field."""
        if self.model == "second_order":
            assert self.tau2_s is not None
            den = [self.tau1_s * self.tau2_s, self.tau1_s + self.tau2_s, 1.0]
        else:
            den = [self.tau1_s, 1.0]
        return {"numerator": [self.process_gain], "denominator": den,
                "input_delay_s": self.theta_s, "units": "deg C / valve fraction"}


def _single_step_data(data: pd.DataFrame, step_time_s: float):
    needed = {"time_s", "tc_c", "u"}
    if not needed.issubset(data.columns) or len(data) < 8:
        raise ValueError("Need >=8 step-test rows with time_s, tc_c, u")
    values = data[["time_s", "tc_c", "u"]].to_numpy(dtype=float)
    if not np.all(np.isfinite(values)) or np.any(np.diff(values[:, 0]) <= 0):
        raise ValueError("Data must have finite, strictly increasing times and measurements")
    t, y, u = values.T
    before = t < step_time_s
    after = t >= step_time_s
    if sum(before) < 3 or sum(after) < 8:
        raise ValueError("Insufficient observations before or after step")
    initial_command = float(np.median(u[before]))
    final_command = float(np.median(u[after]))
    if not np.allclose(u[before], initial_command, atol=1e-10) or not np.allclose(
        u[after], final_command, atol=1e-10
    ):
        raise ValueError("Single-step fitter cannot accept multi-step input sequences")
    delta_u = final_command - initial_command
    if abs(delta_u) < 1e-9:
        raise ValueError("Cannot identify gain for a zero valve step")
    baseline_c = float(np.mean(y[before][-min(15, sum(before)) :]))
    dy = float(np.mean(y[after][-min(15, sum(after)) :]) - baseline_c)
    if abs(dy) < 1e-8:
        raise ValueError("Flat output: process parameters unidentifiable")
    return t, y, after, baseline_c, delta_u, dy


def _reaction_curve_initial_guess(t, y, step_time_s, baseline_c, dy):
    """Estimate FOPDT tau/theta from 28.3% and 63.2% reaction-curve crossings.

    For an ideal FOPDT: t_28.3=theta+tau/3 and t_63.2=theta+tau.
    Returns None when crossings are unavailable or numerically degenerate.
    """
    samples = t[t >= step_time_s]
    deviation = np.sign(dy) * (y[t >= step_time_s] - baseline_c)
    crossings = []
    for fraction in (-np.expm1(-1 / 3), -np.expm1(-1.0)):
        indices = np.flatnonzero(deviation >= fraction * abs(dy))
        if not len(indices) or indices[0] == 0:
            return None
        j = indices[0]
        if deviation[j] == deviation[j - 1]:
            return None
        crossing = samples[j - 1] + (
            (fraction * abs(dy) - deviation[j - 1])
            * (samples[j] - samples[j - 1])
            / (deviation[j] - deviation[j - 1])
        )
        crossings.append(float(crossing - step_time_s))
    tau = 1.5 * (crossings[1] - crossings[0])
    theta = crossings[1] - tau
    if not np.isfinite([tau, theta]).all() or tau <= 0:
        return None
    return tau, max(0.0, theta)


def fit_step_response(data: pd.DataFrame, *, model: ModelKind,
                      step_time_s: float, max_nfev: int = 2000) -> FitResult:
    """Fit K/tau[/theta] on post-event data only, then check solver success.

    Estimation never receives a validation frame or analytical plant parameters.
    Operating-point changes must be treated as separate predictive tests.
    """
    if model not in ("fo", "fopdt", "second_order"):
        raise ValueError("model must be fo, fopdt or second_order")
    if not isinstance(max_nfev, int) or max_nfev <= 0:
        raise ValueError("max_nfev must be a positive integer")
    if not isinstance(step_time_s, (float, int)) or not isfinite(step_time_s):
        raise ValueError("step_time_s must be finite")
    t, y, after, y0, du, dy = _single_step_data(data, step_time_s)
    elapsed = float(t[-1] - step_time_s)
    if elapsed <= 0:
        raise ValueError("Step must precede final sample")
    gain_guess = dy / du
    gain_limit = max(5.0, 10.0 * abs(gain_guess))
    # Time-scale bounds tied to recorded sampling and observation horizon.
    min_tau = max(1e-3, np.min(np.diff(t)) / 100)
    max_tau = max(2.0, elapsed * 5.0)
    theta_max = max(0.1, elapsed * 0.75)
    mid_time = max(min_tau * 2, elapsed * 0.2)
    if model == "fo":
        x0 = [gain_guess, mid_time]
        lower, upper = [-gain_limit, min_tau], [gain_limit, max_tau]
    elif model == "fopdt":
        initial = _reaction_curve_initial_guess(t, y, step_time_s, y0, dy)
        guess_tau, guess_theta = (mid_time, elapsed * 0.02) if initial is None else initial
        x0 = [gain_guess, min(max_tau * 0.99, max(min_tau * 1.01, guess_tau)),
              min(theta_max * 0.99, max(0.0, guess_theta))]
        lower, upper = [-gain_limit, min_tau, 0.0], [gain_limit, max_tau, theta_max]
    else:
        x0 = [gain_guess, mid_time / 4, mid_time * 1.25]
        lower = [-gain_limit, min_tau, min_tau]
        upper = [gain_limit, max_tau, max_tau]

    observed = y[after]
    samples = t[after]

    def predict(parameters):
        if model == "fo":
            return first_order.response(samples, parameters[0], parameters[1],
                                        step_time_s=step_time_s, delta_u=du, baseline_c=y0)
        if model == "fopdt":
            return fopdt.response(samples, parameters[0], parameters[1], parameters[2],
                                  step_time_s=step_time_s, delta_u=du, baseline_c=y0)
        return second_order.response(samples, parameters[0], parameters[1], parameters[2],
                                     step_time_s=step_time_s, delta_u=du, baseline_c=y0)

    solution = least_squares(lambda a: predict(a) - observed, x0,
                             bounds=(lower, upper), method="trf", max_nfev=max_nfev,
                             ftol=1e-11, xtol=1e-11, gtol=1e-11)
    if not solution.success or not np.all(np.isfinite(solution.x)) or not np.isfinite(solution.cost):
        raise RuntimeError(f"{model} optimization failed: {solution.message}")
    coeff = solution.x
    tau1, tau2, theta = float(coeff[1]), None, 0.0
    if model == "fopdt":
        theta = float(coeff[2])
    elif model == "second_order":
        tau1, tau2 = sorted((float(coeff[1]), float(coeff[2])))
    return FitResult(
        model=model, process_gain=float(coeff[0]), tau1_s=tau1, tau2_s=tau2,
        theta_s=theta, training_rmse_c=error_metrics(observed, predict(coeff)).rmse,
        baseline_c=y0, training_step_amplitude=du,
        training_step_time_s=float(step_time_s), samples_used=len(observed),
        optimizer_message=solution.message,
    )


def predict_piecewise_steps(fit: FitResult, time_s, *, initial_command: float,
                             baseline_c: float, changes) -> np.ndarray:
    """Superpose deviations from arbitrary piecewise-constant valve *changes*.

    changes are (event_time_s, new_absolute_command), in increasing time.
    The model starts at zero perturbation about initial_command.  This
    superposition is valid for LTI transfer functions around their local point.
    """
    t = np.asarray(time_s, dtype=float)
    if t.ndim != 1 or not np.all(np.isfinite(t)) or not isfinite(baseline_c):
        raise ValueError("Invalid time grid or baseline")
    if not np.isfinite(initial_command) or not 0 <= initial_command <= 1:
        raise ValueError("Invalid initial command")
    result = np.full_like(t, baseline_c, dtype=float)
    previous, previous_time = initial_command, float("-inf")
    for event_time, command in changes:
        if (not np.isfinite([event_time, command]).all() or event_time <= previous_time
                or not 0 <= command <= 1):
            raise ValueError("Commands must be physical and event times strictly increasing")
        result += fit.predict(t, delta_u=command - previous, step_time_s=event_time,
                              baseline_c=0.0)
        previous, previous_time = command, event_time
    return result
