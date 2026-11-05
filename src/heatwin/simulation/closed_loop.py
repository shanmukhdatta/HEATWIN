"""Causal sampled-data controller + exact-time Phase 2 nonlinear plant integration.

Controller samples at t=k*Ts; it never sees future plant states. Each intersample
plant integration uses the last zero-order-held command. Exogenous steps split
ODE intervals exactly. Disturbance steps at non-sample instants do not trigger
an unauthorized early controller update; logged rows record the discontinuity.
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from math import floor, isfinite

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

from heatwin.config import PlantParameters
from heatwin.control.controller_config import ControllerSettings
from heatwin.control.pid import ControlOutput, PIDController
from heatwin.models.actuator import hot_mass_flow
from heatwin.models.plant import PlantInputs, rhs, steady_state_for_target
from heatwin.simulation.open_loop import InputStep


class ClosedLoopError(ValueError):
    """Invalid sampled control scenario or failed physical integration."""


def _state(value, *, initial=False) -> np.ndarray:
    try:
        state = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ClosedLoopError("State must have three finite numeric components") from exc
    if state.shape != (3,) or not np.isfinite(state).all():
        raise ClosedLoopError("State must have three finite numeric components")
    if initial and not 0 <= state[2] <= 1:
        raise ClosedLoopError("Initial valve position must be in [0,1]")
    return state.copy()


@dataclass(frozen=True, slots=True)
class SetpointStep:
    time_s: float
    value_c: float

    def __post_init__(self) -> None:
        for name in ("time_s", "value_c"):
            x = getattr(self, name)
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x):
                raise ClosedLoopError(f"{name} must be finite")
        if self.time_s < 0:
            raise ClosedLoopError("Setpoint step time must be nonnegative")


def _validate_events(events, duration: float, label: str) -> tuple:
    ordered = tuple(sorted(events, key=lambda item: item.time_s))
    if len(ordered) > 10000:
        raise ClosedLoopError(f"Too many {label} events")
    previous = -1.0
    for event in ordered:
        if event.time_s > duration or event.time_s == previous:
            raise ClosedLoopError(f"{label} times must be unique and at most duration")
        previous = event.time_s
    return ordered


def simulate_closed_loop(
    params: PlantParameters,
    settings: ControllerSettings,
    *,
    duration_s: float = 420.0,
    initial_setpoint_c: float | None = None,
    setpoint_steps: Sequence[SetpointStep] = (),
    disturbance_steps: Sequence[InputStep] = (),
    initial_state: Sequence[float] | None = None,
    measurement_bias_c: float = 0.0,
    rtol: float = 1e-9,
    atol: float = 1e-11,
) -> pd.DataFrame:
    """Return full sampled control and physical time series with experiment metadata.

    Row at t=0: measurement->controller->command; state still at equilibrium.
    At other sample ticks update using that instant's measurement; at non-grid
    disturbance/setpoint events hold command from the preceding tick.
    Each output is logged at its *current* time, never shifted a future step.
    """
    for name, value in (("duration_s", duration_s), ("rtol", rtol),
                        ("atol", atol), ("measurement_bias_c", measurement_bias_c)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ClosedLoopError(f"{name} must be finite")
    if duration_s <= 0 or rtol < 1e-13 or atol <= 0 or rtol <= 0:
        raise ClosedLoopError("duration_s and tolerances must be positive and rtol >= 1e-13")
    target = params.setpoint if initial_setpoint_c is None else initial_setpoint_c
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not isfinite(target):
        raise ClosedLoopError("initial_setpoint_c must be finite")
    if duration_s / settings.sample_time_s > 100000:
        raise ClosedLoopError("Too many controller samples")
    if any(not isinstance(event, SetpointStep) for event in setpoint_steps):
        raise ClosedLoopError("setpoint_steps require SetpointStep objects")
    if any(not isinstance(event, InputStep) or event.u is not None for event in disturbance_steps):
        raise ClosedLoopError("Disturbances must be InputStep without a valve command")
    sp_events = _validate_events(setpoint_steps, duration_s, "setpoint")
    disturbance_events = _validate_events(disturbance_steps, duration_s, "disturbance")
    equilibrium = steady_state_for_target(target, params)
    state = _state(equilibrium.state if initial_state is None else initial_state,
                           initial=True)
    inputs = PlantInputs.from_params(params, equilibrium.u)
    controller = PIDController(settings)
    controller.initialize(setpoint_c=float(target), measurement_c=float(state[0]) + measurement_bias_c,
                          manual_command=equilibrium.u)
    sample_count = floor(duration_s / settings.sample_time_s)
    ticks = np.arange(sample_count + 1, dtype=float) * settings.sample_time_s
    ticks = ticks[ticks <= duration_s]
    times = np.unique(np.concatenate((ticks, [duration_s],
                                      [e.time_s for e in sp_events],
                                      [e.time_s for e in disturbance_events])))
    samples = set(ticks.tolist())
    sp_index = disturbance_index = 0
    last_output: ControlOutput | None = None
    held_u = float(equilibrium.u)
    records: list[dict] = []
    for i, time in enumerate(times):
        while sp_index < len(sp_events) and sp_events[sp_index].time_s <= time:
            target = sp_events[sp_index].value_c
            sp_index += 1
        updates = {}
        while (disturbance_index < len(disturbance_events)
               and disturbance_events[disturbance_index].time_s <= time):
            event = disturbance_events[disturbance_index]
            updates = {name: getattr(event, name) for name in ("tc_in", "th_in", "mc")
                       if getattr(event, name) is not None} | updates
            disturbance_index += 1
        if updates:
            inputs = replace(inputs, **updates)
        measurement = float(state[0] + measurement_bias_c)
        if time in samples:
            last_output = controller.update(setpoint_c=float(target), measurement_c=measurement)
            held_u = last_output.command
        assert last_output is not None
        inputs = replace(inputs, u=held_u)
        records.append({
            "time_s": float(time), "setpoint_c": float(target),
            "tc_c": float(state[0]), "measurement_c": measurement,
            "th_c": float(state[1]), "error_c": float(target - measurement),
            "u": held_u, "u_raw": last_output.raw_command, "xv": float(state[2]),
            "mh_kg_s": hot_mass_flow(float(state[2]), params),
            "mc_kg_s": inputs.mc, "tc_in_c": inputs.tc_in, "th_in_c": inputs.th_in,
            "q_w": params.ua * float(state[1] - state[0]),
            "p_term": last_output.p_term, "i_term": last_output.i_term,
            "d_term": last_output.d_term, "saturated": last_output.saturated,
            "controller_sample": time in samples,
        })
        if i + 1 == len(times):
            break
        nxt = float(times[i + 1])
        solution = solve_ivp(lambda t, y, interval_inputs=inputs: rhs(t, y, interval_inputs, params), (float(time), nxt),
                             state, method="RK45", rtol=rtol, atol=atol)
        if not solution.success or not np.isfinite(solution.y).all():
            raise ClosedLoopError(f"Closed-loop integration failed at {time:g} seconds")
        state = _state(solution.y[:, -1])
        if state[2] < -1e-7 or state[2] > 1 + 1e-7:
            raise ClosedLoopError("Valve integration left the physical interval")
        state[2] = np.clip(state[2], 0, 1)
    frame = pd.DataFrame.from_records(records)
    frame.attrs = {"parameters": asdict(params), "controller": asdict(settings),
                   "initial_equilibrium": asdict(equilibrium),
                   "initial_state": _state(equilibrium.state if initial_state is None else initial_state).tolist(),
                   "initial_setpoint_c": float(params.setpoint if initial_setpoint_c is None else initial_setpoint_c),
                   "setpoint_steps": [asdict(x) for x in sp_events],
                   "disturbance_steps": [asdict(x) for x in disturbance_events],
                   "simulation": {"duration_s": duration_s, "rtol": rtol, "atol": atol,
                                  "zero_order_hold": True, "measurement_bias_c": measurement_bias_c}}
    return frame
