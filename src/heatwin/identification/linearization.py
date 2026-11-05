"""Exact local three-state Jacobian and transfer function of the Phase 2 plant.

Interior valve operating points only: derivatives of clipped valve behavior
are not defined in the classical sense at 0 and 1.
"""

from dataclasses import dataclass

import numpy as np
from scipy.linalg import expm
from scipy.signal import StateSpace, TransferFunction

from heatwin.config import PlantParameters
from heatwin.models.plant import PlantInputs, SteadyState, rhs, steady_state_for_valve


@dataclass(frozen=True)
class LocalModel:
    equilibrium: SteadyState
    A: np.ndarray
    B: np.ndarray
    C: np.ndarray
    D: np.ndarray
    numerator: np.ndarray  # monic third-order denominator; no delay
    denominator: np.ndarray
    poles: np.ndarray
    process_gain: float

    def scipy_state_space(self) -> StateSpace:
        return StateSpace(self.A, self.B, self.C, self.D)

    def scipy_transfer_function(self) -> TransferFunction:
        return TransferFunction(self.numerator, self.denominator)

    def predict_step(self, time_s, *, delta_u: float, step_time_s: float,
                     baseline_c: float | None = None) -> np.ndarray:
        """Exact three-pole local LTI step response via matrix exponential."""
        t = np.asarray(time_s, dtype=float)
        if t.ndim != 1 or not np.isfinite(t).all() or not np.isfinite([delta_u, step_time_s]).all():
            raise ValueError("Invalid prediction input")
        base = self.equilibrium.tc if baseline_c is None else float(baseline_c)
        if not np.isfinite(base):
            raise ValueError("Invalid baseline")
        # A is nonsingular and Hurwitz for the nominal positive-flow case.
        inv_b = np.linalg.solve(self.A, self.B).reshape(3)
        step_shape = np.array([
            (self.C @ ((expm(self.A * max(0.0, float(ti - step_time_s)))
                        - np.eye(3)) @ inv_b)).item() if ti >= step_time_s else 0.0
            for ti in t
        ])
        return base + float(delta_u) * step_shape


def linearize_at_valve(params: PlantParameters, u0: float) -> LocalModel:
    """Derive exact Jacobians at a true thermal/actuator equilibrium."""
    if not isinstance(u0, (float, int)) or not np.isfinite(u0) or not 0 < u0 < 1:
        raise ValueError("Classical valve Jacobian requires a finite interior 0 < u0 < 1")
    eq = steady_state_for_valve(u0, params)
    ac = params.mc / (params.rho * params.vc)
    bc = params.ua / (params.rho * params.vc * params.cp)
    ah = eq.mh / (params.rho * params.vh)
    bh = params.ua / (params.rho * params.vh * params.cp)
    hot_valve_coupling = ((params.mh_max - params.mh_min) /
                          (params.rho * params.vh) * (params.th_in - eq.th))
    lv = 1.0 / params.valve_tau
    a = np.array([[-(ac + bc), bc, 0.0],
                  [bh, -(ah + bh), hot_valve_coupling],
                  [0.0, 0.0, -lv]])
    b = np.array([[0.0], [0.0], [lv]])
    c = np.array([[1.0, 0.0, 0.0]])
    d = np.array([[0.0]])
    thermal_sum = ac + bc + ah + bh
    thermal_prod = (ac + bc) * (ah + bh) - bc * bh
    den = np.array([1.0, lv + thermal_sum, thermal_prod + lv*thermal_sum,
                    lv * thermal_prod])
    num = np.array([bc * hot_valve_coupling * lv])
    poles = np.linalg.eigvals(a)
    gain = float(num[-1] / den[-1])
    return LocalModel(eq, a, b, c, d, num, den, poles, gain)


def finite_difference_jacobians(params: PlantParameters, u0: float,
                                *, perturbation: float = 1e-5) -> tuple[np.ndarray, np.ndarray]:
    if not np.isfinite(perturbation) or perturbation <= 0:
        raise ValueError("perturbation must be strictly positive and finite")
    eq = steady_state_for_valve(u0, params)
    inp = PlantInputs.from_params(params, u0)
    a = np.empty((3, 3))
    for i in range(3):
        delta = np.zeros(3)
        delta[i] = perturbation
        a[:, i] = (rhs(0, eq.state + delta, inp, params)
                   - rhs(0, eq.state - delta, inp, params))/(2*perturbation)
    plus = PlantInputs.from_params(params, u0 + perturbation)
    minus = PlantInputs.from_params(params, u0 - perturbation)
    b = ((rhs(0, eq.state, plus, params)
          - rhs(0, eq.state, minus, params))/(2*perturbation)).reshape(3, 1)
    return a, b
