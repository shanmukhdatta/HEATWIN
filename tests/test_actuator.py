"""PHY-04: physical valve and hot-flow constraints."""

import numpy as np
import pytest

from heatwin.config import load_config
from heatwin.models.actuator import clamp_fraction, hot_mass_flow, valve_derivative
from heatwin.simulation.open_loop import InputStep, simulate_open_loop


def test_flow_endpoints_and_saturation() -> None:
    p = load_config()
    assert hot_mass_flow(0, p) == pytest.approx(p.mh_min)
    assert hot_mass_flow(1, p) == pytest.approx(p.mh_max)
    assert hot_mass_flow(-8, p) == pytest.approx(p.mh_min)
    assert hot_mass_flow(8, p) == pytest.approx(p.mh_max)
    assert hot_mass_flow(0.5, p) == pytest.approx((p.mh_min + p.mh_max) / 2)


@pytest.mark.parametrize("command,expected", [(-3.0, 0.0), (0.25, 0.25), (3.0, 1.0)])
def test_command_saturation(command: float, expected: float) -> None:
    p = load_config()
    assert clamp_fraction(command) == expected
    assert valve_derivative(0.25, command, p) == pytest.approx((expected - 0.25) / p.valve_tau)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), None, True, "0.5"])
def test_bad_valve_fractions(invalid: object) -> None:
    p = load_config()
    with pytest.raises(ValueError, match="finite real"):
        hot_mass_flow(invalid, p)
    with pytest.raises(ValueError, match="finite real"):
        valve_derivative(0.4, invalid, p)


def test_valve_step_follows_analytical_first_order_solution() -> None:
    p = load_config()
    out = simulate_open_loop(p, duration_s=20, initial_command=0.4,
                             steps=[InputStep(0.0, u=0.7)])
    t = out["time_s"].to_numpy()
    expected = 0.7 + (0.4 - 0.7) * np.exp(-t / p.valve_tau)
    assert np.max(np.abs(out["xv"].to_numpy() - expected)) < 1e-8
    assert np.all((0 <= out["xv"]) & (out["xv"] <= 1))


def test_out_of_range_command_is_bounded() -> None:
    p = load_config()
    data = simulate_open_loop(p, duration_s=30, initial_command=0.4,
                              steps=[InputStep(0, u=10.0)])
    assert data["u"].eq(1.0).all()
    assert data["xv"].between(0, 1).all()
    assert data["mh_kg_s"].between(p.mh_min, p.mh_max).all()
