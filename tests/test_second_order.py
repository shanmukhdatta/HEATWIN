"""ID-05: two stable real poles; repeated-pole analytic limit."""
import numpy as np
import pandas as pd
import pytest

from heatwin.identification.fit_models import fit_step_response
from heatwin.identification.second_order import response


def test_known_second_order_response_recovery():
    t = np.arange(0., 350., .5)
    y = response(t, 15., 6., 24., step_time_s=40, delta_u=.1, baseline_c=55)
    df = pd.DataFrame({"time_s": t, "tc_c": y, "u": np.where(t >= 40, .5, .4)})
    fit = fit_step_response(df, model="second_order", step_time_s=40)
    assert fit.process_gain == pytest.approx(15., abs=.01)
    assert sorted([fit.tau1_s, fit.tau2_s]) == pytest.approx([6., 24.], abs=.08)
    assert fit.training_rmse_c < 1e-5
    assert len(fit.coefficients()["denominator"]) == 3


def test_repeated_pole_response_is_finite_and_monotone():
    t = np.linspace(0, 300, 601)
    y = response(t, 10., 15., 15., step_time_s=20, delta_u=.1)
    assert np.isfinite(y).all()
    assert np.min(np.diff(y)) >= -1e-11
    assert y[-1] == pytest.approx(1., abs=1e-6)


def test_invalid_poles_rejected():
    for a, b in [(0, 1), (1, -1), (np.inf, 2)]:
        with pytest.raises(ValueError):
            response([0., 1.], 1, a, b, step_time_s=0, delta_u=.1)
