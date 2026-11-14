import numpy as np
import pytest

from heatwin.core import Parameters, equilibrium, simulate


def test_open_loop_independent_step_and_flow_disturbance():
    d = simulate(
        duration=180,
        step_time=20,
        open_loop=True,
        open_loop_value=0.3,
        fault_time=90,
        flow_factor=1.2,
    )
    assert d.command.iloc[30] == 0.3
    assert d.mc.iloc[100] == pytest.approx(0.036)
    assert d.tc.iloc[-1] < equilibrium(0.3, Parameters())[0]


def test_sensor_drift_and_stuck_actuator():
    d = simulate(duration=120, fault_time=60, sensor_drift=0.02, stuck=True)
    assert d.measurement.iloc[-1] - d.tc.iloc[-1] == pytest.approx(1.2)
    assert d.valve.iloc[-1] == pytest.approx(d.valve.iloc[60])


def test_first_order_fit_and_validation():
    from heatwin.identification import first_order, fit_first_order

    t = np.arange(150.0)
    assert fit_first_order(t, first_order(t, 4.0, 22.0)) == pytest.approx(
        (4.0, 22.0), abs=0.05
    )


def test_tuning_formulas_and_invalid_delay():
    from heatwin.tuning import tune

    assert np.allclose(tune("zn", 2.0, 20.0, 4.0), (3.0, 0.375, 6.0))
    assert all(np.isfinite(tune("imc", 2.0, 20.0, 4.0)))
    with pytest.raises(ValueError):
        tune("cohen-coon", 2.0, 20.0, 0.0)


def test_fault_evaluation_reports_false_alarm_and_delay():
    from heatwin.diagnostics import detection_metrics

    result = detection_metrics([0, 1, 2, 3, 4], [False, True, False, False, True], 3)
    assert result["false_alarm_fraction"] == pytest.approx(1 / 3)
    assert result["detection_delay_s"] == 1


def test_dashboard_flow_fault_and_comparison():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    app.selectbox[1].select("Cold flow +30%").run()
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert len(app.get("download_button")) == 1
    assert len(app.dataframe) >= 1


def test_pid_bumpless_initialization():
    from heatwin.core import PID

    controller = PID(0.1, 0.01, 0.2)
    controller.initialize(setpoint=55.0, measurement=54.0, output=0.6)
    assert controller.update(55.0, 54.0) == pytest.approx(0.61)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dt": float("nan")},
        {"noise": float("nan")},
        {"setpoint": float("nan")},
        {"duration": 0},
        {"flow_factor": float("nan")},
    ],
)
def test_simulation_rejects_invalid_numerical_inputs(kwargs):
    with pytest.raises(ValueError):
        simulate(**kwargs)


def test_pid_rejects_nonfinite_measurement():
    from heatwin.core import PID

    with pytest.raises(ValueError):
        PID(0.1, 0.01, 0).update(50, float("nan"))


def test_pid_derivative_mode_controls_setpoint_kick():
    from heatwin.core import PID

    measurement = PID(0, 0, 0.1, filter_tau=0, derivative_on_measurement=True)
    error = PID(0, 0, 0.1, filter_tau=0, derivative_on_measurement=False)
    measurement.update(50, 50)
    error.update(50, 50)
    assert measurement.update(51, 50) == pytest.approx(0.4)
    assert error.update(51, 50) == pytest.approx(0.5)


def test_analytic_equilibrium_temperature_for_given_setpoint():
    p = Parameters()
    target = 55.0
    heat = p.mc * p.cp * (target - p.tc_in)
    hot_out = target + heat / p.ua
    hot_flow = heat / (p.cp * (p.th_in - hot_out))
    opening = (hot_flow - p.mh_min) / (p.mh_max - p.mh_min)
    state = equilibrium(opening, p)
    assert state[0] == pytest.approx(target, abs=1e-10)
    assert opening == pytest.approx(0.4085, abs=0.001)


def test_solver_grid_consistency_and_positive_step():
    fine = simulate(duration=180, dt=0.5, open_loop=True)
    coarse = simulate(duration=180, dt=1, open_loop=True)
    assert np.max(abs(fine.tc.to_numpy()[::2] - coarse.tc.to_numpy())) < 1e-5
    assert coarse.tc.iloc[-1] > coarse.tc.iloc[60]


def test_safety_limits_report_low_and_high_observations():
    from heatwin.diagnostics import safety_limits

    assert safety_limits([20.0, 50.0, 70.0], low=25.0, high=65.0).tolist() == [
        True,
        False,
        True,
    ]
    with pytest.raises(ValueError):
        safety_limits([40.0], low=70.0, high=65.0)


def test_configuration_loads_and_rejects_unknown_fields(tmp_path):
    from heatwin.config import load_parameters

    path = tmp_path / "plant.json"
    path.write_text('{"ua": 250}')
    assert load_parameters(path).ua == 250
    path.write_text('{"unknown": 1}')
    with pytest.raises(ValueError):
        load_parameters(path)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_twin_rejects_nonfinite_inputs(bad):
    from heatwin.diagnostics import predict_twin

    with pytest.raises(ValueError):
        predict_twin([0, 1], [0, 1], 50.0, 2.0, bad, 0.0)
    with pytest.raises(ValueError):
        predict_twin([0, 1], [0, bad], 50.0, 2.0, 3.0, 0.0)


def test_metrics_rejects_invalid_times():
    from heatwin.core import metrics

    with pytest.raises(ValueError):
        metrics([0.0, 0.0], [50.0, 51.0], [52.0, 52.0], [0.4, 0.5])


def test_local_closed_loop_linearization_predicts_decay():
    from heatwin.stability import local_stability

    result = local_stability((0.04, 0.001, 0.08))
    assert result["spectral_radius"] < 1.0
    assert result["stable"]
