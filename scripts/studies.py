"""Independent validation, tuning and fault studies; all data are simulated."""

import json
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from heatwin.core import (
    PID,
    Parameters,
    equilibrium,
    fit_fopdt,
    fopdt,
    metrics,
    simulate,
)
from heatwin.diagnostics import detection_metrics, predict_twin, residual_alarm
from heatwin.identification import first_order, fit_first_order
from heatwin.stability import local_stability
from heatwin.tuning import optimize_gains, tune

OUT = Path("results/studies")


def performance(data, start=60):
    data = data[data.time >= start]
    return metrics(
        data.time.to_numpy(),
        data.tc.to_numpy(),
        data.setpoint.to_numpy(),
        data.command.to_numpy(),
    )


def model_objective(gains, model):
    """Tune on a discrete FOPDT approximation, never on validation plant runs."""
    gain, tau, delay = model
    controller = PID(*gains, bias=0.4)
    y = 0.0
    commands = [0.4] * (int(np.ceil(delay)) + 2)
    error = []
    for _ in range(400):
        u = controller.update(2.0, y)
        commands.append(u)
        delayed = commands[-int(np.ceil(delay)) - 1]
        y += (gain * (delayed - 0.4) - y) * (1 - np.exp(-1 / tau))
        error.append(abs(2 - y))
    return sum(error) + 5 * sum(abs(np.diff(commands)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    train = simulate(duration=450, open_loop=True)
    sample = train[train.time >= 60]
    t = sample.time.to_numpy() - 60
    response = (sample.tc.to_numpy() - sample.tc.iloc[0]) / 0.1
    fo = fit_first_order(t, response)
    model = fit_fopdt(t, response)
    valid = simulate(duration=450, open_loop=True, open_loop_value=0.3)
    elapsed = np.maximum(valid.time.to_numpy() - 60, 0)
    valid["first_order"] = valid.tc.iloc[0] - 0.1 * first_order(elapsed, *fo)
    valid["fopdt"] = valid.tc.iloc[0] - 0.1 * fopdt(elapsed, *model)
    valid["fo_residual"] = valid.tc - valid.first_order
    valid["fopdt_residual"] = valid.tc - valid.fopdt
    valid.to_csv(OUT / "identification_validation.csv", index=False)
    fig, ax = plt.subplots(2, 1, figsize=(8, 7), sharex=True)
    for col in ["tc", "first_order", "fopdt"]:
        ax[0].plot(valid.time, valid[col], label=col)
    for col in ["fo_residual", "fopdt_residual"]:
        ax[1].plot(valid.time, valid[col], label=col)
    ax[0].set(ylabel="Cold outlet (°C)", title="Held-out downward valve step")
    ax[1].set(xlabel="Time (s)", ylabel="Plant − model (°C)")
    for a in ax:
        a.legend()
    fig.tight_layout()
    fig.savefig(OUT / "identification_validation.png", dpi=150)
    plt.close(fig)
    summary = {
        "identification": {
            "first_order": fo.tolist(),
            "fopdt": model.tolist(),
            "validation_fo_rmse_C": float(np.sqrt(np.mean(valid.fo_residual**2))),
            "validation_fopdt_rmse_C": float(np.sqrt(np.mean(valid.fopdt_residual**2))),
        }
    }
    opt = optimize_gains(lambda g: model_objective(g, model))
    choices = {
        "manual": (0.04, 0.001, 0.08),
        "imc": tune("imc", *model),
        "zn": tune("zn", *model),
        "cohen_coon": tune("cohen-coon", *model),
        "optimized_fopdt": tuple(opt.x),
    }
    summary["optimization"] = {
        "success": bool(opt.success),
        "message": str(opt.message),
        "objective": float(opt.fun),
        "gains": opt.x.tolist(),
    }
    summary["tuning"] = {}
    summary["local_stability"] = {
        name: local_stability(gains) for name, gains in choices.items()
    }
    fig, ax = plt.subplots(figsize=(9, 5))
    for name, gains in choices.items():
        d = simulate(duration=600, gains=gains)
        d.to_csv(OUT / f"tuning_{name}.csv", index=False)
        result = performance(d)
        result.update(
            {
                "gains": list(gains),
                "saturation_fraction": float(
                    ((d.command <= 0) | (d.command >= 1)).mean()
                ),
                "max_abs_error_C": float(abs(d.setpoint - d.tc).max()),
            }
        )
        summary["tuning"][name] = result
        ax.plot(d.time, d.tc, label=name)
    ax.plot(d.time, d.setpoint, "k--", label="setpoint")
    ax.set(
        xlabel="Time (s)",
        ylabel="Cold outlet (°C)",
        title="Tuning methods on nonlinear plant",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "tuning.png", dpi=150)
    plt.close(fig)
    cases = {
        "normal": {},
        "sensor_bias": {"bias": 2.0},
        "sensor_drift": {"sensor_drift": 0.01},
        "noise": {"noise": 0.4},
        "flow": {"flow_factor": 1.3},
        "cold_inlet": {"disturbance": -3.0},
        "degradation": {"degradation": 0.7},
        "stuck_valve": {"stuck": True},
        "parameter_mismatch": {"p": Parameters(ua=280.0)},
        "saturation": {"setpoint": 70.0},
    }
    summary["faults"] = {}
    fig, ax = plt.subplots(figsize=(9, 5))
    for name, options in cases.items():
        options = {"noise": 0.05, **options}
        d = simulate(duration=600, fault_time=300, **options)
        d["twin"] = predict_twin(d.time, d.command, d.tc.iloc[0], *model)
        d["residual"] = d.measurement - d.twin
        d["alarm"] = residual_alarm(d.residual, 1.0, 3)
        d.to_csv(OUT / f"case_{name}.csv", index=False)
        pre = d[d.time < 300]
        post = d[d.time >= 300]
        injected = name in {
            "sensor_bias",
            "sensor_drift",
            "flow",
            "cold_inlet",
            "degradation",
            "stuck_valve",
        }
        result = detection_metrics(d.time, d.alarm, 300)
        result["injection_at_300"] = injected
        if not injected:
            result["detection_delay_s"] = None
        result.update(
            {
                "pre_rmse_C": float(np.sqrt(np.mean((pre.tc - pre.twin) ** 2))),
                "post_rmse_C": float(np.sqrt(np.mean((post.tc - post.twin) ** 2))),
                "post_alarm_fraction": float(post.alarm.mean()),
                "high_temperature_fraction": float((d.tc > 65).mean()),
            }
        )
        summary["faults"][name] = result
        if name in ("normal", "sensor_bias", "flow", "degradation", "stuck_valve"):
            ax.plot(d.time, d.residual, label=name)
    ax.axhline(1, color="black", ls="--")
    ax.axhline(-1, color="black", ls="--")
    ax.axvline(300, color="grey", ls=":")
    ax.set(
        xlabel="Time (s)",
        ylabel="Sensor − twin (°C)",
        title="Separate simulated fault scenarios",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "fault_residuals.png", dpi=150)
    plt.close(fig)
    # Regulatory comparison starts at one common equilibrium and changes only inlet temperature.
    base = equilibrium(0.4, Parameters())[0]
    regulatory = {}
    fig, ax = plt.subplots(figsize=(9, 5))
    for label, gains in {
        "P": (0.04, 0.0, 0.0),
        "PI": (0.04, 0.001, 0.0),
        "PID": (0.04, 0.001, 0.08),
    }.items():
        d = simulate(
            setpoint=base, step_time=0, gains=gains, disturbance=-3, fault_time=300
        )
        d.to_csv(OUT / f"regulatory_{label.lower()}.csv", index=False)
        regulatory[label] = performance(d, 300)
        ax.plot(d.time, d.tc, label=label)
    ax.axhline(base, color="black", ls="--", label="setpoint")
    ax.axvline(300, color="grey", ls=":")
    ax.set(
        xlabel="Time (s)",
        ylabel="Cold outlet (°C)",
        title="Cold inlet disturbance rejection",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "regulatory.png", dpi=150)
    plt.close(fig)
    summary["regulatory"] = regulatory
    # Estimate false-alarm behavior across independent seeded normal-noise runs.
    false_alarms = []
    for seed in range(10):
        normal = simulate(duration=600, noise=0.2, seed=seed)
        twin = predict_twin(normal.time, normal.command, normal.tc.iloc[0], *model)
        false_alarms.append(
            float(residual_alarm(normal.measurement - twin, 1.0, 3).mean())
        )
    summary["normal_noise_false_alarm"] = {
        "seeds": list(range(10)),
        "noise_std_C": 0.2,
        "alarm_sample_fractions": false_alarms,
        "runs_with_alarm": sum(x > 0 for x in false_alarms),
    }
    summary["configuration"] = {
        "plant": asdict(Parameters()),
        "sample_time_s": 1.0,
        "seed": 42,
        "fault_time_s": 300.0,
        "alarm_threshold_C": 1.0,
        "alarm_persistence_samples": 3,
        "training_valve_step": [0.4, 0.5],
        "validation_valve_step": [0.4, 0.3],
    }
    # Compare a finer open-loop integration grid.

    fine = simulate(duration=180, dt=0.5, open_loop=True)
    coarse = simulate(duration=180, dt=1, open_loop=True)
    summary["solver_grid_max_difference_C"] = float(
        np.max(abs(fine.tc.to_numpy()[::2] - coarse.tc.to_numpy()))
    )

    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(v) for v in x]
        if isinstance(x, (float, np.floating)):
            return float(x) if np.isfinite(x) else None
        return x

    (OUT / "summary.json").write_text(
        json.dumps(clean(summary), indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(clean(summary), indent=2))


if __name__ == "__main__":
    main()
