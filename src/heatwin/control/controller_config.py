"""Validated parallel-form sampled P/PI/PID controller settings.

Kc: valve fraction / deg C; Ti/Td/tau_filter: seconds; output: fraction.
Ki=Kc/Ti, Kd=Kc*Td. All physical valve commands lie in [0, 1].
"""

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Literal


@dataclass(frozen=True, slots=True)
class ControllerSettings:
    mode: Literal["P", "PI", "PID"]
    kc: float
    sample_time_s: float = 1.0
    ti_s: float | None = None
    td_s: float = 0.0
    filter_tau_s: float = 1.0
    bias: float = 0.4
    lower: float = 0.0
    upper: float = 1.0
    anti_windup: Literal["conditional", "none"] = "conditional"

    def __post_init__(self) -> None:
        if self.mode not in ("P", "PI", "PID"):
            raise ValueError("mode must be P, PI, or PID")
        if self.anti_windup not in ("conditional", "none"):
            raise ValueError("anti_windup must be conditional or none")
        for key in ("kc", "sample_time_s", "td_s", "filter_tau_s", "bias", "lower", "upper"):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
                raise ValueError(f"{key} must be a finite number")
            object.__setattr__(self, key, float(value))
        if self.kc == 0:
            raise ValueError("kc cannot be zero")
        if self.sample_time_s <= 0 or self.filter_tau_s <= 0:
            raise ValueError("sample_time_s and filter_tau_s must be positive")
        if not 0 <= self.lower < self.upper <= 1:
            raise ValueError("output limits must satisfy 0 <= lower < upper <= 1")
        if not self.lower <= self.bias <= self.upper:
            raise ValueError("bias must lie inside output limits")
        if self.td_s < 0 or (self.mode != "PID" and self.td_s != 0):
            raise ValueError("td_s must be nonnegative and used only with PID")
        if self.mode in ("PI", "PID"):
            if (self.ti_s is None or isinstance(self.ti_s, bool)
                    or not isinstance(self.ti_s, Real) or not isfinite(self.ti_s)
                    or self.ti_s <= 0):
                raise ValueError("PI/PID requires a positive finite ti_s")
            object.__setattr__(self, "ti_s", float(self.ti_s))
        elif self.ti_s is not None:
            raise ValueError("P controller cannot specify ti_s")

    @property
    def ki(self) -> float:
        return 0.0 if self.ti_s is None else self.kc / self.ti_s

    @property
    def kd(self) -> float:
        return self.kc * self.td_s if self.mode == "PID" else 0.0
