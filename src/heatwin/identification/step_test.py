"""Deterministic, equilibrium-initialized virtual open-loop experiments.

All observations come from the Phase 2 nonlinear plant; no textbook responses
are substituted.  Flow/temperature/actuator signals are preserved in full.
"""

from dataclasses import asdict, dataclass
from math import isfinite

import numpy as np
import pandas as pd

from heatwin.config import PlantParameters
from heatwin.models.plant import SteadyState, steady_state_for_valve
from heatwin.simulation.open_loop import InputStep, simulate_open_loop


@dataclass(frozen=True)
class StepExperiment:
    data: pd.DataFrame
    equilibrium: SteadyState
    final_equilibrium: SteadyState
    metadata: dict

    def export(self, directory, name: str) -> None:
        """Export signals as CSV and full configuration as separate JSON."""
        import json
        from pathlib import Path

        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        self.data.to_csv(target / f"{name}.csv", index=False, float_format="%.15g")
        (target / f"{name}_metadata.json").write_text(
            json.dumps(self.metadata, indent=2, allow_nan=False), encoding="utf-8"
        )


def create_step_experiment(
    params: PlantParameters,
    *,
    u0: float = 0.4,
    delta_u: float = 0.1,
    step_time_s: float = 60.0,
    duration_s: float = 480.0,
    sample_time_s: float | None = None,
    rtol: float = 1e-9,
    atol: float = 1e-11,
    split: str = "training",
) -> StepExperiment:
    """Apply an exact-time, unsaturated command step from an exact equilibrium.

    Step amplitudes taking the command beyond [0, 1] are errors, not silently
    clipped.  The metadata contains analytical references for independent
    physics checks; estimators only receive the data frame.
    """
    for name, value in (("u0", u0), ("delta_u", delta_u),
                        ("step_time_s", step_time_s), ("duration_s", duration_s)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"{name} must be a finite real number")
    if not 0 <= u0 <= 1 or not 0 <= u0 + delta_u <= 1:
        raise ValueError("Both initial and final valve commands must be in [0, 1]")
    if abs(delta_u) < 1e-8:
        raise ValueError("Step amplitude must be nonzero and identifiable")
    if not 0 < step_time_s < duration_s:
        raise ValueError("Require 0 < step_time_s < duration_s")
    initial = steady_state_for_valve(u0, params)
    final = steady_state_for_valve(u0 + delta_u, params)
    data = simulate_open_loop(
        params, duration_s=duration_s, initial_command=u0,
        initial_state=initial.state, steps=[InputStep(step_time_s, u=u0 + delta_u)],
        sample_time_s=sample_time_s, rtol=rtol, atol=atol,
    )
    metadata = {
        "split": split, "source": "Phase 2 nonlinear three-state heat exchanger",
        "initial_operating_point": asdict(initial),
        "reference_final_operating_point": asdict(final),
        "configuration": asdict(params), "step_time_s": step_time_s,
        "initial_command": u0, "final_command": u0 + delta_u,
        "step_amplitude": delta_u, "sample_interval_s": (
            params.sample_time if sample_time_s is None else sample_time_s
        ), "duration_s": duration_s, "rtol": rtol, "atol": atol,
        "signal_units": {
            "time_s": "s", "tc_c": "deg C", "th_c": "deg C", "u": "fraction",
            "xv": "fraction", "mh_kg_s": "kg/s", "q_w": "W",
            "tc_in_c": "deg C", "th_in_c": "deg C", "mc_kg_s": "kg/s",
        },
    }
    return StepExperiment(data, initial, final, metadata)


def measure_process_gain(data: pd.DataFrame, step_time_s: float, *, window_s: float = 20.0) -> float:
    """Estimate ΔTc/Δu using measured pre-step and settled tail averages.

    This is a *data-derived* finite-step gain, not an analytical Jacobian.
    The caller is responsible for ensuring the tail reached steady state.
    """
    needed = {"time_s", "tc_c", "u"}
    if not needed.issubset(data.columns) or data.empty:
        raise ValueError("Missing step-test columns")
    arr = data[["time_s", "tc_c", "u"]].to_numpy(dtype=float)
    if not np.all(np.isfinite(arr)) or np.any(np.diff(arr[:, 0]) <= 0):
        raise ValueError("Non-finite or unordered experimental signals")
    if not 0 < window_s or step_time_s <= 0:
        raise ValueError("Invalid baseline window or step time")
    before = data[(data.time_s < step_time_s) & (data.time_s >= step_time_s - window_s)]
    after = data[data.time_s >= float(data.time_s.iloc[-1]) - window_s]
    if len(before) < 2 or len(after) < 2 or data.time_s.iloc[-1] - step_time_s <= window_s:
        raise ValueError("Insufficient pre-step or settled-tail observations")
    du = float(after.u.mean() - before.u.mean())
    dy = float(after.tc_c.mean() - before.tc_c.mean())
    if abs(du) < 1e-12 or abs(dy) < 1e-9:
        raise ValueError("Near-zero step or flat output: gain is unidentifiable")
    return dy / du
