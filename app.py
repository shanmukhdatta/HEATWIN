"""Streamlit landing page; simulation and controllers arrive in later phases."""

import streamlit as st

from heatwin import __version__
from heatwin.config import ConfigurationError, load_config

st.set_page_config(page_title="HEATWIN", page_icon="🌡️", layout="centered")
st.title("HEATWIN — Heat Exchanger Digital Twin")
st.caption(f"Project foundation · version {__version__}")
st.info(
    "Phases 1–2 provide a validated Python heat-exchanger model and open-loop simulator. "
    "The full dashboard, PID controller and independent digital twin "
    "have not been implemented yet."
)

try:
    settings = load_config()
except ConfigurationError as exc:
    st.error(f"Configuration error: {exc}")
else:
    st.subheader("Illustrative physical configuration")
    st.metric("Target cold outlet temperature", f"{settings.setpoint:g} °C")
    st.write(
        f"Cold inlet: {settings.tc_in:g} °C · "
        f"Hot inlet: {settings.th_in:g} °C · "
        f"Sample interval: {settings.sample_time:g} s"
    )
    st.caption("Run scripts/phase2_experiments.py for open-loop physics plots and CSV output.")
