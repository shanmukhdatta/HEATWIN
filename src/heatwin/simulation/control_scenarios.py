"""Standard reusable Phase 4 sampled setpoint/disturbance experiments."""

from dataclasses import dataclass

from heatwin.simulation.closed_loop import SetpointStep
from heatwin.simulation.open_loop import InputStep


@dataclass(frozen=True)
class ControlScenario:
    name: str
    duration_s: float
    setpoint_steps: tuple[SetpointStep, ...] = ()
    disturbance_steps: tuple[InputStep, ...] = ()


def standard_scenarios(setpoint_c: float = 55.0) -> dict[str, ControlScenario]:
    """Default nominal tests use illustrative inlet conditions from Phase 1."""
    return {
        "nominal_hold": ControlScenario("nominal_hold", 300.0),
        "positive_setpoint": ControlScenario("positive_setpoint", 420.0,
                                               (SetpointStep(60, setpoint_c + 2),)),
        "negative_setpoint": ControlScenario("negative_setpoint", 420.0,
                                               (SetpointStep(60, setpoint_c - 2),)),
        "multiple_setpoints": ControlScenario("multiple_setpoints", 480.0,
                                             (SetpointStep(60, setpoint_c + 2),
                                              SetpointStep(180, setpoint_c - 1),
                                              SetpointStep(300, setpoint_c + 1))),
        "cold_inlet": ControlScenario("cold_inlet", 420.0, (),
                                      (InputStep(100, tc_in=27.0),)),
        "hot_inlet": ControlScenario("hot_inlet", 420.0, (),
                                     (InputStep(100, th_in=75.0),)),
        "cold_flow": ControlScenario("cold_flow", 420.0, (),
                                     (InputStep(100, mc=0.035),)),
        "windup": ControlScenario("windup", 540.0,
                                  (SetpointStep(60, setpoint_c + 25),
                                   SetpointStep(220, setpoint_c))),
    }
