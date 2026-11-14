"""HTTP interface to the validated simulation and identified twin.

Each request is independent. Parameter changes create a new deterministic replay;
the browser never computes plant dynamics.
"""

from functools import lru_cache
from typing import Literal

import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from heatwin.core import Parameters, fit_fopdt, metrics, simulate
from heatwin.diagnostics import predict_twin, residual_alarm
from heatwin.tuning import tune

app = FastAPI(title="HEATWIN simulation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Request(BaseModel):
    duration: int = Field(default=360, ge=60, le=1200)
    setpoint: float = Field(default=57, ge=30, le=75, allow_inf_nan=False)
    kp: float = Field(default=0.04, ge=0, le=1, allow_inf_nan=False)
    ki: float = Field(default=0.001, ge=0, le=0.1, allow_inf_nan=False)
    kd: float = Field(default=0.08, ge=0, le=10, allow_inf_nan=False)
    ua: float = Field(default=350, gt=0, le=1000, allow_inf_nan=False)
    controller: Literal["P", "PI", "PID"] = "PID"
    tuning: Literal["manual", "imc", "zn", "cohen-coon"] = "manual"
    mode: Literal["auto", "manual"] = "auto"
    manual_valve: float = Field(default=0.4, ge=0, le=1, allow_inf_nan=False)
    compare: bool = False
    fault: Literal[
        "none",
        "sensor_bias",
        "sensor_drift",
        "noise",
        "cold_inlet",
        "flow",
        "degradation",
        "stuck",
    ] = "none"
    fault_time: int = Field(default=120, ge=0, le=1200)
    seed: int = 42
    initial_state: tuple[float, float, float] | None = None

    @field_validator("initial_state")
    @classmethod
    def valid_initial_state(cls, value):
        if value is not None and (
            not np.all(np.isfinite(value)) or not 0 <= value[2] <= 1
        ):
            raise ValueError(
                "initial state requires finite temperatures and a valve fraction in [0, 1]"
            )
        return value


@lru_cache(maxsize=1)
def identified_model():
    training = simulate(open_loop=True, duration=450)
    step = training[training.time >= 60]
    return fit_fopdt(
        step.time.to_numpy() - 60, (step.tc.to_numpy() - step.tc.iloc[0]) / 0.1
    )


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/run")
def run(request: Request):
    model = identified_model()
    gains = (
        (request.kp, request.ki, request.kd)
        if request.tuning == "manual"
        else tune(request.tuning, *model)
    )
    runs = {}
    modes = ["P", "PI", "PID"] if request.compare else [request.controller]
    for mode in modes:
        selected = (
            gains[0],
            gains[1] if mode != "P" else 0,
            gains[2] if mode == "PID" else 0,
        )
        options = {
            "bias": 2.0 if request.fault == "sensor_bias" else 0.0,
            "sensor_drift": 0.01 if request.fault == "sensor_drift" else 0.0,
            "noise": 0.4 if request.fault == "noise" else 0.0,
            "disturbance": -3.0 if request.fault == "cold_inlet" else 0.0,
            "flow_factor": 1.3 if request.fault == "flow" else 1.0,
            "degradation": 0.7 if request.fault == "degradation" else 1.0,
            "stuck": request.fault == "stuck",
        }
        data = simulate(
            p=Parameters(ua=request.ua),
            duration=request.duration,
            setpoint=request.setpoint,
            step_time=30,
            gains=selected,
            fault_time=request.fault_time,
            seed=request.seed,
            open_loop=request.mode == "manual",
            open_loop_value=request.manual_valve,
            noise_at_fault=True,
            initial_state=request.initial_state,
            **options,
        )
        data["twin"] = predict_twin(data.time, data.command, data.tc.iloc[0], *model)
        data["residual"] = data.measurement - data.twin
        data["alarm"] = residual_alarm(data.residual, 1.0, 3)
        data["hot_flow"] = 0.01 + 0.09 * data.valve
        data["heat_w"] = data.ua * (data.th - data.tc)
        view = data[data.time >= 30]
        summary = metrics(
            view.time.to_numpy(),
            view.tc.to_numpy(),
            view.setpoint.to_numpy(),
            view.command.to_numpy(),
        )
        runs[mode] = {
            "samples": data.to_dict(orient="records"),
            "metrics": summary,
            "gains": list(selected),
        }
    return clean(
        {
            "runs": runs,
            "model": list(map(float, model)),
            "hot_inlet": 80.0,
            "sample_time": 1.0,
            "seed": request.seed,
        }
    )
