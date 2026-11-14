"""Interactive HEATWIN scenarios backed by the same simulation modules as the studies."""

import pandas as pd
import streamlit as st

from heatwin.core import Parameters, fit_fopdt, metrics, simulate
from heatwin.diagnostics import (
    detection_metrics,
    predict_twin,
    residual_alarm,
    safety_limits,
)
from heatwin.tuning import tune

st.set_page_config(page_title="HEATWIN", layout="wide")
st.title("HEATWIN — heat exchanger digital twin")
st.caption(
    "Illustrative water-to-water simulation; not a validated industrial safety system."
)
with st.sidebar:
    mode = st.selectbox("Controller", ["P", "PI", "PID"])
    fault = st.selectbox(
        "Fault / disturbance at 300 s",
        [
            "None",
            "Sensor bias +2 °C",
            "Sensor drift",
            "Cold inlet −3 °C",
            "Cold flow +30%",
            "Heat transfer −30%",
            "Stuck actuator",
        ],
    )
    method = st.selectbox("Tuning", ["Manual", "IMC", "Ziegler–Nichols", "Cohen–Coon"])
    kp = st.number_input("Kp (fraction/°C)", 0.0, 1.0, 0.04, 0.01, format="%.3f")
    ki = st.number_input("Ki (fraction/(°C s))", 0.0, 1.0, 0.001, 0.001, format="%.3f")
    kd = st.number_input("Kd (fraction s/°C)", 0.0, 10.0, 0.08, 0.01)
    sp = st.slider("Setpoint (°C)", 40.0, 70.0, 57.0)
    ua = st.number_input("Plant UA (W/K)", 1.0, 1000.0, 350.0)
    noise = st.slider("Sensor noise standard deviation (°C)", 0.0, 1.0, 0.0)
    threshold = st.number_input("Residual alarm threshold (°C)", 0.1, 10.0, 1.0)
    run = st.button("Run simulation", type="primary")
if run:
    training = simulate(open_loop=True)
    step = training[training.time >= 60]
    fitted = fit_fopdt(
        step.time.to_numpy() - 60, (step.tc.to_numpy() - step.tc.iloc[0]) / 0.1
    )
    if method != "Manual":
        key = {"IMC": "imc", "Ziegler–Nichols": "zn", "Cohen–Coon": "cohen-coon"}[
            method
        ]
        kp, ki, kd = tune(key, *fitted)
    comparison_gains = (kp, ki, kd)
    if mode == "P":
        ki, kd = 0.0, 0.0
    if mode == "PI":
        kd = 0.0
    options = {
        "p": Parameters(ua=ua),
        "setpoint": sp,
        "noise": noise,
        "bias": 2 if fault.startswith("Sensor bias") else 0,
        "sensor_drift": 0.01 if fault == "Sensor drift" else 0,
        "disturbance": -3 if fault.startswith("Cold inlet") else 0,
        "flow_factor": 1.3 if fault.startswith("Cold flow") else 1.0,
        "degradation": 0.7 if fault.startswith("Heat") else 1.0,
        "stuck": fault.startswith("Stuck"),
    }
    data = simulate(gains=(kp, ki, kd), **options)
    data["twin"] = predict_twin(data.time, data.command, data.tc.iloc[0], *fitted)
    data["residual"] = data.measurement - data.twin
    data["alarm"] = residual_alarm(data.residual, threshold)
    st.write("Actual gains:", {"Kp": kp, "Ki": ki, "Kd": kd})
    simulation_tab, comparison_tab, diagnostics_tab = st.tabs(
        ["Simulation", "Controller comparison", "Twin and monitoring"]
    )
    with simulation_tab:
        st.line_chart(data.set_index("time")[["tc", "measurement", "setpoint"]])
        st.line_chart(data.set_index("time")[["command", "valve"]])
        st.download_button(
            "Download CSV", data.to_csv(index=False), "heatwin.csv", "text/csv"
        )
    with comparison_tab:
        comparisons = {}
        ck, ci, cd = comparison_gains
        for label, gains in {
            "P": (ck, 0, 0),
            "PI": (ck, ci, 0),
            "PID": (ck, ci, cd),
        }.items():
            d = simulate(gains=gains, **options)
            window = d[d.time >= 60]
            comparisons[label] = metrics(
                window.time.to_numpy(),
                window.tc.to_numpy(),
                window.setpoint.to_numpy(),
                window.command.to_numpy(),
            )
        st.caption(
            "Comparison uses the displayed gains, with integral and derivative terms disabled as appropriate."
        )
        st.dataframe(pd.DataFrame(comparisons).T)
    with diagnostics_tab:
        st.caption(
            "Twin is an open-loop FOPDT fit to a separate nominal valve step. Residuals also respond to disturbances and model mismatch."
        )
        st.line_chart(data.set_index("time")[["tc", "measurement", "twin"]])
        st.line_chart(data.set_index("time")[["residual"]])
        st.write(
            "Residual alarm:",
            bool(data.alarm.any()),
            "| Temperature outside 25–65 °C:",
            bool(safety_limits(data.measurement).any()),
        )
        st.json(detection_metrics(data.time, data.alarm, 300))
else:
    st.info("Choose parameters and run the simulation.")
