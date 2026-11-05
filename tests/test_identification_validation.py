"""ID-08 through ID-12: metrics, holdout isolation, input failures."""
import numpy as np
import pandas as pd
import pytest

from heatwin.config import load_config
from heatwin.identification.fit_models import fit_step_response
from heatwin.identification.step_test import create_step_experiment
from heatwin.identification.validation import error_metrics


def test_metric_values():
    result = error_metrics([1, 3, 6], [2, 2, 5])
    assert result.mae == pytest.approx(1)
    assert result.rmse == pytest.approx(1)
    assert result.max_abs_error == 1
    assert isinstance(result.fit_percent, float)


def test_constant_truth_does_not_divide_by_zero():
    assert error_metrics([1., 1.], [1., 2.]).fit_percent is None


@pytest.mark.parametrize("actual,pred", [([1, 2], [1]), ([1], [[1]]),
                                         ([np.nan], [1]), ([], []), ([1], [np.inf])])
def test_invalid_metrics(actual, pred):
    with pytest.raises(ValueError):
        error_metrics(actual, pred)


def test_holdout_data_change_cannot_modify_fitted_parameters():
    p=load_config()
    training=create_step_experiment(p, u0=.4, delta_u=.1)
    holdout=create_step_experiment(p, u0=.4, delta_u=.05)
    fit=fit_step_response(training.data, model="fopdt", step_time_s=60)
    altered=holdout.data.copy()
    altered.loc[altered.time_s >= 60, "tc_c"] += 100
    # Validation is never supplied to fitting; this checks that no global
    # state is reused and the fitted model is immutable/deterministic.
    fit2=fit_step_response(training.data, model="fopdt", step_time_s=60)
    assert fit==fit2
    t=holdout.data.time_s.to_numpy()
    y1=fit.predict(t, delta_u=.05, baseline_c=holdout.equilibrium.tc)
    y2=fit2.predict(t, delta_u=.05, baseline_c=holdout.equilibrium.tc)
    np.testing.assert_array_equal(y1, y2)
    assert error_metrics(holdout.data.tc_c.to_numpy(),y1).rmse < 1
    assert error_metrics(altered.tc_c.to_numpy(),y1).rmse > 1


def test_fit_rejects_invalid_data_and_optimizer_constraints():
    ex=create_step_experiment(load_config())
    with pytest.raises(ValueError):
        fit_step_response(ex.data, model="bad", step_time_s=60)
    with pytest.raises(ValueError):
        fit_step_response(ex.data, model="fo", step_time_s=60, max_nfev=0)
    with pytest.raises(ValueError):
        fit_step_response(ex.data.iloc[:5], model="fo", step_time_s=60)
    bad=ex.data.copy()
    bad.loc[40,"tc_c"]=np.inf
    with pytest.raises(ValueError):
        fit_step_response(bad, model="fo", step_time_s=60)
    # A very tight evaluation cap must not silently be reported as success.
    with pytest.raises(RuntimeError):
        fit_step_response(ex.data, model="fo", step_time_s=60, max_nfev=1)


def test_fit_rejects_multi_step_as_single_step():
    ex=create_step_experiment(load_config())
    bad=ex.data.copy()
    bad.loc[bad.time_s >= 180,"u"] = .55
    with pytest.raises(ValueError, match="multi-step"):
        fit_step_response(bad, model="fo", step_time_s=60)


def test_fit_rejects_insufficient_post_event_observations():
    df=pd.DataFrame({"time_s":[0,1,2,3,4,5,6,7],
                     "u":[.4,.4,.4,.5,.5,.5,.5,.5],
                     "tc_c":[55,55,55,55.01,55.02,55.03,55.04,55.05]})
    with pytest.raises(ValueError):
        fit_step_response(df, model="fo", step_time_s=3)
