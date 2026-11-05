"""PID-01/02/03/04/06/16/17: sampled controller mathematics."""

import pytest

from heatwin.control.controller_config import ControllerSettings
from heatwin.control.pid import PIDController


def test_positive_error_increases_heating():
    p = PIDController(ControllerSettings("P", 0.05, bias=0.4))
    p.initialize(setpoint_c=55, measurement_c=55)
    assert p.update(setpoint_c=57, measurement_c=55).command == pytest.approx(0.5)


def test_integral_rectangular_update_and_output_timing():
    pid = PIDController(ControllerSettings("PI", 0.2, ti_s=10, sample_time_s=2, bias=0.4))
    pid.initialize(setpoint_c=55, measurement_c=55)
    a = pid.update(setpoint_c=56, measurement_c=55)
    assert a.i_term == pytest.approx(0)
    assert pid.integral == pytest.approx(0.04)
    b = pid.update(setpoint_c=56, measurement_c=55)
    assert b.i_term == pytest.approx(0.04)


def test_derivative_on_measurement_no_setpoint_kick():
    ctrl = PIDController(ControllerSettings("PID", 0.05, ti_s=20, td_s=5,
                                            filter_tau_s=2, bias=0.4))
    ctrl.initialize(setpoint_c=55, measurement_c=55)
    x = ctrl.update(setpoint_c=57, measurement_c=55)
    assert x.d_term == 0
    y = ctrl.update(setpoint_c=57, measurement_c=56)
    assert y.d_term < 0
    assert y.d_term == pytest.approx(-0.05 * 5 / 3)
    z = ctrl.update(setpoint_c=57, measurement_c=56)
    assert abs(z.d_term) < abs(y.d_term)


def test_bumpless_initialization_tracks_manual_for_all_modes():
    for mode in ("P", "PI", "PID"):
        s = ControllerSettings(mode, 0.05, ti_s=30 if mode != "P" else None,
                               td_s=2 if mode == "PID" else 0, bias=0.4)
        c = PIDController(s)
        c.initialize(setpoint_c=55, measurement_c=54, manual_command=0.47)
        assert c.update(setpoint_c=55, measurement_c=54).command == pytest.approx(0.47)
        c.reset()
        assert c.last_measurement is None
        assert c.integral == 0


def test_saturation_at_both_limits():
    c = PIDController(ControllerSettings("P", 1.0, bias=0.4))
    c.initialize(setpoint_c=55, measurement_c=55)
    assert c.update(setpoint_c=60, measurement_c=55).command == 1
    assert c.update(setpoint_c=50, measurement_c=55).command == 0


@pytest.mark.parametrize("kwargs", [
    {"mode": "INVALID", "kc": 0.1}, {"mode": "PI", "kc": 0.0, "ti_s": 2},
    {"mode": "PI", "kc": 0.1, "ti_s": 0}, {"mode": "PID", "kc": 0.1, "ti_s": 2, "td_s": -1},
    {"mode": "P", "kc": 0.1, "ti_s": 2}, {"mode": "P", "kc": 0.1, "td_s": 1},
    {"mode": "P", "kc": 0.1, "sample_time_s": 0},
    {"mode": "P", "kc": 0.1, "sample_time_s": float("nan")},
    {"mode": "P", "kc": 0.1, "lower": 0.9, "upper": 0.3},
    {"mode": "P", "kc": float("inf")},
    {"mode": "P", "kc": 0.1, "anti_windup": "invalid"},
])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        ControllerSettings(**kwargs)


def test_invalid_update_time():
    c = PIDController(ControllerSettings("P", 0.1))
    for dt in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            c.update(setpoint_c=55, measurement_c=54, dt_s=dt)


def test_controller_does_not_store_future_measurements():
    c = PIDController(ControllerSettings("PI", .04, ti_s=25))
    c.initialize(setpoint_c=55, measurement_c=55)
    a = c.update(setpoint_c=55, measurement_c=55)
    assert a.command == pytest.approx(0.4)
    c.update(setpoint_c=55, measurement_c=54)
    assert c.integral > 0
