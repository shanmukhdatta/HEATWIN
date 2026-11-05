"""Run all Phase 3 physical identification experiments and export reusable results.

Usage: python scripts/phase3_identification.py --output-dir outputs/phase3
Training=.40→.50; validation=.40→.45; final test=.40→.35.
No validation or test samples are ever passed to the optimizers.
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from heatwin.config import load_config
from heatwin.identification.first_order import time_constant_632
from heatwin.identification.fit_models import fit_step_response
from heatwin.identification.linearization import (
    finite_difference_jacobians,
    linearize_at_valve,
)
from heatwin.identification.step_test import create_step_experiment, measure_process_gain
from heatwin.identification.validation import error_metrics
from heatwin.visualization.identification_charts import make_figures

matplotlib.use("Agg")


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    params = load_config()
    ts = 60.0
    train = create_step_experiment(params, u0=.4, delta_u=.1, split="training")
    val = create_step_experiment(params, u0=.4, delta_u=.05, split="validation")
    test = create_step_experiment(params, u0=.4, delta_u=-.05, split="final_test")
    datasets = {"training": train, "validation": val, "final_test": test}
    for label, ex in datasets.items():
        ex.export(output_dir, label)
    fitted = {kind: fit_step_response(train.data, model=kind, step_time_s=ts)
              for kind in ("fo", "fopdt", "second_order")}
    local = linearize_at_valve(params, .4)
    numeric_a, numeric_b = finite_difference_jacobians(params, .4)
    predictions: dict[str, np.ndarray] = {}
    model_rows: list[dict] = []
    validation_errors = {}
    for name in ["fo", "fopdt", "second_order", "local_linear"]:
        fit = fitted.get(name)
        row = {"model": name, "process_gain_deg_c_per_fraction": (
            local.process_gain if fit is None else fit.process_gain
        ), "tau1_s": None if fit is None else fit.tau1_s,
               "tau2_s": None if fit is None else fit.tau2_s,
               "theta_s": 0.0 if fit is None else fit.theta_s}
        for label, experiment in datasets.items():
            t = experiment.data.time_s.to_numpy()
            delta = experiment.metadata["step_amplitude"]
            baseline = experiment.equilibrium.tc
            predicted = (local.predict_step(t, delta_u=delta, step_time_s=ts,
                                            baseline_c=baseline)
                         if fit is None else fit.predict(t, delta_u=delta,
                                                          step_time_s=ts, baseline_c=baseline))
            if label == "training":
                predictions[name] = predicted
            mask = t >= ts
            metrics = error_metrics(experiment.data.tc_c.to_numpy()[mask], predicted[mask])
            row[f"{label}_rmse_c"] = metrics.rmse
            row[f"{label}_mae_c"] = metrics.mae
            row[f"{label}_max_abs_error_c"] = metrics.max_abs_error
            row[f"{label}_fit_percent"] = metrics.fit_percent
            if label == "validation":
                validation_errors[name] = metrics.rmse
        row["gain_error_vs_analytic_percent"] = (
            100 * (row["process_gain_deg_c_per_fraction"] - local.process_gain)
            / local.process_gain
        )
        model_rows.append(row)
    pd.DataFrame(model_rows).to_csv(output_dir / "model_comparison.csv", index=False)

    amplitude_rows = []
    for delta in [.05, .1, -.05, -.1]:
        experiment = create_step_experiment(params, u0=.4, delta_u=delta,
                                            split="amplitude_sensitivity")
        fopdt = fit_step_response(experiment.data, model="fopdt", step_time_s=ts)
        amplitude_rows.append({"u0": .4, "delta_u": delta,
                               "initial_tc_c": experiment.equilibrium.tc,
                               "final_tc_c": experiment.final_equilibrium.tc,
                               "gain_empirical": measure_process_gain(experiment.data, ts),
                               "gain_analytical_finite_step": (
                                   experiment.final_equilibrium.tc - experiment.equilibrium.tc
                               ) / delta,
                               "fopdt_tau_s": fopdt.tau1_s,
                               "fopdt_theta_s": fopdt.theta_s})
        experiment.export(output_dir, f"amplitude_{'positive' if delta>0 else 'negative'}_{round(abs(delta)*100):02d}")
    pd.DataFrame(amplitude_rows).to_csv(output_dir / "amplitude_sensitivity.csv", index=False)

    op_rows = []
    for u0 in [.3, .4, .5, .6]:
        ex = create_step_experiment(params, u0=u0, delta_u=.05,
                                    split="operating_point_sensitivity")
        local_op = linearize_at_valve(params, u0)
        fit_op = fit_step_response(ex.data, model="fopdt", step_time_s=ts)
        op_rows.append({"u0": u0, "delta_u": .05,
                        "tc0_c": ex.equilibrium.tc, "tc_final_c": ex.final_equilibrium.tc,
                        "gain_empirical": measure_process_gain(ex.data, ts),
                        "gain_local": local_op.process_gain,
                        "fopdt_tau_s": fit_op.tau1_s,
                        "fopdt_theta_s": fit_op.theta_s})
        ex.export(output_dir, f"operating_point_{round(u0*100):02d}")
    ops = pd.DataFrame(op_rows)
    ops.to_csv(output_dir / "operating_point_sensitivity.csv", index=False)

    figures = make_figures(train.data, predictions, ops, output_dir)
    # Comparable validation performance, shorter interpretable tuning form:
    # FOPDT is selected for initial PI tuning, not because it wins training RMSE.
    best = min(validation_errors[n] for n in ["fo", "fopdt", "second_order"])
    if validation_errors["fopdt"] > 1.2 * best:
        raise RuntimeError("FOPDT fails transparent <=20% validation-accuracy tolerance")
    selected = fitted["fopdt"]
    handover = {
        "selected_model": "FOPDT", "model_form": "K*exp(-theta_s*s)/(tau_s*s+1)",
        "operating_point": asdict(train.equilibrium),
        "process_gain": selected.process_gain,
        "time_constant_s": selected.tau1_s,
        "effective_dead_time_s": selected.theta_s,
        "transfer_function": selected.coefficients(),
        "sampling_interval_s": params.sample_time,
        "training_step": {"initial_u": .4, "final_u": .5, "step_time_s": ts},
        "validation_step": {"initial_u": .4, "final_u": .45, "step_time_s": ts},
        "test_step": {"initial_u": .4, "final_u": .35, "step_time_s": ts},
        "local_validity_guidance": {
            "baseline_valve_fraction": .4,
            "tested_command_interval_fraction": [.3, .5],
            "caution": "Empirical LTI approximation; significant performance loss on negative/out-of-point steps. Re-identify or robustly tune outside tested conditions.",
        },
        "training_rmse_c": next(r["training_rmse_c"] for r in model_rows if r["model"] == "fopdt"),
        "validation_rmse_c": validation_errors["fopdt"],
        "final_test_rmse_c": next(r["final_test_rmse_c"] for r in model_rows if r["model"] == "fopdt"),
        "units": {"process_gain": "deg C / valve fraction", "time_constant": "s",
                  "effective_dead_time": "s", "temperatures": "deg C"},
    }
    (output_dir / "selected_model.json").write_text(
        json.dumps(handover, indent=2, allow_nan=False), encoding="utf-8"
    )
    report = {
        "training": train.metadata,
        "validation": val.metadata,
        "final_test": test.metadata,
        "measured_process_gain": measure_process_gain(train.data, ts),
        "fo_time_constant_632_s": time_constant_632(
            train.data.time_s, train.data.tc_c, step_time_s=ts,
            final_c=train.final_equilibrium.tc
        ),
        "fits": {name: asdict(result) for name, result in fitted.items()},
        "local_linear": {"A": local.A.tolist(), "B": local.B.tolist(),
                         "C": local.C.tolist(), "D": local.D.tolist(),
                         "numerator": local.numerator.tolist(),
                         "denominator": local.denominator.tolist(),
                         "poles": [[float(z.real), float(z.imag)] for z in local.poles],
                         "gain": local.process_gain,
                         "max_jacobian_difference_A": float(np.max(np.abs(local.A - numeric_a))),
                         "max_jacobian_difference_B": float(np.max(np.abs(local.B - numeric_b)))},
        "comparisons": model_rows,
        "amplitude_sensitivity": amplitude_rows,
        "operating_point_sensitivity": op_rows,
        "selected_model": handover,
        "figures": [Path(p).name for p in figures],
    }
    (output_dir / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(pd.DataFrame(model_rows)[["model", "process_gain_deg_c_per_fraction", "tau1_s", "tau2_s", "theta_s", "training_rmse_c", "validation_rmse_c", "final_test_rmse_c"]].to_string(index=False))
    print(f"Exported {len(figures)} figures, datasets, metadata and selected model to {output_dir}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/phase3"))
    args = parser.parse_args()
    run(args.output_dir)


if __name__ == "__main__":
    main()
