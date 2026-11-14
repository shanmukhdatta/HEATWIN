"""Generate reproducible simulated results: python -m scripts.experiments."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from heatwin.config import load_parameters
from heatwin.core import fit_fopdt, fopdt, metrics, simulate
from heatwin.diagnostics import predict_twin, residual_alarm

OUT = Path("results")


def main():
    OUT.mkdir(exist_ok=True)
    plant = load_parameters("configs/default.json")
    train = simulate(p=plant, open_loop=True, duration=600)
    step = train[train.time >= 60]
    t = step.time.to_numpy() - 60
    params = fit_fopdt(t, (step.tc.to_numpy() - step.tc.iloc[0]) / 0.1)
    train["fitted_tc"] = train.tc.iloc[0] + 0.1 * fopdt(
        np.maximum(train.time.to_numpy() - 60, 0), *params
    )
    train.to_csv(OUT / "identification.csv", index=False)
    fig, ax = plt.subplots()
    ax.plot(train.time, train.tc, label="plant")
    ax.plot(train.time, train.fitted_tc, "--", label="FOPDT training fit")
    ax.set(
        xlabel="Time (s)", ylabel="Cold outlet (°C)", title="Open-loop identification"
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "identification.png", dpi=150)
    plt.close(fig)
    settings = {"P": (0.04, 0, 0), "PI": (0.04, 0.001, 0), "PID": (0.04, 0.001, 0.08)}
    summary = {}
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(8, 7))
    for name, gains in settings.items():
        data = simulate(p=plant, gains=gains)
        data.to_csv(OUT / f"{name.lower()}.csv", index=False)
        window = data[data.time >= 60]
        summary[name] = metrics(
            window.time.to_numpy(),
            window.tc.to_numpy(),
            window.setpoint.to_numpy(),
            window.command.to_numpy(),
        )
        axes[0].plot(data.time, data.tc, label=name)
        axes[1].plot(data.time, data.command, label=name)
    axes[0].plot(data.time, data.setpoint, "k--", label="setpoint")
    axes[0].set(ylabel="Cold outlet (°C)", title="Setpoint tracking")
    axes[1].set(xlabel="Time (s)", ylabel="Valve command (fraction)")
    axes[0].legend()
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(OUT / "controllers.png", dpi=150)
    plt.close(fig)
    validation = simulate(p=plant, disturbance=-3, noise=0.05, bias=2, fault_time=300)
    prediction = predict_twin(
        validation.time, validation.command, validation.tc.iloc[0], *params
    )
    validation["twin"] = prediction
    validation["residual"] = validation.measurement - prediction
    validation["alarm"] = residual_alarm(validation.residual, 1.0, 3)
    validation.to_csv(OUT / "twin_fault.csv", index=False)
    pre = validation[validation.time < 300]
    post = validation[validation.time >= 300]
    alarms = post[post.alarm]
    summary["identification"] = dict(
        zip(
            ["gain_C_per_fraction", "tau_s", "delay_s"], map(float, params), strict=True
        )
    )
    summary["identification"]["training_rmse_C"] = float(
        np.sqrt(np.mean((train.tc - train.fitted_tc) ** 2))
    )
    summary["held_out_twin"] = {
        "pre_fault_rmse_C": float(np.sqrt(np.mean((pre.tc - pre.twin) ** 2))),
        "post_fault_rmse_C": float(np.sqrt(np.mean((post.tc - post.twin) ** 2))),
        "pre_fault_alarm_fraction": float(pre.alarm.mean()),
        "first_alarm_delay_s": float(alarms.time.iloc[0] - 300)
        if len(alarms)
        else None,
    }
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(8, 7))
    axes[0].plot(validation.time, validation.tc, label="plant")
    axes[0].plot(validation.time, validation.measurement, label="sensor", alpha=0.7)
    axes[0].plot(validation.time, validation.twin, label="open-loop twin")
    axes[0].set(ylabel="Temperature (°C)", title="Held-out disturbance and sensor bias")
    axes[0].legend()
    axes[1].plot(validation.time, validation.residual, label="sensor − twin")
    axes[1].axhline(1, color="r", linestyle="--")
    axes[1].axhline(-1, color="r", linestyle="--", label="alarm threshold")
    axes[1].set(xlabel="Time (s)", ylabel="Residual (°C)")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(OUT / "twin_fault.png", dpi=150)
    plt.close(fig)
    clean = {
        name: {
            key: (
                None if isinstance(value, float) and not np.isfinite(value) else value
            )
            for key, value in values.items()
        }
        for name, values in summary.items()
    }
    (OUT / "summary.json").write_text(
        json.dumps(clean, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
