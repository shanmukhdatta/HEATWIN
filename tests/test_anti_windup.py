"""PID-05 conditional integration prevents sustained saturation windup."""

from dataclasses import replace

import pytest

from heatwin.control.controller_config import ControllerSettings
from heatwin.control.pid import PIDController


def test_integral_saturation_does_not_accumulate_unboundedly():
    base = ControllerSettings("PI", .15, ti_s=5, bias=.4)
    with_aw = PIDController(base)
    no_aw = PIDController(replace(base, anti_windup="none"))
    for c in (with_aw, no_aw):
        c.initialize(setpoint_c=55, measurement_c=55)
        for _ in range(100):
            result = c.update(setpoint_c=80, measurement_c=55)
            assert result.command == 1.0
    assert abs(with_aw.integral) < 5.0
    assert no_aw.integral > 70
    a = with_aw.update(setpoint_c=55, measurement_c=55)
    b = no_aw.update(setpoint_c=55, measurement_c=55)
    assert a.command < b.command
    assert a.command == pytest.approx(.4)
