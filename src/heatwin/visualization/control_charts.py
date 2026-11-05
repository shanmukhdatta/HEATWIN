"""Publication-ready matplotlib visualizations of executed closed-loop data."""

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure


def comparison_figure(runs: dict[str, pd.DataFrame], *, title: str,
                      signal: str = "tc_c", ylabel: str = "Cold outlet (°C)",
                      include_setpoint: bool = True) -> Figure:
    if not runs:
        raise ValueError("At least one recorded run is required")
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    for name, data in runs.items():
        if not {"time_s", signal}.issubset(data.columns) or data.empty:
            raise ValueError("Run is missing required recorded signals")
        ax.plot(data.time_s, data[signal], label=name)
    if include_setpoint:
        first = next(iter(runs.values()))
        ax.step(first.time_s, first.setpoint_c, where="post", linestyle="--",
                linewidth=1.4, label="Setpoint")
    ax.set(title=title, xlabel="Simulation time (s)", ylabel=ylabel)
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    return fig


def actuator_figure(runs: dict[str, pd.DataFrame]) -> Figure:
    if not runs:
        raise ValueError("Runs cannot be empty")
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True, constrained_layout=True)
    for name, d in runs.items():
        axes[0].step(d.time_s, d.u, where="post", label=f"{name} command")
        axes[1].plot(d.time_s, d.xv, label=f"{name} position")
        axes[2].plot(d.time_s, d.mh_kg_s, label=f"{name} flow")
    for ax, label in zip(axes, ["Valve command (fraction)", "Actual valve (fraction)",
                                "Hot-side mass flow (kg/s)"], strict=True):
        ax.set_ylabel(label)
        ax.grid(alpha=0.25)
        ax.legend()
    axes[-1].set_xlabel("Simulation time (s)")
    fig.suptitle("Valve actuator and hot-flow dynamics")
    return fig


def windup_figure(runs: dict[str, pd.DataFrame]) -> Figure:
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True, constrained_layout=True)
    for name, d in runs.items():
        axes[0].plot(d.time_s, d.tc_c, label=name)
        axes[1].plot(d.time_s, d.i_term, label=name)
        axes[2].step(d.time_s, d.u, where="post", label=name)
    axes[0].step(next(iter(runs.values())).time_s,
                 next(iter(runs.values())).setpoint_c, where="post", linestyle="--",
                 label="Setpoint")
    for ax, label in zip(axes, ["Cold outlet (°C)", "Integral contribution (fraction)",
                                "Valve command (fraction)"], strict=True):
        ax.set_ylabel(label)
        ax.grid(alpha=0.25)
        ax.legend()
    axes[-1].set_xlabel("Simulation time (s)")
    fig.suptitle("Infeasible setpoint: anti-windup and recovery")
    return fig


def metrics_figure(metrics: pd.DataFrame) -> Figure:
    if metrics.empty or not {"controller", "iae_c_s", "ise_c2_s", "itae_c_s2"}.issubset(metrics):
        raise ValueError("Missing performance metrics")
    fig, axs = plt.subplots(3, 1, figsize=(10, 9), constrained_layout=True)
    for ax, column, ylabel in zip(axs, ["iae_c_s", "ise_c2_s", "itae_c_s2"],
                                  ["IAE (°C·s)", "ISE (°C²·s)", "ITAE (°C·s²)"], strict=True):
        ax.bar(metrics.controller, metrics[column])
        ax.set_ylabel(ylabel)
        ax.tick_params(axis="x", labelrotation=20)
    fig.suptitle("Controller performance after 60 s setpoint change")
    return fig
