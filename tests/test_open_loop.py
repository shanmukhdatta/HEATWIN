"""PHY-05, PHY-07, PHY-09, PHY-10 and numerical event/validation tests."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from heatwin.config import load_config
from heatwin.models.plant import PlantInputs, rhs, steady_state_for_valve
from heatwin.simulation.open_loop import InputStep, SimulationError, simulate_open_loop
from heatwin.visualization.charts import make_open_loop_figure


def test_phy05_hot_flow_step_approaches_analytic_equilibrium() -> None:
    p = load_config()
    start = steady_state_for_valve(0.4, p)
    target = steady_state_for_valve(0.5, p)
    data = simulate_open_loop(p, steps=[InputStep(60, u=0.5)])
    assert data["tc_c"].iloc[0] == pytest.approx(start.tc)
    assert data["tc_c"].iloc[-1] == pytest.approx(target.tc, abs=2e-3)
    assert data["th_c"].iloc[-1] == pytest.approx(target.th, abs=2e-3)
    assert data["tc_c"].iloc[-1] > data["tc_c"].iloc[0]
    assert data["xv"].iloc[-1] == pytest.approx(0.5, abs=1e-10)
    assert (data["mh_kg_s"] >= p.mh_min - 1e-12).all()
    assert (data["mh_kg_s"] <= p.mh_max + 1e-12).all()


def test_downward_valve_step_cools_cold_side() -> None:
    p = load_config()
    high = steady_state_for_valve(0.5, p)
    low = steady_state_for_valve(0.3, p)
    data = simulate_open_loop(p, initial_command=0.5, initial_state=high.state,
                              steps=[InputStep(60, u=0.3)])
    assert data["tc_c"].iloc[-1] == pytest.approx(low.tc, abs=2e-3)
    assert data["tc_c"].iloc[-1] < data["tc_c"].iloc[0]
    assert data["mh_kg_s"].iloc[-1] == pytest.approx(low.mh, abs=1e-9)


def test_phy07_cold_inlet_step_changes_open_loop_temperature() -> None:
    p = load_config()
    data = simulate_open_loop(p, steps=[InputStep(100.0, tc_in=27.0)])
    original = steady_state_for_valve(0.4, p)
    conditions = replace(PlantInputs.from_params(p, 0.4), tc_in=27)
    disturbed = steady_state_for_valve(0.4, p, inputs=conditions)
    assert data.loc[data.time_s == 100, "tc_in_c"].item() == 27.0
    assert data.loc[data.time_s == 99, "tc_in_c"].item() == 30.0
    assert data["tc_c"].iloc[0] == pytest.approx(original.tc)
    assert data["tc_c"].iloc[-1] == pytest.approx(disturbed.tc, abs=2e-3)
    assert disturbed.tc < original.tc
    assert (data["u"] == 0.4).all()


def test_step_at_non_grid_time_uses_right_continuous_input_and_continuous_state() -> None:
    p = load_config()
    step = 60.37
    d1 = simulate_open_loop(p, duration_s=100.0, sample_time_s=1.0,
                            steps=[InputStep(step, u=0.7)])
    row = d1.loc[d1.time_s == step].iloc[0]
    assert row["u"] == 0.7
    assert row["xv"] == pytest.approx(0.4, abs=1e-9)
    # An input discontinuity must not cause an instantaneous temperature jump.
    old = steady_state_for_valve(0.4, p)
    assert row["tc_c"] == pytest.approx(old.tc, abs=1e-9)
    assert row["th_c"] == pytest.approx(old.th, abs=1e-9)
    after = d1.loc[d1.time_s == 61.0].iloc[0]
    assert 0.4 < after["xv"] < 0.7
    assert after["tc_c"] > row["tc_c"]


def test_multiple_changes_have_exact_event_rows() -> None:
    p = load_config()
    data = simulate_open_loop(p, duration_s=12.5, sample_time_s=2,
                              steps=[InputStep(1.75, u=0.6),
                                     InputStep(8.25, th_in=75.0, mc=0.025)])
    assert np.any(data.time_s == 1.75)
    assert np.any(data.time_s == 8.25)
    assert data.time_s.iloc[-1] == 12.5
    assert data.loc[data.time_s == 8.25, "mc_kg_s"].item() == 0.025
    assert data.loc[data.time_s == 8.25, "th_in_c"].item() == 75.0
    assert data.loc[data.time_s == 8.25, "u"].item() == 0.6


def test_step_at_duration_is_logged_without_changing_state() -> None:
    p = load_config()
    data = simulate_open_loop(p, duration_s=15, steps=[InputStep(15, u=0.9)])
    assert data.iloc[-1]["u"] == 0.9
    assert data.iloc[-1]["xv"] == pytest.approx(0.4)


def test_phy09_repeated_runs_are_bitwise_reproducible() -> None:
    p = load_config()
    kwargs = {"duration_s": 300, "steps": [InputStep(60, u=0.5),
                                           InputStep(110, tc_in=28)]}
    a = simulate_open_loop(p, **kwargs)
    b = simulate_open_loop(p, **kwargs)
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert a.attrs == b.attrs


def test_phy10_convergence_under_stricter_tolerances() -> None:
    p = load_config()
    steps = [InputStep(60, u=0.5)]
    coarse = simulate_open_loop(p, steps=steps, rtol=1e-7, atol=1e-9)
    fine = simulate_open_loop(p, steps=steps, rtol=1e-11, atol=1e-13,
                              sample_time_s=0.25)
    sampled = fine[fine.time_s.isin(coarse.time_s)]
    assert len(sampled) == len(coarse)
    for name, limit in (("tc_c", 1e-4), ("th_c", 1e-4), ("xv", 1e-5)):
        assert np.max(np.abs(coarse[name].to_numpy() - sampled[name].to_numpy())) < limit


def test_internal_energy_identity_at_each_simulated_time() -> None:
    p = load_config()
    data = simulate_open_loop(p, steps=[InputStep(60, u=0.5), InputStep(100, tc_in=27)])
    for row in data.iloc[::17].itertuples():
        controls = PlantInputs(u=row.u, tc_in=row.tc_in_c, th_in=row.th_in_c,
                               mc=row.mc_kg_s)
        dtc, dth, _ = rhs(row.time_s, [row.tc_c, row.th_c, row.xv], controls, p)
        lhs = p.rho * p.vc * p.cp * dtc + p.rho * p.vh * p.cp * dth
        rhs_external = (row.mc_kg_s * p.cp * (row.tc_in_c - row.tc_c)
                        + row.mh_kg_s * p.cp * (row.th_in_c - row.th_c))
        assert lhs == pytest.approx(rhs_external, abs=1e-8)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True, "300"])
def test_invalid_duration(bad: object) -> None:
    with pytest.raises(ValueError):
        simulate_open_loop(load_config(), duration_s=bad)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_invalid_numerical_settings(bad: float) -> None:
    p = load_config()
    for name in ("sample_time_s", "rtol", "atol"):
        with pytest.raises(SimulationError):
            simulate_open_loop(p, **{name: bad})


def test_too_small_relative_tolerance_is_rejected() -> None:
    with pytest.raises(SimulationError, match="rtol"):
        simulate_open_loop(load_config(), rtol=1e-15)


def test_invalid_solver_method() -> None:
    with pytest.raises(SimulationError, match="method"):
        simulate_open_loop(load_config(), method="invalid")


@pytest.mark.parametrize("bad", [-1, 1.1, float("nan")])
def test_invalid_initial_actuator_state(bad: float) -> None:
    with pytest.raises(ValueError):
        simulate_open_loop(load_config(), initial_state=[55, 64, bad])


def test_invalid_initial_state_shape() -> None:
    with pytest.raises(ValueError, match="three finite numbers"):
        simulate_open_loop(load_config(), initial_state=[55, 64])


def test_invalid_event_time_after_duration() -> None:
    with pytest.raises(SimulationError, match="exceed"):
        simulate_open_loop(load_config(), duration_s=10,
                           steps=[InputStep(11, u=0.6)])


def test_duplicate_event_time_rejected() -> None:
    with pytest.raises(SimulationError, match="same time"):
        simulate_open_loop(load_config(), duration_s=10,
                           steps=[InputStep(2, u=0.6), InputStep(2, tc_in=28)])


@pytest.mark.parametrize("time_s", [-1, float("nan"), float("inf")])
def test_invalid_step_timestamp(time_s: float) -> None:
    with pytest.raises(ValueError):
        InputStep(time_s, u=0.7)


def test_empty_step_and_bad_mass_flow_rejected() -> None:
    with pytest.raises(SimulationError, match="change at least one"):
        InputStep(10)
    with pytest.raises(SimulationError, match="mc must be nonnegative"):
        InputStep(10, mc=-0.01)


def test_output_sampling_and_metadata() -> None:
    p = load_config()
    df = simulate_open_loop(p, duration_s=10.2, sample_time_s=1.25)
    assert df.time_s.iloc[0] == 0.0
    assert df.time_s.iloc[-1] == 10.2
    assert df.time_s.is_monotonic_increasing
    assert not df.isna().any().any()
    assert df.attrs["parameters"]["ua"] == 350.0
    assert df.attrs["solver"]["method"] == "RK45"


def test_alternate_solver_uses_same_physics() -> None:
    p = load_config()
    kwargs = {"duration_s": 100, "steps": [InputStep(30, u=0.6)]}
    a = simulate_open_loop(p, method="RK45", **kwargs)
    b = simulate_open_loop(p, method="DOP853", **kwargs)
    assert np.max(np.abs(a.tc_c - b.tc_c)) < 1e-5


def test_figure_uses_real_results_and_has_five_axes() -> None:
    import matplotlib.pyplot as plt

    df = simulate_open_loop(load_config(), duration_s=15)
    fig = make_open_loop_figure(df, title="Test physical output")
    assert len(fig.axes) == 5
    assert "time" in fig.axes[-1].get_xlabel().lower()
    plt.close(fig)


def test_plot_rejects_bad_frame() -> None:
    with pytest.raises(ValueError, match="missing required columns"):
        make_open_loop_figure(pd.DataFrame({"time_s": [0]}))
