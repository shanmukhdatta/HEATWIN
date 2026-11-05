"""Scientific Matplotlib plots using the simulated open-loop trajectory only."""

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

import pandas as pd


_REQUIRED_COLUMNS = {
    "time_s", "tc_c", "th_c", "u", "xv", "mh_kg_s", "q_w",
}


def make_open_loop_figure(data: pd.DataFrame, *, title: str = "Open-loop response") -> Figure:
    """Return a five-panel temperature/actuator/flow/heat-duty figure.

    No fabricated or smoothed data are introduced.  Curves use the actual
    output of simulate_open_loop and retain physical units in their labels.
    """
    missing = sorted(_REQUIRED_COLUMNS - set(data.columns))
    if missing:
        raise ValueError(f"Plot input is missing required columns: {', '.join(missing)}")
    if data.empty:
        raise ValueError("Cannot plot an empty trajectory.")

    t = data["time_s"]
    fig, axs = plt.subplots(5, 1, figsize=(11, 13), sharex=True, constrained_layout=True)
    axs[0].plot(t, data["tc_c"], label="Cold outlet Tc")
    axs[0].set_ylabel("Cold outlet (°C)")
    axs[1].plot(t, data["th_c"], label="Hot outlet Th")
    axs[1].set_ylabel("Hot outlet (°C)")
    axs[2].step(t, data["u"], where="post", label="Valve command u")
    axs[2].plot(t, data["xv"], label="Actual valve position xv")
    axs[2].set_ylabel("Valve fraction (0–1)")
    axs[2].set_ylim(-0.05, 1.05)
    axs[3].plot(t, data["mh_kg_s"], label="Hot-side mass flow")
    axs[3].set_ylabel("Hot flow (kg/s)")
    axs[4].plot(t, data["q_w"], label="Q = UA(Th−Tc)")
    axs[4].set_ylabel("Heat duty (W)")
    axs[4].set_xlabel("Simulation time (s)")
    for ax in axs:
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3)
    fig.suptitle(title)
    return fig
