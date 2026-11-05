"""Load and validate the baseline heat-exchanger configuration.

Phase 1 deliberately does not implement the heat exchanger dynamics.
Default paths are relative to the source checkout, never the process CWD.
"""

from dataclasses import dataclass, fields
from math import isfinite
from numbers import Real
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"


class ConfigurationError(ValueError):
    """An unreadable, malformed, or physically invalid configuration."""


@dataclass(frozen=True, slots=True)
class PlantParameters:
    """SI-unit process parameters; temperatures are in degrees Celsius.

    All fields except ``seed`` are finite real numbers. Validation also runs
    when constructing this class directly, not only when loading YAML.
    """

    rho: float  # kg/m^3
    cp: float  # J/(kg K)
    vc: float  # m^3
    vh: float  # m^3
    ua: float  # W/K
    tc_in: float  # deg C
    th_in: float  # deg C
    mc: float  # kg/s
    mh_min: float  # kg/s
    mh_max: float  # kg/s
    valve_tau: float  # s
    sample_time: float  # s
    setpoint: float  # deg C
    seed: int  # random seed, dimensionless

    def __post_init__(self) -> None:
        for field in fields(self):
            name = field.name
            value = getattr(self, name)
            if name == "seed":
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ConfigurationError("Parameter 'seed' must be a nonnegative integer.")
                continue
            if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
                raise ConfigurationError(f"Parameter '{name}' must be a finite real number.")
            object.__setattr__(self, name, float(value))

        for name in ("rho", "cp", "vc", "vh", "ua", "valve_tau", "sample_time"):
            if getattr(self, name) <= 0:
                raise ConfigurationError(f"Parameter '{name}' must be greater than zero.")
        for name in ("mc", "mh_min", "mh_max"):
            if getattr(self, name) < 0:
                raise ConfigurationError(f"Parameter '{name}' must be nonnegative.")
        if self.mh_max <= self.mh_min:
            raise ConfigurationError("Parameter 'mh_max' must exceed 'mh_min'.")


def load_config(path: str | Path | None = None) -> PlantParameters:
    """Read a YAML configuration from ``path`` or the checkout's default file.

    Explicit relative paths resolve against the caller's current directory.
    The default is absolute, independent of the current working directory.
    """

    config_path = DEFAULT_CONFIG_PATH if path is None else Path(path).expanduser()
    try:
        contents = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Cannot read configuration '{config_path}': {exc}") from exc

    try:
        data = yaml.safe_load(contents)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in configuration '{config_path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Configuration '{config_path}' must contain a YAML mapping of parameters."
        )

    if any(not isinstance(key, str) for key in data):
        raise ConfigurationError("Configuration parameter names must be strings.")

    required = {field.name for field in fields(PlantParameters)}
    missing = sorted(required - data.keys())
    unknown = sorted(data.keys() - required)
    if missing:
        raise ConfigurationError(f"Missing required parameter(s): {', '.join(missing)}.")
    if unknown:
        raise ConfigurationError(f"Unknown configuration parameter(s): {', '.join(map(str, unknown))}.")

    return PlantParameters(**data)
