"""PID-07/08/09: exact tuning-rule algebra and actual Phase 3 artifact."""

import json

import pytest

from heatwin.control.tuning import (
    ProcessModel,
    imc_pi,
    load_identified_model,
    manual_pi,
    ziegler_nichols,
)


def example():
    return ProcessModel(process_gain=2, tau_s=20, theta_s=5,
                        nominal_u=0.4, nominal_tc_c=55, sample_time_s=1)


@pytest.mark.parametrize("mode,multiplier,ti,td", [
    ("P", 1, None, 0), ("PI", 0.9, 16.65, 0), ("PID", 1.2, 10, 2.5),
])
def test_zn_equations(mode, multiplier, ti, td):
    s = ziegler_nichols(example(), mode=mode)
    assert s.kc == pytest.approx(multiplier * 20 / (2 * 5))
    assert s.ti_s == pytest.approx(ti) if ti is not None else s.ti_s is None
    assert s.td_s == pytest.approx(td)


def test_imc_equations_and_lambda_sensitivity():
    fast = imc_pi(example(), lambda_s=5)
    slow = imc_pi(example(), lambda_s=40)
    assert fast.kc == pytest.approx(20 / (2 * 10))
    assert fast.ti_s == 20
    assert slow.kc == pytest.approx(20 / (2 * 45))
    assert slow.kc < fast.kc
    assert manual_pi(example()).kc == pytest.approx(0.5 / 2)


def test_signed_reverse_gain_rule():
    m = ProcessModel(-2, 20, 5, .4, 55, 1)
    assert imc_pi(m, lambda_s=15).kc < 0
    assert ziegler_nichols(m, mode="PI").kc < 0


def test_identification_artifact_is_read_from_disk(tmp_path):
    p = tmp_path / "model.json"
    p.write_text(json.dumps({"selected_model": "FOPDT", "process_gain": 12,
                             "time_constant_s": 27, "effective_dead_time_s": 4,
                             "operating_point": {"u": .45, "tc": 56},
                             "sampling_interval_s": 2}), encoding="utf-8")
    m = load_identified_model(p)
    assert m.process_gain == 12
    assert imc_pi(m, lambda_s=27).bias == .45


@pytest.mark.parametrize("field,value", [(0, 0), (1, 0), (1, -1), (2, -1), (5, 0)])
def test_invalid_process_model(field, value):
    values = [2., 20., 5., .4, 55., 1.]
    values[field] = value
    with pytest.raises(ValueError):
        ProcessModel(*values)


def test_zero_dead_time_zn_invalid_but_imc_defined():
    m = ProcessModel(2, 20, 0, .4, 55, 1)
    with pytest.raises(ValueError, match="dead time"):
        ziegler_nichols(m, mode="PI")
    assert imc_pi(m, lambda_s=10).kc == pytest.approx(1.0)


def test_invalid_lambda_and_file(tmp_path):
    for value in (-1, 0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            imc_pi(example(), lambda_s=value)
    with pytest.raises(ValueError):
        load_identified_model(tmp_path / "nonexistent.json")
