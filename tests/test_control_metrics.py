"""PID-14 independent metric values and event-window conventions."""

import numpy as np
import pandas as pd
import pytest

from heatwin.diagnostics.control_metrics import evaluate_control


def fixture_data():
    return pd.DataFrame({"time_s": [0, 1, 2], "error_c": [2., 1., 0.],
                         "setpoint_c": [2., 2., 2.], "tc_c": [0., 1., 2.],
                         "u": [.4, .6, .6], "xv": [.4, .5, .6],
                         "saturated": [True, False, False]})


def test_trapezoidal_integrals_and_effort():
    m = evaluate_control(fixture_data(), reference_initial_c=0, band_c=.01)
    assert m.iae_c_s == pytest.approx(2.)
    assert m.ise_c2_s == pytest.approx(3.)
    assert m.itae_c_s2 == pytest.approx(1.)
    assert m.total_command_movement == pytest.approx(.2)
    assert m.total_valve_movement == pytest.approx(.2)
    assert m.saturation_duration_s == 1
    assert m.observed_final_error_c == 0
    assert m.settling_time_s == 2
    assert m.rise_time_s == pytest.approx(1.6)


def test_event_relative_itae_time_origin():
    f = fixture_data()
    f.time_s += 50
    m = evaluate_control(f, window_start_s=50)
    assert m.itae_c_s2 == pytest.approx(1.)


def test_unsettled_reports_none_and_avoids_fake_precision():
    f = fixture_data()
    f.tc_c = [0, 1, 1]
    f.error_c = f.setpoint_c - f.tc_c
    m = evaluate_control(f, reference_initial_c=0, band_c=.1)
    assert m.settling_time_s is None
    assert m.rise_time_s is None


def test_negative_step_direction_is_handled():
    f = fixture_data()
    f.setpoint_c = 0
    f.tc_c = [2, 1, 0]
    f.error_c = f.setpoint_c - f.tc_c
    m = evaluate_control(f, reference_initial_c=2)
    assert m.overshoot_c == 0
    assert m.settling_time_s == 2


@pytest.mark.parametrize("mod", [
    lambda f: f.drop(columns="u"),
    lambda f: f.assign(time_s=[0, 0, 2]),
    lambda f: f.assign(error_c=[np.nan, 1, 0]),
    lambda f: f.iloc[:1],
    lambda f: f.assign(saturated=[True, None, False]),
])
def test_invalid_metrics_input(mod):
    with pytest.raises(ValueError):
        evaluate_control(mod(fixture_data()))
