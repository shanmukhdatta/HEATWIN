"""Deterministic open-loop integration with exact input-discontinuity boundaries.

The ODE solver is stopped and restarted at every commanded step.  This
ensures its internal stages never average a discontinuous right-hand side.
Event rows use right-continuous inputs and continuous physical states.
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from math import floor
from typing import Literal

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from heatwin.config import PlantParameters
from heatwin.models.actuator import _finite_real, clamp_fraction, hot_mass_flow
from heatwin.models.plant import (
    PlantInputs,
    rhs,
    steady_state_for_valve,
    validate_state,
)


class SimulationError(ValueError):
    """Invalid integration settings, inputs or numerical ODE solution."""


@dataclass(frozen=True, slots=True)
class InputStep:
    """Set any listed operating inputs at simulation time `time_s`.

    Unspecified fields retain their previous values.  Time is seconds;
    temperatures deg C; cold-side flow kg/s.  Values take effect at exactly
    `time_s` and the state remains continuous across the step.
    """

    time_s: float
    u: float | None = None
    tc_in: float | None = None
    th_in: float | None = None
    mc: float | None = None

    def __post_init__(self) -> None:
        t = _finite_real(self.time_s, "step time_s")
        if t < 0:
            raise SimulationError("Step time_s must be nonnegative.")
        object.__setattr__(self, "time_s", t)
        if all(getattr(self, name) is None for name in ("u", "tc_in", "th_in", "mc")):
            raise SimulationError("An input step must change at least one operating input.")
        for name in ("u", "tc_in", "th_in", "mc"):
            value = getattr(self, name)
            if value is not None:
                value = _finite_real(value, f"step {name}")
                if name == "mc" and value < 0:
                    raise SimulationError("Step mc must be nonnegative (kg/s).")
                object.__setattr__(self, name, value)


def _positive_finite(value: float, name: str) -> float:
    try:
        number = _finite_real(value, name)
    except ValueError as exc:
        raise SimulationError(str(exc)) from exc
    if number <= 0:
        raise SimulationError(f"{name} must be positive.")
    return number


def _apply_step(conditions: PlantInputs, step: InputStep) -> PlantInputs:
    updates = {
        name: value
        for name in ("u", "tc_in", "th_in", "mc")
        if (value := getattr(step, name)) is not None
    }
    if "u" in updates:
        updates["u"] = clamp_fraction(updates["u"])
    return replace(conditions, **updates)


def simulate_open_loop(
    params: PlantParameters,
    *,
    duration_s: float = 300.0,
    initial_command: float = 0.4,
    initial_state: Sequence[float] | None = None,
    steps: Sequence[InputStep] = (),
    sample_time_s: float | None = None,
    rtol: float = 1e-9,
    atol: float = 1e-11,
    method: Literal["RK45", "DOP853", "Radau", "BDF"] = "RK45",
) -> pd.DataFrame:
    """Return a time-indexed experiment DataFrame from real ODE integration.

    Always includes t=0, t=duration_s, the regular requested sample grid,
    and each non-grid input-step instant.  At a step instant, input columns
    reflect the *new* input; temperature and valve states cannot jump.

    Default initial state is the analytical equilibrium for the *initial*
    command and baseline inlet conditions.  Caller-supplied states are
    checked for physical valve bounds and expected state length.

    Output columns:
      time_s, tc_c, th_c, xv, u, mh_kg_s, q_w, tc_in_c, th_in_c, mc_kg_s.
    DataFrame.attrs contains configuration and solver metadata.
    """
    duration = _positive_finite(duration_s, "duration_s")
    dt = _positive_finite(params.sample_time if sample_time_s is None else sample_time_s,
                          "sample_time_s")
    rel_tol = _positive_finite(rtol, "rtol")
    abs_tol = _positive_finite(atol, "atol")
    if rel_tol < 1e-13:
        raise SimulationError("rtol below 1e-13 is not supported reliably in double precision.")
    if method not in ("RK45", "DOP853", "Radau", "BDF"):
        raise SimulationError("method must be RK45, DOP853, Radau, or BDF.")
    command = clamp_fraction(initial_command)
    base = PlantInputs.from_params(params, command)

    if any(not isinstance(e, InputStep) for e in steps):
        raise SimulationError("All steps must be InputStep objects.")
    events = tuple(sorted(steps, key=lambda event: event.time_s))
    for i, event in enumerate(events):
        if event.time_s > duration:
            raise SimulationError("Step time_s cannot exceed simulation duration_s.")
        if i and event.time_s == events[i - 1].time_s:
            raise SimulationError("Multiple steps at the same time are ambiguous; combine them.")

    if duration / dt > 1_000_000 or len(events) > 100_000:
        raise SimulationError("Requested output grid or event count is too large.")
    sample_count = floor(duration / dt)
    if sample_count > 1_000_000:
        raise SimulationError("Requested output grid or event count is too large.")
    regular = np.arange(sample_count + 1, dtype=float) * dt
    regular = regular[regular <= duration]
    times = np.unique(np.concatenate((regular, [duration],
                                      [event.time_s for event in events])))
    states = np.empty((len(times), 3), dtype=float)
    states[0] = validate_state(
        steady_state_for_valve(command, params).state if initial_state is None else initial_state,
        initial=True,
    )

    # Apply the t=0 step to the input, but not the previously initialized state.
    conditions = base
    event_index = 0
    if events and events[0].time_s == 0.0:
        conditions = _apply_step(conditions, events[0])
        event_index = 1

    boundaries = [0.0, *[event.time_s for event in events if 0 < event.time_s < duration],
                  duration]
    current_state = states[0].copy()

    # For every solver interval the operating inputs remain constant.
    for start, stop in zip(boundaries[:-1], boundaries[1:], strict=True):
        solution = solve_ivp(
            lambda t, y, interval_inputs=conditions: rhs(t, y, interval_inputs, params),
            (start, stop),
            current_state,
            method=method,
            dense_output=True,
            rtol=rel_tol,
            atol=abs_tol,
        )
        if not solution.success or solution.sol is None:
            raise SimulationError(f"ODE integration failed at t={start:g}-{stop:g}s: {solution.message}")
        positions = np.flatnonzero((times > start) & (times <= stop))
        if len(positions):
            states[positions] = solution.sol(times[positions]).T
        current_state = np.asarray(solution.y[:, -1], dtype=float)
        if not np.all(np.isfinite(current_state)):
            raise SimulationError(f"Non-finite integrated state at t={stop:g}s.")
        while event_index < len(events) and events[event_index].time_s == stop:
            conditions = _apply_step(conditions, events[event_index])
            event_index += 1
        # Record input transitions at each output instant in a single pass below.

    # Audit all integrated stages we expose: a solver error is never silently
    # fixed by the actuator's saturated flow mapping.
    if not np.all(np.isfinite(states)):
        raise SimulationError("Integrated state contains non-finite values.")
    if np.any(states[:, 2] < -1e-7) or np.any(states[:, 2] > 1.0 + 1e-7):
        raise SimulationError("Numerical valve position violated physical [0,1] limits.")
    states[:, 2] = np.clip(states[:, 2], 0.0, 1.0)

    conditions = base
    event_index = 0
    condition_rows = []
    for t in times:
        while event_index < len(events) and events[event_index].time_s <= t:
            conditions = _apply_step(conditions, events[event_index])
            event_index += 1
        condition_rows.append(conditions)

    data = pd.DataFrame({
        "time_s": times,
        "tc_c": states[:, 0],
        "th_c": states[:, 1],
        "xv": states[:, 2],
        "u": [item.u for item in condition_rows],
        "mh_kg_s": [hot_mass_flow(xv, params) for xv in states[:, 2]],
        "q_w": params.ua * (states[:, 1] - states[:, 0]),
        "tc_in_c": [item.tc_in for item in condition_rows],
        "th_in_c": [item.th_in for item in condition_rows],
        "mc_kg_s": [item.mc for item in condition_rows],
    })
    data.attrs = {
        "parameters": asdict(params),
        "initial_command": command,
        "initial_state": states[0].tolist(),
        "steps": [asdict(event) for event in events],
        "solver": {"method": method, "rtol": rel_tol, "atol": abs_tol,
                   "sample_time_s": dt, "duration_s": duration},
    }
    return data
