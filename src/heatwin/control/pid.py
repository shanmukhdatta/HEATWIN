"""Causal, discrete parallel P/PI/PID with derivative on measured output.

At tick k: use y[k] and integral state I[k] to calculate u[k].  The
rectangular integral update I[k+1]=I[k]+Ki*e[k]*Ts is *for the next tick*.
Thus initial zero-error regulation is bumpless. A backward-Euler first-order
filtered measurement derivative has no setpoint derivative kick.
"""

from dataclasses import dataclass
from math import isfinite

from heatwin.control.controller_config import ControllerSettings


@dataclass(frozen=True, slots=True)
class ControlOutput:
    command: float
    raw_command: float
    error_c: float
    p_term: float
    i_term: float
    d_term: float
    saturated: bool


class PIDController:
    """One stateful controller per independent experiment; no plant dependency."""

    def __init__(self, settings: ControllerSettings):
        self.settings = settings
        self.reset()

    def reset(self) -> None:
        self.integral = 0.0
        self.filtered_derivative = 0.0
        self.last_measurement: float | None = None
        self.effective_bias = self.settings.bias

    def initialize(self, *, setpoint_c: float, measurement_c: float,
                   manual_command: float | None = None) -> None:
        """Track manual command at transfer, without derivative kick.

        For P-only the bias is adjusted to track; for PI/PID the integral is
        initialized to track while the user-configured bias remains intact.
        """
        self.reset()
        self._check_finite(setpoint_c, measurement_c)
        command = self.settings.bias if manual_command is None else manual_command
        self._check_finite(command)
        if not self.settings.lower <= command <= self.settings.upper:
            raise ValueError("manual_command must lie inside output limits")
        p = self.settings.kc * (setpoint_c - measurement_c)
        if self.settings.mode == "P":
            self.effective_bias = command - p
        else:
            self.integral = command - self.settings.bias - p
        self.last_measurement = float(measurement_c)

    @staticmethod
    def _check_finite(*values: float) -> None:
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and isfinite(v) for v in values):
            raise ValueError("controller inputs must be finite real numbers")

    def update(self, *, setpoint_c: float, measurement_c: float,
               dt_s: float | None = None) -> ControlOutput:
        self._check_finite(setpoint_c, measurement_c)
        dt = self.settings.sample_time_s if dt_s is None else dt_s
        self._check_finite(dt)
        if dt <= 0:
            raise ValueError("dt_s must be positive")
        s = self.settings
        error = setpoint_c - measurement_c
        if self.last_measurement is None:
            self.last_measurement = float(measurement_c)
        # Filter H(s)=s/(tau_f*s+1) discretized by backward Euler.
        if s.mode == "PID" and s.td_s > 0:
            self.filtered_derivative = (
                s.filter_tau_s * self.filtered_derivative
                + (measurement_c - self.last_measurement)
            ) / (s.filter_tau_s + dt)
        else:
            self.filtered_derivative = 0.0
        self.last_measurement = float(measurement_c)
        p = s.kc * error
        d = -s.kd * self.filtered_derivative
        i = self.integral if s.mode in ("PI", "PID") else 0.0
        raw = self.effective_bias + p + i + d
        command = min(s.upper, max(s.lower, raw))
        saturated = raw < s.lower or raw > s.upper
        if s.mode in ("PI", "PID"):
            increment = s.ki * error * dt
            if s.anti_windup == "none" or not (
                (raw >= s.upper and increment > 0)
                or (raw <= s.lower and increment < 0)
            ):
                self.integral += increment
        if not all(isfinite(v) for v in (command, raw, self.integral, d)):
            raise ValueError("Non-finite controller state")
        return ControlOutput(command, raw, error, p, i, d, saturated)
