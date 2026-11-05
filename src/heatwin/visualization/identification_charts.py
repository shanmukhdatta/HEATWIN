"""Publication-ready plots driven exclusively by executed Phase 2 trajectories."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def make_figures(training: pd.DataFrame, predictions: dict[str, np.ndarray],
                 operating_points: pd.DataFrame, output_dir: str | Path) -> list[str]:
    """Export figures 1–7; predictions are already evaluated on training times."""
    needed = {"time_s", "tc_c", "th_c", "u", "xv"}
    if not needed.issubset(training.columns):
        raise ValueError("Missing required nonlinear plant signals")
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    t = training.time_s.to_numpy()
    real = training.tc_c.to_numpy()
    for name, pred in predictions.items():
        if np.asarray(pred).shape != real.shape or not np.all(np.isfinite(pred)):
            raise ValueError(f"Invalid predicted response: {name}")
    files = []

    def save(fig, slug):
        target = path / slug
        fig.savefig(target, dpi=160)
        plt.close(fig)
        files.append(str(target))

    fig, axs = plt.subplots(4, 1, figsize=(10, 9), sharex=True, constrained_layout=True)
    for ax, col, label in zip(
        axs, ["tc_c", "th_c", "u", "xv"],
        ["Cold outlet temperature (°C)", "Hot outlet temperature (°C)",
         "Valve command (fraction)", "Actual valve position (fraction)"], strict=True,
    ):
        if col == "u":
            ax.step(t, training[col], where="post", label=col)
        else:
            ax.plot(t, training[col], label=col)
        ax.set_ylabel(label)
        ax.grid(alpha=.25)
        ax.legend()
    axs[-1].set_xlabel("Time (s)")
    fig.suptitle("Figure 1 — Actual three-state nonlinear open-loop step response")
    save(fig, "figure_1_physical_step.png")

    for n, name, label in [(2, "fo", "First order"), (3, "fopdt", "FOPDT"),
                            (4, "second_order", "Two-real-pole second order")]:
        fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
        ax.plot(t, real, label="Nonlinear reference plant", linewidth=2)
        ax.plot(t, predictions[name], "--", label=label)
        ax.set(title=f"Figure {n} — {label} fit", xlabel="Time (s)",
               ylabel="Cold outlet temperature (°C)")
        ax.legend()
        ax.grid(alpha=.25)
        save(fig, f"figure_{n}_{name}.png")

    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    ax.plot(t, real, "k", label="Nonlinear reference plant", linewidth=2)
    for name, y in predictions.items():
        ax.plot(t, y, label=name)
    ax.set(title="Figure 5 — Full valve-to-cold-outlet model comparison",
           xlabel="Time (s)", ylabel="Cold outlet temperature (°C)")
    ax.grid(alpha=.25)
    ax.legend()
    save(fig, "figure_5_model_comparison.png")

    fig, ax = plt.subplots(figsize=(11, 5), constrained_layout=True)
    for name, y in predictions.items():
        ax.plot(t, real - y, label=name)
    ax.axhline(0, color="black", linewidth=.8)
    ax.set(title="Figure 6 — Prediction residuals (reference − model)",
           xlabel="Time (s)", ylabel="Cold outlet residual (°C)")
    ax.grid(alpha=.25)
    ax.legend()
    save(fig, "figure_6_residuals.png")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                                  constrained_layout=True)
    ax1.plot(operating_points.u0, operating_points.gain_empirical, "o-",
             label="Measured finite-step gain")
    ax1.plot(operating_points.u0, operating_points.gain_local, "s--",
             label="Analytical local derivative")
    ax1.set_ylabel("Process gain (°C / valve fraction)")
    ax1.grid(alpha=.25)
    ax1.legend()
    ax2.plot(operating_points.u0, operating_points.fopdt_tau_s, "o-",
             label="FOPDT lag τ")
    ax2.plot(operating_points.u0, operating_points.fopdt_theta_s, "s--",
             label="Effective delay θ")
    ax2.set(xlabel="Initial valve fraction u₀", ylabel="Time (s)")
    ax2.grid(alpha=.25)
    ax2.legend()
    fig.suptitle("Figure 7 — Operating-point dependence (+0.05 valve step)")
    save(fig, "figure_7_operating_point_dependence.png")
    return files
