"""Smoke tests for the real src-layout Python package."""

from importlib import import_module

import pytest

import heatwin


def test_package_version() -> None:
    assert heatwin.__version__ == "0.1.0"


@pytest.mark.parametrize(
    "module",
    [
        "heatwin.config",
        "heatwin.models",
        "heatwin.control",
        "heatwin.identification",
        "heatwin.simulation",
        "heatwin.diagnostics",
        "heatwin.visualization",
    ],
)
def test_package_submodules_import(module: str) -> None:
    assert import_module(module) is not None
