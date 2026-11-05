"""Two-lumped-capacitance water-to-water heat-exchanger energy balances.

State y = [Tc (deg C), Th (deg C), xv (fraction)].  Both fluid-side
capacities are rho * volume * cp (J/K).  No PID or predictive-twin
components belong in this reference-plant module.
"""

from dataclasses import dataclass
from math import isfinite

import numpy as np
from numpy.typing import ArrayLike, NDArray

from heatwin.config import PlantParameters
from heatwin.models.actuator import _finite_real, clamp_fraction, hot_mass_flow, valve_derivative


class ModelError(ValueError):
    """Invalid state, process conditions, or infeasible steady-state request."""


@dataclass(frozen=True, slots=True)
class PlantInputs:
    """Operating inputs held piecewise constant over integration intervals.

    u is normalized command (saturated to [0,1] in the actuator),
    temperatures are deg C, and mc is cold-side mass flow in kg/s.
    """

    u: float
    tc_in: float
    th_in: float
    mc: float

    def __post_init__(self) -> None:
        for name in ("u", "tc_in", "th_in", "mc"):
            value = _finite_real(getattr(self, name), name)
            object.__setattr__(self, name, value)
        if self.mc < 0:
            raise ModelError("mc must be nonnegative (kg/s).")

    @classmethod
    def from_params(cls, params: PlantParameters, u: float) -> "PlantInputs":
        """Use inlet conditions from an already validated configuration."""
        return cls(u=u, tc_in=params.tc_in, th_in=params.th_in, mc=params.mc)


@dataclass(frozen=True, slots=True)
class SteadyState:
    """Steady water temperatures and actuator/energy operating point."""

    tc: float  # deg C
    th: float  # deg C
    xv: float  # fraction
    u: float  # fraction
    mh: float  # kg/s
    q: float  # W, positive hot to cold

    @property
    def state(self) -> NDArray[np.float64]:
        """Exact state ordering for rhs and the open-loop integrator."""
        return np.array([self.tc, self.th, self.xv], dtype=float)


def validate_state(y: ArrayLike, *, initial: bool = False) -> NDArray[np.float64]:
    """Validate a three-component finite numeric state.

    The *initial* valve position must be physical.  Intermediate solver
    stages are not constrained because adaptive Runge-Kutta interpolation
    may stray by machine precision; the flow mapping always clips them.
    """
    try:
        unconverted = np.asarray(y)
        if unconverted.shape != (3,) or unconverted.dtype.kind not in "iuf":
            raise ModelError("State must be three finite numbers [Tc, Th, xv].")
        arr = np.asarray(unconverted, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ModelError("State must be three finite numbers [Tc, Th, xv].") from exc
    if not np.all(np.isfinite(arr)):
        raise ModelError("State must contain only finite numbers.")
    if initial and not 0.0 <= arr[2] <= 1.0:
        raise ModelError("Initial actual valve position xv must be within [0, 1].")
    return arr


def heat_transfer_rate(tc: float, th: float, params: PlantParameters) -> float:
    """Q = UA*(Th-Tc), W; positive Q denotes hot-to-cold heat flow."""
    return params.ua * (_finite_real(th, "th") - _finite_real(tc, "tc"))


def rhs(
    t: float, y: ArrayLike, inputs: PlantInputs, params: PlantParameters
) -> NDArray[np.float64]:
    """d[Tc, Th, xv]/dt from the first law of thermodynamics.

    `t` is present for scipy.solve_ivp compatibility; the equations are
    autonomous for constant inputs.  The return shape is always (3,).
    """
    _finite_real(t, "simulation time")
    tc, th, xv = validate_state(y)
    mh = hot_mass_flow(xv, params)
    q = heat_transfer_rate(tc, th, params)
    cc = params.rho * params.vc * params.cp
    ch = params.rho * params.vh * params.cp
    dtc = (inputs.mc * params.cp * (inputs.tc_in - tc) + q) / cc
    dth = (mh * params.cp * (inputs.th_in - th) - q) / ch
    dxv = valve_derivative(xv, inputs.u, params)
    return np.array([dtc, dth, dxv], dtype=float)


def steady_state_for_valve(
    u: float, params: PlantParameters, *, inputs: PlantInputs | None = None
) -> SteadyState:
    """Analytical equilibrium for a fixed commanded valve fraction.

    Solves the two linear heat balances exactly via Cramer's rule; a unique
    equilibrium exists when at least one stream has positive mass flow.
    Optional inputs customize inlet conditions/cold flow; their `u` is
    ignored in favor of the explicit function argument.
    """
    valve = clamp_fraction(u)
    conditions = inputs or PlantInputs.from_params(params, valve)
    mh = hot_mass_flow(valve, params)
    a = conditions.mc * params.cp
    b = mh * params.cp
    h = params.ua
    denom = a * b + h * (a + b)
    if not isfinite(denom) or denom <= 0:
        raise ModelError("No unique equilibrium when both stream mass flows are zero.")
    tc = (a * conditions.tc_in * (b + h) + h * b * conditions.th_in) / denom
    th = (b * conditions.th_in * (a + h) + h * a * conditions.tc_in) / denom
    if not (isfinite(tc) and isfinite(th)):
        raise ModelError("Non-finite steady-state temperatures.")
    return SteadyState(tc=tc, th=th, xv=valve, u=valve, mh=mh,
                       q=heat_transfer_rate(tc, th, params))


def steady_state_for_target(
    target_tc: float, params: PlantParameters, *, inputs: PlantInputs | None = None
) -> SteadyState:
    """Analytically invert the balances for required flow and valve setting.

    Raises ModelError for a target outside available valve-flow limits,
    insufficient cold flow, or degenerate hot-side driving temperature.
    """
    target = _finite_real(target_tc, "target cold outlet temperature")
    conditions = inputs or PlantInputs.from_params(params, 0.0)
    if conditions.mc <= 0:
        raise ModelError("Target inversion requires positive cold-side mass flow.")
    q = conditions.mc * params.cp * (target - conditions.tc_in)
    th = target + q / params.ua
    driving = conditions.th_in - th
    if abs(driving) <= 1e-12:
        raise ModelError("Target is infeasible: hot-side driving temperature is zero.")
    mh = q / (params.cp * driving)
    # Absolute margin is for finite floating point roundoff at boundaries,
    # not a physical tolerance for unattainable setpoints.
    flow_slack = 1e-12 * max(1.0, params.mh_max)
    if not isfinite(mh) or mh < params.mh_min - flow_slack or mh > params.mh_max + flow_slack:
        raise ModelError(
            f"Target {target:g} deg C requires hot flow {mh:g} kg/s, "
            f"outside [{params.mh_min:g}, {params.mh_max:g}] kg/s."
        )
    mh = min(params.mh_max, max(params.mh_min, mh))
    valve = (mh - params.mh_min) / (params.mh_max - params.mh_min)
    return SteadyState(tc=target, th=th, xv=valve, u=valve, mh=mh, q=q)
