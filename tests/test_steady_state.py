"""PHY-02, PHY-03, PHY-06, PHY-08 analytical equilibria and feasibility."""

from dataclasses import replace

import numpy as np
import pytest

from heatwin.config import ConfigurationError, load_config
from heatwin.models.plant import (
    ModelError,
    PlantInputs,
    rhs,
    steady_state_for_target,
    steady_state_for_valve,
)
from heatwin.simulation.open_loop import simulate_open_loop


def test_phy02_nominal_equilibrium_and_derivatives() -> None:
    p = load_config()
    eq = steady_state_for_target(p.setpoint, p)
    # These are independent reference computations, not hard-coded model values.
    expected_q = p.mc * p.cp * (p.setpoint - p.tc_in)
    expected_th = p.setpoint + expected_q / p.ua
    expected_mh = expected_q / (p.cp * (p.th_in - expected_th))
    expected_xv = (expected_mh - p.mh_min) / (p.mh_max - p.mh_min)
    assert eq.tc == pytest.approx(55.0)
    assert eq.th == pytest.approx(63.957142857, abs=1e-7)
    assert eq.q == pytest.approx(expected_q)
    assert eq.mh == pytest.approx(expected_mh)
    assert eq.xv == pytest.approx(expected_xv)
    assert np.linalg.norm(rhs(0, eq.state, PlantInputs.from_params(p, eq.u), p), ord=np.inf) < 1e-12


@pytest.mark.parametrize("valve", [0.0, 0.1, 0.3, 0.4, 0.5, 0.8, 1.0])
def test_forward_equilibrium_residuals(valve: float) -> None:
    p = load_config()
    ss = steady_state_for_valve(valve, p)
    derivative = rhs(0, ss.state, PlantInputs.from_params(p, valve), p)
    assert np.max(np.abs(derivative)) < 1e-12
    assert min(p.tc_in, p.th_in) <= ss.tc <= max(p.tc_in, p.th_in)
    assert min(p.tc_in, p.th_in) <= ss.th <= max(p.tc_in, p.th_in)


def test_phy03_hot_flow_increases_cold_equilibrium_temperature() -> None:
    p = load_config()
    low = steady_state_for_valve(0.3, p)
    high = steady_state_for_valve(0.5, p)
    assert high.mh > low.mh
    assert high.tc > low.tc
    assert high.th > low.th


@pytest.mark.parametrize("valve", [0, 0.2, 0.40833085980013833, 0.9, 1])
def test_forward_inverse_consistency(valve: float) -> None:
    p = load_config()
    fwd = steady_state_for_valve(valve, p)
    inverse = steady_state_for_target(fwd.tc, p)
    assert inverse.u == pytest.approx(valve, abs=1e-10)
    assert inverse.th == pytest.approx(fwd.th, abs=1e-10)
    assert inverse.mh == pytest.approx(fwd.mh, abs=1e-10)


@pytest.mark.parametrize("target", [25, 30, 40, 61, 79, 85, 1e6])
def test_unreachable_setpoints_raise(target: float) -> None:
    p = load_config()
    with pytest.raises(ModelError, match="infeasible|outside"):
        steady_state_for_target(target, p)


def test_no_cold_flow_fails_inverse() -> None:
    p = load_config()
    conditions = replace(PlantInputs.from_params(p, 0.4), mc=0)
    with pytest.raises(ModelError, match="positive cold-side"):
        steady_state_for_target(55.0, p, inputs=conditions)


def test_zero_flow_on_both_sides_is_nonunique() -> None:
    p = replace(load_config(), mh_min=0, mh_max=0.1)
    conditions = PlantInputs.from_params(p, 0.0)
    conditions = replace(conditions, mc=0.0)
    with pytest.raises(ModelError, match="No unique equilibrium"):
        steady_state_for_valve(0.0, p, inputs=conditions)


@pytest.mark.parametrize("field,value", [("vc", -0.1), ("vh", 0), ("cp", -1),
                                         ("ua", -1), ("mh_max", 0.001)])
def test_phy08_invalid_physical_params_rejected(field: str, value: float) -> None:
    with pytest.raises(ConfigurationError):
        replace(load_config(), **{field: value})


def test_phy06_numerical_nominal_equilibrium_hold() -> None:
    p = load_config()
    state = steady_state_for_target(55.0, p)
    result = simulate_open_loop(p, duration_s=300, initial_state=state.state,
                                initial_command=state.u)
    assert np.max(np.abs(result["tc_c"] - state.tc)) < 2e-7
    assert np.max(np.abs(result["th_c"] - state.th)) < 2e-7
    assert np.max(np.abs(result["xv"] - state.xv)) < 1e-10
