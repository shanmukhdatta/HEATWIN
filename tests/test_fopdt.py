"""ID-04: FOPDT constrained estimator recovery and nonnegative delay."""
import numpy as np
import pandas as pd
import pytest

from heatwin.identification.fit_models import fit_step_response, predict_piecewise_steps
from heatwin.identification.fopdt import response


def test_known_fopdt_parameter_recovery():
    t = np.unique(np.r_[np.arange(0., 250., .5), 25.3])
    y = response(t, 12.0, 20.0, 6.5, step_time_s=25.3, delta_u=.10, baseline_c=55)
    df = pd.DataFrame({"time_s": t, "tc_c": y, "u": np.where(t >= 25.3, .5, .4)})
    fit = fit_step_response(df, model="fopdt", step_time_s=25.3)
    assert fit.process_gain == pytest.approx(12., abs=.003)
    assert fit.tau1_s == pytest.approx(20., abs=.03)
    assert fit.theta_s == pytest.approx(6.5, abs=.03)
    assert fit.training_rmse_c < 1e-5
    assert fit.coefficients()["input_delay_s"] == pytest.approx(6.5, abs=.03)


def test_step_time_plus_delay_is_exactly_flat_before_response():
    t = np.array([0., 9.9, 10., 15.9, 16., 17.])
    y = response(t, 5., 12., 6., step_time_s=10., delta_u=.1, baseline_c=50)
    assert y[:-1] == pytest.approx(np.full(5, 50.))
    assert y[-1] > 50


def test_multi_step_superposition_matches_sum_of_independent_steps():
    t = np.linspace(0, 160, 161)
    y0 = 50
    df = pd.DataFrame({"time_s": t, "tc_c": response(
        t, 5., 18., 4., step_time_s=20, delta_u=.1, baseline_c=y0),
        "u": np.where(t >= 20, .5, .4)})
    fit = fit_step_response(df, model="fopdt", step_time_s=20)
    predicted = predict_piecewise_steps(fit, t, initial_command=.4, baseline_c=y0,
                                         changes=[(20, .5), (70, .45), (120, .6)])
    expected = (response(t, fit.process_gain, fit.tau1_s, fit.theta_s,
                         step_time_s=20, delta_u=.1)
                + response(t, fit.process_gain, fit.tau1_s, fit.theta_s,
                           step_time_s=70, delta_u=-.05)
                + response(t, fit.process_gain, fit.tau1_s, fit.theta_s,
                           step_time_s=120, delta_u=.15) + y0)
    assert np.max(np.abs(predicted - expected)) < 1e-11


@pytest.mark.parametrize("tau,delay", [(0, 0), (3, -1), (float("nan"), 1)])
def test_invalid_physical_params(tau, delay):
    with pytest.raises(ValueError):
        response([0, 1], 10, tau, delay, step_time_s=0, delta_u=.1)
