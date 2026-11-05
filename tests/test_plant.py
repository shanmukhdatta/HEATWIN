"""PHY-01: first-law energy balances and independent input/state checks."""

from dataclasses import replace

import numpy as np
import pytest

from heatwin.config import PlantParameters, load_config
from heatwin.models.plant import (
    ModelError,
    PlantInputs,
    heat_transfer_rate,
    rhs,
    validate_state,
)


@pytest.fixture
def p() -> PlantParameters:
    return load_config()


@pytest.mark.parametrize("tc,th,xv", [(40.0, 70.0, 0.0), (55.0, 64.0, 0.5),
                                      (70.0, 40.0, 1.0), (20.0, 90.0, 0.123)])
def test_phy01_energy_terms_cancel(p: PlantParameters, tc: float, th: float, xv: float) -> None:
    """The two internal Q terms must cancel, leaving only inlet enthalpy terms."""
    inputs = PlantInputs.from_params(p, u=xv)
    output = rhs(3.0, [tc, th, xv], inputs, p)
    cc = p.rho * p.vc * p.cp
    ch = p.rho * p.vh * p.cp
    mh = p.mh_min + (p.mh_max - p.mh_min) * xv
    external = inputs.mc * p.cp * (inputs.tc_in - tc) + mh * p.cp * (inputs.th_in - th)
    assert cc * output[0] + ch * output[1] == pytest.approx(external, abs=1e-9)


def test_heat_transfer_sign(p: PlantParameters) -> None:
    assert heat_transfer_rate(40, 70, p) == pytest.approx(10500.0)
    assert heat_transfer_rate(70, 40, p) == pytest.approx(-10500.0)
    assert heat_transfer_rate(40, 40, p) == 0.0


def test_rhs_uses_changed_inlet_temperature(p: PlantParameters) -> None:
    base = PlantInputs.from_params(p, 0.4)
    cool = replace(base, tc_in=27.0)
    a = rhs(0, [54, 64, 0.4], base, p)
    b = rhs(0, [54, 64, 0.4], cool, p)
    assert b[0] - a[0] == pytest.approx(p.mc * -3.0 / (p.rho * p.vc))
    assert b[1] == a[1]
    assert b[2] == a[2]


def test_rhs_shape(p: PlantParameters) -> None:
    out = rhs(0, [50, 65, 0.4], PlantInputs.from_params(p, 0.4), p)
    assert out.shape == (3,)
    assert np.all(np.isfinite(out))


@pytest.mark.parametrize("bad", [[55, 65], [55, 65, 0.4, 1.0], [55, float("nan"), 0.4],
                                  [55, 65, float("inf")], "bad", [55, 65, "0.4"]])
def test_reject_bad_state(p: PlantParameters, bad: object) -> None:
    with pytest.raises(ModelError, match="State"):
        rhs(0, bad, PlantInputs.from_params(p, 0.4), p)


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_invalid_initial_valve_position(bad: float) -> None:
    with pytest.raises(ModelError, match="valve position"):
        validate_state([50, 65, bad], initial=True)


@pytest.mark.parametrize("field,value", [
    ("mc", -0.01), ("tc_in", float("nan")), ("th_in", float("inf")),
    ("u", True), ("u", "0.4"),
])
def test_invalid_process_inputs(field: str, value: object) -> None:
    values = {"u": 0.4, "tc_in": 30.0, "th_in": 80.0, "mc": 0.03}
    values[field] = value
    with pytest.raises(ValueError, match=field):
        PlantInputs(**values)


def test_invalid_time(p: PlantParameters) -> None:
    with pytest.raises(ValueError, match="simulation time"):
        rhs(float("nan"), [50, 65, 0.4], PlantInputs.from_params(p, 0.4), p)
