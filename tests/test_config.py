"""Validation contracts for Phase 1 and the subsequent physical model."""

from dataclasses import FrozenInstanceError, asdict
from pathlib import Path

import pytest
import yaml

from heatwin.config import ConfigurationError, PlantParameters, load_config


@pytest.fixture
def valid_data() -> dict[str, float | int]:
    return asdict(load_config())


def write_yaml(path: Path, data: object) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_default_loads_structured_parameters() -> None:
    params = load_config()
    assert isinstance(params, PlantParameters)
    assert params.rho == pytest.approx(1000.0)
    assert params.cp == pytest.approx(4180.0)
    assert params.vc == pytest.approx(0.001)
    assert params.vh == pytest.approx(0.001)
    assert params.ua == pytest.approx(350.0)
    assert params.tc_in == pytest.approx(30.0)
    assert params.th_in == pytest.approx(80.0)
    assert params.mc == pytest.approx(0.030)
    assert params.mh_min == pytest.approx(0.010)
    assert params.mh_max == pytest.approx(0.100)
    assert params.valve_tau == pytest.approx(4.0)
    assert params.sample_time == pytest.approx(1.0)
    assert params.setpoint == pytest.approx(55.0)
    assert params.seed == 42


def test_parameters_are_immutable() -> None:
    params = load_config()
    with pytest.raises(FrozenInstanceError):
        params.ua = 500.0  # type: ignore[misc]


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="Cannot read configuration"):
        load_config(tmp_path / "does-not-exist.yaml")


def test_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("rho: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid YAML"):
        load_config(path)


@pytest.mark.parametrize("document", ["", "[]", "2", "- abc"])
def test_non_mapping_yaml(tmp_path: Path, document: str) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(document, encoding="utf-8")
    with pytest.raises(ConfigurationError, match="YAML mapping"):
        load_config(path)


def test_missing_required_parameter(tmp_path: Path, valid_data: dict[str, float | int]) -> None:
    valid_data.pop("rho")
    with pytest.raises(ConfigurationError, match="Missing required parameter.*rho"):
        load_config(write_yaml(tmp_path / "missing.yaml", valid_data))


def test_unknown_parameter(tmp_path: Path, valid_data: dict[str, float | int]) -> None:
    valid_data["unused_setting"] = 1
    with pytest.raises(ConfigurationError, match="Unknown configuration parameter.*unused_setting"):
        load_config(write_yaml(tmp_path / "unknown.yaml", valid_data))


@pytest.mark.parametrize("name", ["rho", "cp", "vc", "vh", "ua", "valve_tau"])
@pytest.mark.parametrize("value", [0, -1])
def test_invalid_positive_parameters(
    tmp_path: Path, valid_data: dict[str, float | int], name: str, value: int
) -> None:
    valid_data[name] = value
    with pytest.raises(ConfigurationError, match=rf"'{name}'.*greater than zero"):
        load_config(write_yaml(tmp_path / "invalid.yaml", valid_data))


@pytest.mark.parametrize("name", ["mc", "mh_min", "mh_max"])
def test_negative_mass_flows(
    tmp_path: Path, valid_data: dict[str, float | int], name: str
) -> None:
    valid_data[name] = -0.01
    with pytest.raises(ConfigurationError, match=rf"'{name}'.*nonnegative"):
        load_config(write_yaml(tmp_path / "invalid.yaml", valid_data))


@pytest.mark.parametrize("limits", [(0.1, 0.1), (0.1, 0.05)])
def test_invalid_hot_flow_range(
    tmp_path: Path, valid_data: dict[str, float | int], limits: tuple[float, float]
) -> None:
    valid_data["mh_min"], valid_data["mh_max"] = limits
    with pytest.raises(ConfigurationError, match="'mh_max' must exceed 'mh_min'"):
        load_config(write_yaml(tmp_path / "invalid.yaml", valid_data))


@pytest.mark.parametrize("value", [0, -1])
def test_invalid_sampling_interval(
    tmp_path: Path, valid_data: dict[str, float | int], value: int
) -> None:
    valid_data["sample_time"] = value
    with pytest.raises(ConfigurationError, match="'sample_time'.*greater than zero"):
        load_config(write_yaml(tmp_path / "invalid.yaml", valid_data))


@pytest.mark.parametrize("name", ["rho", "ua", "tc_in", "sample_time", "setpoint"])
@pytest.mark.parametrize("value", ["12.5", None, True, float("nan"), float("inf")])
def test_bad_numeric_types_and_nonfinite_values(
    tmp_path: Path, valid_data: dict[str, float | int], name: str, value: object
) -> None:
    valid_data[name] = value  # type: ignore[assignment]
    with pytest.raises(ConfigurationError, match=rf"'{name}' must be a finite real number"):
        load_config(write_yaml(tmp_path / "invalid.yaml", valid_data))


@pytest.mark.parametrize("value", [-1, 1.5, True, "42"])
def test_invalid_seed(tmp_path: Path, valid_data: dict[str, float | int], value: object) -> None:
    valid_data["seed"] = value  # type: ignore[assignment]
    with pytest.raises(ConfigurationError, match="'seed'.*nonnegative integer"):
        load_config(write_yaml(tmp_path / "invalid.yaml", valid_data))


def test_zero_cold_flow_is_allowed(tmp_path: Path, valid_data: dict[str, float | int]) -> None:
    valid_data["mc"] = 0.0
    assert load_config(write_yaml(tmp_path / "zero-flow.yaml", valid_data)).mc == 0.0


def test_load_default_outside_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_config().setpoint == 55.0


def test_load_explicit_path(
    tmp_path: Path, valid_data: dict[str, float | int]
) -> None:
    valid_data["setpoint"] = 57.0
    file_path = write_yaml(tmp_path / "alternative.yaml", valid_data)
    assert load_config(file_path).setpoint == 57.0


def test_explicit_relative_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, valid_data: dict[str, float | int]
) -> None:
    write_yaml(tmp_path / "custom.yaml", valid_data)
    monkeypatch.chdir(tmp_path)
    assert load_config("custom.yaml") == PlantParameters(**valid_data)


def test_direct_construction_validates(valid_data: dict[str, float | int]) -> None:
    valid_data["rho"] = -1.0
    with pytest.raises(ConfigurationError, match="'rho'"):
        PlantParameters(**valid_data)


def test_nonstring_yaml_key(tmp_path: Path, valid_data: dict[str, float | int]) -> None:
    valid_data[7] = 1  # type: ignore[index]
    with pytest.raises(ConfigurationError, match="parameter names must be strings"):
        load_config(write_yaml(tmp_path / "nonstring.yaml", valid_data))
