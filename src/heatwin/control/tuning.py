"""Named reaction-curve Ziegler–Nichols and IMC/SIMC-type tuning rules.

The process gain is deg C / normalized command fraction (not %).  Controller
Kc is its reciprocal (fraction/deg C). No gain is silently re-estimated.
"""

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from heatwin.control.controller_config import ControllerSettings


@dataclass(frozen=True, slots=True)
class ProcessModel:
    process_gain: float
    tau_s: float
    theta_s: float
    nominal_u: float
    nominal_tc_c: float
    sample_time_s: float

    def __post_init__(self) -> None:
        for name in ("process_gain", "tau_s", "theta_s", "nominal_u",
                     "nominal_tc_c", "sample_time_s"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not isfinite(v):
                raise ValueError(f"{name} must be finite")
        if (self.process_gain == 0 or self.tau_s <= 0 or self.theta_s < 0
                or self.sample_time_s <= 0 or not 0 < self.nominal_u < 1):
            raise ValueError("Invalid FOPDT process model")


def load_identified_model(path: str | Path) -> ProcessModel:
    """Read the actual Phase 3 model artifact; never substitute model guesses."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        op = raw["operating_point"]
        if raw["selected_model"] != "FOPDT":
            raise ValueError("Selected Phase 3 model must be FOPDT")
        return ProcessModel(raw["process_gain"], raw["time_constant_s"],
                            raw["effective_dead_time_s"], op["u"], op["tc"],
                            raw["sampling_interval_s"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load Phase 3 identification artifact: {exc}") from exc


def manual_p(model: ProcessModel, *, gain_fraction: float = 0.5) -> ControllerSettings:
    """Conservative explicit teaching heuristic: Kc*Kprocess = gain_fraction.

    This is not optimized tuning. The documented starting value 0.5 is an
    assumed dimensionless loop sensitivity, not an estimated plant parameter.
    """
    if not isfinite(gain_fraction) or gain_fraction <= 0:
        raise ValueError("gain_fraction must be positive")
    return ControllerSettings("P", gain_fraction / model.process_gain,
                              sample_time_s=model.sample_time_s, bias=model.nominal_u)


def manual_pi(model: ProcessModel, *, gain_fraction: float = 0.5) -> ControllerSettings:
    """Conservative teaching baseline: Kc=0.5/Kprocess, Ti=tau_process."""
    p = manual_p(model, gain_fraction=gain_fraction)
    return ControllerSettings("PI", p.kc, sample_time_s=p.sample_time_s,
                              ti_s=model.tau_s, bias=model.nominal_u)


def ziegler_nichols(model: ProcessModel, *, mode: str) -> ControllerSettings:
    """Classical open-loop Z-N reaction-curve tuning (not ultimate gain)."""
    if mode not in ("P", "PI", "PID"):
        raise ValueError("ZN mode must be P, PI or PID")
    if model.theta_s <= 1e-8 * model.tau_s:
        raise ValueError("ZN reaction-curve tuning requires nonzero usable dead time")
    factor = {"P": 1.0, "PI": 0.9, "PID": 1.2}[mode]
    kc = factor * model.tau_s / (model.process_gain * model.theta_s)
    ti = None if mode == "P" else (3.33 if mode == "PI" else 2.0) * model.theta_s
    td = 0.5 * model.theta_s if mode == "PID" else 0.0
    return ControllerSettings(mode, kc, ti_s=ti, td_s=td,
                              sample_time_s=model.sample_time_s,
                              filter_tau_s=max(model.sample_time_s, td / 10),
                              bias=model.nominal_u)


def imc_pi(model: ProcessModel, *, lambda_s: float) -> ControllerSettings:
    """SIMC-style PI: Kc=tau/[K(lambda+theta)], Ti=min(tau,4(lambda+theta))."""
    if isinstance(lambda_s, bool) or not isinstance(lambda_s, (int, float)) or not isfinite(lambda_s) or lambda_s <= 0:
        raise ValueError("lambda_s must be finite and positive")
    summation = lambda_s + model.theta_s
    kc = model.tau_s / (model.process_gain * summation)
    ti = min(model.tau_s, 4 * summation)
    return ControllerSettings("PI", kc, ti_s=ti, sample_time_s=model.sample_time_s,
                              bias=model.nominal_u)
