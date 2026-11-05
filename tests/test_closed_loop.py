"""PID-10--15 and event timing/plant coupling integration tests."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from heatwin.config import load_config
from heatwin.control.tuning import imc_pi, load_identified_model
from heatwin.models.plant import steady_state_for_target
from heatwin.simulation.closed_loop import SetpointStep, simulate_closed_loop
from heatwin.simulation.open_loop import InputStep


@pytest.fixture
def case():
    p = load_config()
    model = load_identified_model(
        Path(__file__).resolve().parents[1] / "configs/identified/phase3_fopdt_nominal.json"
    )
    return p, imc_pi(model, lambda_s=model.tau_s)


def test_nominal_regulation_is_exact_bumpless(case):
    p, controller = case
    eq = steady_state_for_target(55, p)
    d = simulate_closed_loop(p, controller, duration_s=300)
    assert d.u.iloc[0] == pytest.approx(eq.u, abs=1e-12)
    assert d.xv.iloc[0] == pytest.approx(eq.xv, abs=1e-12)
    assert np.max(abs(d.tc_c - 55)) < 1e-7
    assert np.max(abs(d.u - eq.u)) < 1e-7
    assert d.time_s.iloc[-1] == 300
    assert d.controller_sample.all()


def test_positive_step_tracks_feasible_setpoint(case):
    p, controller = case
    d = simulate_closed_loop(p, controller, duration_s=420,
                             setpoint_steps=[SetpointStep(60, 57)])
    assert d.loc[d.time_s == 60, "u"].item() > d.loc[d.time_s == 59, "u"].item()
    assert d.tc_c.iloc[-1] == pytest.approx(57, abs=0.015)
    assert d.th_c.iloc[-1] > d.th_c.iloc[0]
    assert d.mh_kg_s.iloc[-1] > d.mh_kg_s.iloc[0]
    assert d.tc_c.loc[d.time_s == 60].item() == pytest.approx(55, abs=1e-7)


def test_negative_step_reduces_heating(case):
    p, controller = case
    d = simulate_closed_loop(p, controller, duration_s=420,
                             setpoint_steps=[SetpointStep(60, 53)])
    assert d.u.loc[d.time_s == 60].item() < d.u.loc[d.time_s == 59].item()
    assert d.tc_c.iloc[-1] == pytest.approx(53, abs=0.015)


def test_multiple_setpoint_transitions(case):
    p, controller = case
    d = simulate_closed_loop(p, controller, duration_s=480,
                             setpoint_steps=[SetpointStep(60, 57), SetpointStep(180, 54),
                                             SetpointStep(300, 56)])
    assert d.setpoint_c.loc[d.time_s == 60].item() == 57
    assert d.setpoint_c.loc[d.time_s == 180].item() == 54
    assert d.setpoint_c.loc[d.time_s == 300].item() == 56
    assert abs(d.tc_c.iloc[-1] - 56) < .05


@pytest.mark.parametrize("step,expected", [
    (InputStep(100, tc_in=27), "tc_in_c"),
    (InputStep(100, th_in=75), "th_in_c"),
    (InputStep(100, mc=.035), "mc_kg_s"),
])
def test_disturbance_is_rejected(case, step, expected):
    p, controller = case
    d = simulate_closed_loop(p, controller, duration_s=450, disturbance_steps=[step])
    assert d[expected].loc[d.time_s == 100].item() == pytest.approx(
        next(x for x in (step.tc_in, step.th_in, step.mc) if x is not None))
    assert abs(d.tc_c.iloc[-1] - 55) < .035
    assert d.u.iloc[-1] > d.u.iloc[0]


def test_offgrid_disturbance_exact_boundary_but_controller_waits(case):
    p, controller = case
    d = simulate_closed_loop(p, controller, duration_s=120,
                             disturbance_steps=[InputStep(73.42, tc_in=27)])
    event = d.loc[d.time_s == 73.42].iloc[0]
    assert event.tc_in_c == 27
    assert not event.controller_sample
    assert event.u == pytest.approx(d.u.loc[d.time_s == 73].item())
    assert event.tc_c == pytest.approx(55, abs=1e-7)
    after = d.loc[d.time_s == 74].iloc[0]
    assert after.tc_c < event.tc_c
    assert after.u > event.u


def test_offgrid_setpoint_only_changes_command_at_next_tick(case):
    p, controller = case
    d = simulate_closed_loop(p, controller, duration_s=100,
                             setpoint_steps=[SetpointStep(60.5, 57)])
    event = d.loc[d.time_s == 60.5].iloc[0]
    assert event.setpoint_c == 57
    assert event.u == pytest.approx(d.u.loc[d.time_s == 60].item())
    assert d.u.loc[d.time_s == 61].item() > event.u


def test_reproducible_identical_inputs(case):
    p, s = case
    kw = {"duration_s": 200, "disturbance_steps": [InputStep(110, tc_in=27.0)],
          "setpoint_steps": [SetpointStep(60, 57)]}
    a = simulate_closed_loop(p, s, **kw)
    b = simulate_closed_loop(p, s, **kw)
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert a.attrs == b.attrs


def test_returned_schema_and_physical_limits(case):
    p, s = case
    d = simulate_closed_loop(p, s, duration_s=80, setpoint_steps=[SetpointStep(60, 57)])
    expected = {"time_s", "setpoint_c", "tc_c", "measurement_c", "th_c", "error_c",
                "u", "u_raw", "xv", "mh_kg_s", "mc_kg_s", "tc_in_c", "th_in_c",
                "q_w", "p_term", "i_term", "d_term", "saturated", "controller_sample"}
    assert expected.issubset(d.columns)
    assert np.isfinite(d.select_dtypes(include="number").to_numpy()).all()
    assert ((d.u >= 0) & (d.u <= 1)).all()
    assert ((d.xv >= 0) & (d.xv <= 1)).all()
    assert d.time_s.is_monotonic_increasing and not d.time_s.duplicated().any()
    assert (d.mh_kg_s >= p.mh_min - 1e-9).all()


@pytest.mark.parametrize("kwargs", [
    {"duration_s": 0}, {"duration_s": float("inf")},
    {"rtol": 0}, {"rtol": 1e-16}, {"atol": -1},
    {"setpoint_steps": [SetpointStep(10, 57), SetpointStep(10, 56)]},
    {"setpoint_steps": [SetpointStep(1000, 57)]},
    {"disturbance_steps": [InputStep(20, u=0.9)]},
    {"disturbance_steps": [InputStep(20, tc_in=25), InputStep(20, mc=0.04)]},
    {"initial_state": [55, 65]}, {"initial_state": [55, 65, 1.5]},
])
def test_invalid_scenarios(case, kwargs):
    p, s = case
    with pytest.raises(ValueError):
        simulate_closed_loop(p, s, duration_s=50, **kwargs) if "duration_s" not in kwargs else simulate_closed_loop(p, s, **kwargs)


def test_changed_ua_without_retuning_is_finite(case):
    p, s = case
    for scale in (.8, 1.2):
        modified = replace(p, ua=p.ua * scale)
        d = simulate_closed_loop(modified, s, duration_s=420,
                                 setpoint_steps=[SetpointStep(60, 57)])
        assert np.isfinite(d.tc_c.to_numpy()).all()
        assert abs(d.tc_c.iloc[-1] - 57) < .1
