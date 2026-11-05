"""ID-03: FO model recovery and characteristic method; synthetic estimator tests only."""
import numpy as np
import pandas as pd
import pytest

from heatwin.identification.first_order import response, time_constant_632
from heatwin.identification.fit_models import fit_step_response


def known_step(model, *, gain=9.0, tau=18.0, ts=20.4, du=.12):
    t = np.unique(np.r_[np.arange(0., 180., .5), ts])
    y = response(t, gain, tau, step_time_s=ts, delta_u=du, baseline_c=45)
    u = np.where(t >= ts, .4 + du, .4)
    return pd.DataFrame({"time_s": t, "tc_c": y, "u": u})


def test_fo_exact_recovery_on_known_synthetic_test_signal():
    df = known_step(None)
    fit = fit_step_response(df, model="fo", step_time_s=20.4)
    assert fit.process_gain == pytest.approx(9, abs=1e-4)
    assert fit.tau1_s == pytest.approx(18, abs=1e-4)
    assert fit.training_rmse_c < 1e-7
    assert fit.coefficients()["denominator"] == pytest.approx([fit.tau1_s, 1])


def test_632_interpolation_relative_to_event():
    df = known_step(None, tau=18)
    tau = time_constant_632(df.time_s, df.tc_c, step_time_s=20.4)
    assert tau == pytest.approx(18, abs=.04)


def test_negative_gain_fo_recovery():
    df = known_step(None, gain=-9)
    fit = fit_step_response(df, model="fo", step_time_s=20.4)
    assert fit.process_gain == pytest.approx(-9, abs=1e-3)


@pytest.mark.parametrize("tau", [0, -3])
def test_invalid_tau(tau):
    with pytest.raises(ValueError):
        response([0, 1], 1, tau, step_time_s=1, delta_u=.1)


def test_flat_response_has_no_identifiable_tau():
    with pytest.raises(ValueError, match="Flat"):
        time_constant_632(np.arange(10.), np.full(10, 55.), step_time_s=2)
