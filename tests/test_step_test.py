"""ID-01, ID-02, ID-09 and ID-10: physical experiment design."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from heatwin.config import load_config
from heatwin.identification.step_test import create_step_experiment, measure_process_gain
from heatwin.models.plant import PlantInputs, rhs


def test_exact_equilibrium_and_complete_record():
    p = load_config()
    ex = create_step_experiment(p, u0=.4, delta_u=.1, step_time_s=60.37, duration_s=480)
    row = ex.data[ex.data.time_s == 60.37].iloc[0]
    assert row.u == pytest.approx(.5)
    assert row.xv == pytest.approx(.4, abs=1e-10)
    assert row.tc_c == pytest.approx(ex.equilibrium.tc, abs=1e-9)
    assert ex.data.iloc[0].tc_c == pytest.approx(ex.equilibrium.tc)
    assert ex.final_equilibrium.tc > ex.equilibrium.tc
    assert len(ex.data.columns) == 10
    assert set(["tc_c", "th_c", "u", "xv", "mh_kg_s", "q_w"]).issubset(ex.data)
    assert ex.metadata["configuration"]["ua"] == 350
    res = rhs(0, ex.equilibrium.state, PlantInputs.from_params(p, .4), p)
    assert np.max(np.abs(res)) < 1e-12


def test_data_derived_gain_matches_reference():
    p = load_config()
    ex = create_step_experiment(p)
    measured = measure_process_gain(ex.data, 60)
    exact = (ex.final_equilibrium.tc - ex.equilibrium.tc) / .1
    assert measured == pytest.approx(exact, abs=2e-4)


def test_positive_and_negative_steps():
    p = load_config()
    for du in [.05, .1, -.05, -.1]:
        ex = create_step_experiment(p, u0=.5, delta_u=du)
        dy = ex.data.tc_c.iloc[-1] - ex.data.tc_c.iloc[0]
        assert dy * du > 0


def test_distinct_operating_points_have_different_local_gains():
    p = load_config()
    gains = [measure_process_gain(create_step_experiment(p, u0=u, delta_u=.05).data, 60)
             for u in [.3, .4, .5, .6]]
    assert max(gains)-min(gains) > 1.0


def test_repeated_runs_bitwise_identical():
    p = load_config()
    a = create_step_experiment(p)
    b = create_step_experiment(p)
    pd.testing.assert_frame_equal(a.data, b.data, check_exact=True)
    assert a.metadata == b.metadata


@pytest.mark.parametrize("kwargs", [
    {"delta_u": 0}, {"delta_u": -.5}, {"u0": 1.1}, {"u0": .99, "delta_u": .1},
    {"duration_s": 0}, {"step_time_s": 0}, {"step_time_s": 480},
    {"step_time_s": float("nan")}, {"delta_u": float("inf")},
])
def test_invalid_step_experiments(kwargs):
    with pytest.raises(ValueError):
        create_step_experiment(load_config(), **kwargs)


def test_gain_measurement_rejects_flat_or_bad_data():
    ex = create_step_experiment(load_config())
    bad = ex.data.copy()
    bad["tc_c"] = 55.0
    with pytest.raises(ValueError, match="flat|Flat|Near-zero"):
        measure_process_gain(bad, 60)
    bad2 = ex.data.copy()
    bad2.loc[5, "tc_c"] = np.nan
    with pytest.raises(ValueError):
        measure_process_gain(bad2, 60)
    with pytest.raises(ValueError):
        measure_process_gain(ex.data.iloc[:5], 60)


def test_new_parameter_set_changes_model_physics_without_hardcoded_values():
    p = replace(load_config(), ua=420.0)
    a = create_step_experiment(p)
    b = create_step_experiment(load_config())
    assert a.equilibrium.tc != pytest.approx(b.equilibrium.tc)
