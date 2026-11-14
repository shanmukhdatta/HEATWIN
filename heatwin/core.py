"""Lumped exchanger, sampled controller and empirical identification.

Temperatures are in Celsius, time in seconds, mass flows in kg/s and UA in W/K.
"""

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares


@dataclass(frozen=True)
class Parameters:
    rho: float = 1000.0
    cp: float = 4180.0
    vc: float = 0.001
    vh: float = 0.001
    ua: float = 350.0
    tc_in: float = 30.0
    th_in: float = 80.0
    mc: float = 0.03
    mh_min: float = 0.01
    mh_max: float = 0.1
    valve_tau: float = 4.0

    def __post_init__(self):
        if not all(np.isfinite(v) for v in vars(self).values()):
            raise ValueError("parameters must be finite")
        if (
            min(self.rho, self.cp, self.vc, self.vh, self.ua, self.mc, self.valve_tau)
            <= 0
            or self.mh_min <= 0
            or self.mh_max <= self.mh_min
        ):
            raise ValueError("invalid physical parameters")


def rhs(y, command, p):
    tc, th, valve = y
    mh = p.mh_min + (p.mh_max - p.mh_min) * np.clip(valve, 0, 1)
    q = p.ua * (th - tc)
    return np.array(
        [
            (p.mc * p.cp * (p.tc_in - tc) + q) / (p.rho * p.vc * p.cp),
            (mh * p.cp * (p.th_in - th) - q) / (p.rho * p.vh * p.cp),
            (np.clip(command, 0, 1) - valve) / p.valve_tau,
        ]
    )


def equilibrium(command, p):
    if not 0 <= command <= 1:
        raise ValueError("command must be in [0, 1]")
    mh = p.mh_min + (p.mh_max - p.mh_min) * command
    a, b = p.mc * p.cp, mh * p.cp
    tc, th = np.linalg.solve(
        [[a + p.ua, -p.ua], [-p.ua, b + p.ua]], [a * p.tc_in, b * p.th_in]
    )
    return np.array([tc, th, command])


class PID:
    """Parallel PID: Kp [fraction/K], Ki [fraction/(K s)], Kd [fraction s/K]."""

    def __init__(
        self,
        kp,
        ki,
        kd,
        dt=1.0,
        bias=0.4,
        filter_tau=3.0,
        derivative_on_measurement=True,
    ):
        if (
            not np.all(np.isfinite([kp, ki, kd, dt, bias, filter_tau]))
            or min(kp, ki, kd) < 0
            or dt <= 0
            or filter_tau < 0
        ):
            raise ValueError("invalid PID parameters")
        self.kp, self.ki, self.kd, self.dt, self.bias, self.filter_tau = (
            kp,
            ki,
            kd,
            dt,
            bias,
            filter_tau,
        )
        self.integral = 0.0
        self.previous = None
        self.previous_error = None
        self.derivative_on_measurement = derivative_on_measurement
        self.derivative = 0.0

    def initialize(self, setpoint, measurement, output):
        """Initialize integral state for transfer from manual output to automatic mode."""
        if (
            not np.all(np.isfinite([setpoint, measurement, output]))
            or not 0 <= output <= 1
        ):
            raise ValueError("invalid initialization")
        self.integral = output - self.bias - self.kp * (setpoint - measurement)
        self.previous = measurement
        self.previous_error = setpoint - measurement
        self.derivative = 0.0

    def update(self, setpoint, measurement):
        if not np.all(np.isfinite([setpoint, measurement])):
            raise ValueError("setpoint and measurement must be finite")
        error = setpoint - measurement
        if self.derivative_on_measurement:
            raw_d = (
                0.0
                if self.previous is None
                else -(measurement - self.previous) / self.dt
            )
        else:
            raw_d = (
                0.0
                if self.previous_error is None
                else (error - self.previous_error) / self.dt
            )
        alpha = self.dt / (self.filter_tau + self.dt)
        self.derivative += alpha * (raw_d - self.derivative)
        self.previous = measurement
        self.previous_error = error
        candidate = self.integral + self.ki * error * self.dt
        raw = self.bias + self.kp * error + candidate + self.kd * self.derivative
        if (0 <= raw <= 1) or (raw > 1 and error < 0) or (raw < 0 and error > 0):
            self.integral = candidate
        return float(
            np.clip(
                self.bias + self.kp * error + self.integral + self.kd * self.derivative,
                0,
                1,
            )
        )


def simulate(
    p=Parameters(),
    duration=600,
    dt=1.0,
    gains=(0.04, 0.001, 0.08),
    setpoint=57.0,
    step_time=60.0,
    disturbance=0.0,
    noise=0.0,
    bias=0.0,
    fault_time=300.0,
    degradation=1.0,
    stuck=False,
    seed=42,
    open_loop=False,
    open_loop_value=0.5,
    flow_factor=1.0,
    sensor_drift=0.0,
    noise_at_fault=False,
    initial_state=None,
):
    values = [
        duration,
        dt,
        setpoint,
        step_time,
        disturbance,
        noise,
        bias,
        fault_time,
        degradation,
        open_loop_value,
        flow_factor,
        sensor_drift,
    ]
    if (
        not np.all(np.isfinite(values))
        or duration <= 0
        or dt <= 0
        or noise < 0
        or not 0 < degradation <= 1
        or flow_factor <= 0
        or not 0 <= open_loop_value <= 1
    ):
        raise ValueError("invalid simulation settings")
    rng = np.random.default_rng(seed)
    y = (
        equilibrium(0.4, p)
        if initial_state is None
        else np.asarray(initial_state, dtype=float).copy()
    )
    if y.shape != (3,) or not np.all(np.isfinite(y)) or not 0 <= y[2] <= 1:
        raise ValueError(
            "initial state requires two finite temperatures and a valve position in [0, 1]"
        )
    initial = y[0]
    initial_valve = float(y[2])
    controller = PID(*gains, dt=dt, bias=initial_valve)
    rows = []
    command = initial_valve
    for t in np.arange(0, duration + dt / 2, dt):
        active = t >= fault_time
        sp = setpoint if t >= step_time else initial
        measured = (
            y[0]
            + (bias + sensor_drift * (t - fault_time) if active else 0)
            + rng.normal(0, noise if active or not noise_at_fault else 0.0)
        )
        command = (
            (open_loop_value if t >= step_time else initial_valve)
            if open_loop
            else controller.update(sp, measured)
        )
        current = replace(
            p,
            tc_in=p.tc_in + (disturbance if active else 0),
            ua=p.ua * (degradation if active else 1),
            mc=p.mc * (flow_factor if active else 1),
        )
        rows.append(
            (
                t,
                *y,
                sp,
                measured,
                command,
                current.tc_in,
                current.ua,
                current.mc,
                active,
            )
        )

        def derivative(_, state, command=command, current=current, active=active):
            result = rhs(state, command, current)
            if stuck and active:
                result[2] = 0.0
            return result

        sol = solve_ivp(derivative, (0, dt), y, rtol=1e-8, atol=1e-9)
        if not sol.success or not np.all(np.isfinite(sol.y[:, -1])):
            raise RuntimeError("integration failed")
        y = sol.y[:, -1]
    return pd.DataFrame(
        rows,
        columns=[
            "time",
            "tc",
            "th",
            "valve",
            "setpoint",
            "measurement",
            "command",
            "tc_in",
            "ua",
            "mc",
            "fault_active",
        ],
    )


def fopdt(t, gain, tau, delay):
    return gain * (1 - np.exp(-np.maximum(np.asarray(t) - delay, 0) / tau))


def fit_fopdt(t, y):
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    if (
        len(t) < 4
        or len(t) != len(y)
        or not np.all(np.isfinite(t))
        or not np.all(np.isfinite(y))
        or np.any(np.diff(t) <= 0)
    ):
        raise ValueError("invalid identification data")
    span = t[-1] - t[0]
    fit = least_squares(
        lambda x: fopdt(t - t[0], *x) - y,
        [y[-1], span / 4, 1.0],
        bounds=([-np.inf, 1e-6, 0], [np.inf, np.inf, span]),
    )
    return fit.x


def metrics(t, y, sp, u):
    t, y, sp, u = [np.asarray(v, dtype=float) for v in (t, y, sp, u)]
    if (
        any(v.ndim != 1 or not np.all(np.isfinite(v)) for v in (t, y, sp, u))
        or len(t) < 2
        or any(len(v) != len(t) for v in (y, sp, u))
        or np.any(np.diff(t) <= 0)
    ):
        raise ValueError("invalid metric series")
    e = sp - y
    integrate = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    target = sp[-1]
    change = target - y[0]
    overshoot = (
        max(0.0, float(np.max((y - target) * np.sign(change)))) if change else 0.0
    )
    band = max(abs(change) * 0.02, 0.01)
    outside = np.flatnonzero(np.abs(y - target) > band)
    settling = (
        float(t[outside[-1] + 1] - t[0])
        if len(outside) and outside[-1] + 1 < len(t)
        else (0.0 if not len(outside) else float("nan"))
    )
    reach = (
        np.flatnonzero((y - y[0]) * np.sign(change) >= 0.9 * abs(change))
        if change
        else []
    )
    return {
        "IAE": float(integrate(abs(e), t)),
        "ISE": float(integrate(e * e, t)),
        "ITAE": float(integrate((t - t[0]) * abs(e), t)),
        "overshoot_C": overshoot,
        "settling_s": settling,
        "rise_90_s": float(t[reach[0]] - t[0]) if len(reach) else float("nan"),
        "final_error_C": float(e[-1]),
        "valve_travel": float(np.abs(np.diff(u)).sum()),
    }
