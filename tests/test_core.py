import numpy as np
from heatwin.core import Parameters, equilibrium, rhs, PID, simulate, fit_fopdt, fopdt, metrics


def test_equilibrium_and_energy_conservation():
    p = Parameters()
    y = equilibrium(0.4, p)
    assert np.max(np.abs(rhs(y, 0.4, p))) < 1e-12
    y = np.array([45., 70., .4])
    d = rhs(y, .4, p)
    mh = p.mh_min + (p.mh_max-p.mh_min)*y[2]
    expected = p.mc*p.cp*(p.tc_in-y[0])+mh*p.cp*(p.th_in-y[1])
    assert np.isclose(p.rho*p.cp*(p.vc*d[0]+p.vh*d[1]), expected)


def test_pid_saturation_and_recovery():
    c = PID(.1, .02, 0, bias=.4)
    for _ in range(100):
        assert 0 <= c.update(100, 50) <= 1
    assert c.update(50, 50) < 1


def test_simulation_is_reproducible_and_tracks():
    a = simulate(seed=42)
    b = simulate(seed=42)
    assert a.equals(b)
    assert abs(a.tc.iloc[-1]-57) < .15


def test_fopdt_fits_synthetic_step():
    t = np.arange(200.)
    y = fopdt(t, 3., 20., 5.)
    k, tau, delay = fit_fopdt(t, y)
    assert np.allclose([k, tau, delay], [3, 20, 5], atol=.2)


def test_metrics_integrals():
    m = metrics(np.arange(3.), np.array([0., 1., 2.]), np.ones(3)*2, np.zeros(3))
    assert np.isclose(m['IAE'], 2)
    assert np.isclose(m['ISE'], 3)


def test_residual_alarm_requires_persistence():
    from heatwin.diagnostics import residual_alarm
    assert residual_alarm([0, 2, 0, 2, 2, 2], 1, 3).tolist() == [False, False, False, False, False, True]


def test_twin_step_prediction_uses_held_out_input():
    from heatwin.diagnostics import predict_twin
    t = np.arange(10.)
    u = np.r_[np.zeros(2), np.ones(8)]
    y = predict_twin(t, u, 50., 2., 3., 0.)
    assert y[1] == 50
    assert y[-1] > 51


def test_dashboard_runs_simulation():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'app.py')).run()
    assert not app.exception
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert len(app.get('download_button')) == 1
