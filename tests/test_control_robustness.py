"""PID-18 plant perturbation checks (simulation-based, not stability proof)."""

from dataclasses import replace

import numpy as np
import pytest

from pathlib import Path

from heatwin.config import load_config
from heatwin.control.tuning import imc_pi, load_identified_model
from heatwin.diagnostics.control_metrics import evaluate_control
from heatwin.models.plant import steady_state_for_valve
from heatwin.simulation.closed_loop import SetpointStep, simulate_closed_loop


@pytest.mark.parametrize("field,factor", [
    ("ua", .8), ("ua", 1.2), ("valve_tau", 2), ("th_in", .9), ("th_in", 1.1),
    ("mc", 1.15),
])
def test_no_retuning_for_plant_parameter_variations(field, factor):
    p = load_config()
    model = load_identified_model(
        Path(__file__).resolve().parents[1] / "configs/identified/phase3_fopdt_nominal.json"
    )
    settings = imc_pi(model, lambda_s=model.tau_s)
    perturbed = replace(p, **{field: getattr(p, field) * factor})
    d = simulate_closed_loop(perturbed, settings, duration_s=360,
                             setpoint_steps=[SetpointStep(60, 57)])
    metrics = evaluate_control(d, window_start_s=60, reference_initial_c=55)
    assert np.isfinite(d.tc_c.to_numpy()).all()
    assert np.isfinite([metrics.iae_c_s, metrics.ise_c2_s, metrics.itae_c_s2]).all()
    assert d.u.between(0, 1).all()
    reachable_max = steady_state_for_valve(1.0, perturbed).tc
    if reachable_max >= 57:
        assert abs(d.tc_c.iloc[-1] - 57) < .18
    else:
        # Physical limitation: no controller can achieve a 57°C target when
        # the perturbed maximum-hot-flow equilibrium is below 57°C.
        assert d.u.iloc[-1] == pytest.approx(1.0)
        assert d.tc_c.iloc[-1] == pytest.approx(reachable_max, abs=.02)
