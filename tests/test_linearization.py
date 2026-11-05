"""ID-06, ID-07: exact Jacobian and small-signal consistency."""
import numpy as np
import pytest

from heatwin.config import load_config
from heatwin.identification.linearization import (
    finite_difference_jacobians, linearize_at_valve,
)
from heatwin.models.plant import steady_state_for_valve
from heatwin.simulation.open_loop import InputStep, simulate_open_loop


@pytest.mark.parametrize("u0", [.3, .4, .5, .6])
def test_analytic_jacobian_matches_finite_difference(u0):
    p = load_config()
    model = linearize_at_valve(p, u0)
    a, b = finite_difference_jacobians(p, u0)
    assert np.max(np.abs(model.A - a)) < 1e-7
    assert np.max(np.abs(model.B - b)) < 1e-7
    assert model.C.tolist() == [[1, 0, 0]]
    assert model.D.item() == 0
    assert np.all(model.poles.real < 0)


def test_transfer_function_gain_agrees_with_equilibrium_derivative():
    p = load_config()
    m = linearize_at_valve(p, .4)
    h = 1e-5
    gain = (steady_state_for_valve(.4+h, p).tc
            - steady_state_for_valve(.4-h, p).tc)/(2*h)
    assert m.process_gain == pytest.approx(gain, rel=1e-7)
    assert m.scipy_transfer_function().num[-1] / m.scipy_transfer_function().den[-1] == pytest.approx(gain)


def test_small_signal_linearization_matches_nonlinear_simulation():
    p = load_config()
    u0, delta = .4, 1e-3
    df = simulate_open_loop(p, initial_command=u0, duration_s=300,
                            steps=[InputStep(60, u=u0+delta)])
    m = linearize_at_valve(p, u0)
    predicted = m.predict_step(df.time_s, delta_u=delta, step_time_s=60)
    assert np.max(np.abs(predicted-df.tc_c.to_numpy())) < 1e-4


@pytest.mark.parametrize("u0", [-.1, 0, 1., 1.1, float("nan")])
def test_noninterior_points_rejected(u0):
    with pytest.raises(ValueError):
        linearize_at_valve(load_config(), u0)
