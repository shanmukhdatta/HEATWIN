"""Idealized first-order, linear-characteristic hot-side control valve.

Valve commands and positions are dimensionless fractions, not percentages.
The command is saturated to [0, 1] before it enters the dynamics;
flow is always bounded by the configured physical minimum and maximum.
"""

from math import isfinite
from numbers import Real

from heatwin.config import PlantParameters


def _finite_real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{name} must be a finite real number.")
    return float(value)


def clamp_fraction(value: float) -> float:
    """Saturate a finite normalized command/position to the interval [0, 1]."""
    return min(1.0, max(0.0, _finite_real(value, "valve fraction")))


def hot_mass_flow(xv: float, params: PlantParameters) -> float:
    """Map actual valve position to hot-water mass flow in kg/s."""
    return params.mh_min + (params.mh_max - params.mh_min) * clamp_fraction(xv)


def valve_derivative(xv: float, u: float, params: PlantParameters) -> float:
    """Return dxv/dt in s^-1; saturated command, unconstrained continuous state.

    A state marginally outside [0,1] is driven back toward the physical range.
    Valid simulation *initial* states must already be within the range.
    """
    value = _finite_real(xv, "valve position")
    return (clamp_fraction(u) - value) / params.valve_tau
