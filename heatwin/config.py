"""Read validated plant configuration from JSON."""

import json
from dataclasses import fields
from pathlib import Path

from heatwin.core import Parameters


def load_parameters(path):
    values = json.loads(Path(path).read_text())
    if not isinstance(values, dict) or set(values) - {
        f.name for f in fields(Parameters)
    }:
        raise ValueError("configuration must contain only known parameter names")
    try:
        return Parameters(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid plant configuration") from exc
