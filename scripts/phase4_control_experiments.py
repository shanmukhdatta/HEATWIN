"""Reproduce HEATWIN Phase 4 P/PI/PID tests, figures, CSVs and recommendations.

Run: python scripts/phase4_control_experiments.py --output-dir outputs/phase4
Uses *existing* Phase 3 FOPDT parameters for tuning and the *existing*
Phase 2 nonlinear energy-balance model for every plant simulation.
"""

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

import matplotlib
import pandas as pd

from heatwin.config import load_config
from heatwin.control.tuning import (
    imc_pi,
    load_identified_model,
    manual_p,
    manual_pi,
    ziegler_nichols,
)
from heatwin.diagnostics.control_metrics import evaluate_control
from heatwin.models.plant import steady_state_for_target, steady_state_for_valve
from heatwin.simulation.closed_loop import simulate_closed_loop
from heatwin.simulation.control_scenarios import standard_scenarios
from heatwin.simulation.open_loop import simulate_open_loop
from heatwin.visualization.control_charts import (
    actuator_figure,
    comparison_figure,
    metrics_figure,
    windup_figure,
)


def run(output_dir: Path) -> dict:
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    params = load_config(root / "configs" / "default.yaml")
    model = load_identified_model(root / "configs" / "identified" / "phase3_fopdt_nominal.json")
    cases = standard_scenarios(params.setpoint)
    gains = {
        "P-manual": manual_p(model),
        "PI-manual": manual_pi(model),
        "PI-IMC": imc_pi(model, lambda_s=model.tau_s),
        "PI-ZN": ziegler_nichols(model, mode="PI"),
        "PID-ZN": ziegler_nichols(model, mode="PID"),
        "PI-IMC-conservative": imc_pi(model, lambda_s=2 * model.tau_s),
        "PI-IMC-aggressive": imc_pi(model, lambda_s=0.5 * model.tau_s),
    }
    results: dict[str, pd.DataFrame] = {}
    records = []
    for scenario_key in ("nominal_hold", "positive_setpoint", "negative_setpoint",
                         "multiple_setpoints", "cold_inlet", "hot_inlet", "cold_flow"):
        scenario = cases[scenario_key]
        for name, s in gains.items():
            # Reduced sweep: all seven controllers on tracking, and the three
            # basic modes for each other scenario. Avoid unnecessary runs.
            if (scenario_key != "positive_setpoint"
                    and name not in ("P-manual", "PI-IMC", "PID-ZN")):
                continue
            frame = simulate_closed_loop(
                params, s, duration_s=scenario.duration_s,
                setpoint_steps=scenario.setpoint_steps,
                disturbance_steps=scenario.disturbance_steps,
            )
            key = f"{scenario_key}__{name}"
            results[key] = frame
            frame.to_csv(output_dir / f"{key}.csv", index=False, float_format="%.15g")
            event = 60 if scenario.setpoint_steps else (100 if scenario.disturbance_steps else 0)
            initial_ref = params.setpoint if scenario_key in ("positive_setpoint",
                        "negative_setpoint") else None
            score = evaluate_control(frame, window_start_s=event,
                                     reference_initial_c=initial_ref)
            records.append({"experiment": scenario_key, "controller": name,
                            "kc": s.kc, "ti_s": s.ti_s, "td_s": s.td_s,
                            "final_tc_c": float(frame.tc_c.iloc[-1]),
                            **score.as_dict()})
    # Actual open-loop disturbance for matched initial conditions and timing.
    cold = cases["cold_inlet"]
    eq = steady_state_for_target(params.setpoint, params)
    open_loop = simulate_open_loop(params, duration_s=cold.duration_s,
                                   initial_command=eq.u, initial_state=eq.state,
                                   steps=cold.disturbance_steps)
    open_loop["setpoint_c"] = params.setpoint
    open_loop.to_csv(output_dir / "cold_inlet__open_loop.csv", index=False)

    # Windup example: impossible 80°C request, then return to 55°C.
    windup = cases["windup"]
    for label, s in (("PI-with-antiwindup", gains["PI-IMC"]),
                     ("PI-no-antiwindup", replace(gains["PI-IMC"], anti_windup="none"))):
        data = simulate_closed_loop(params, s, duration_s=windup.duration_s,
                                    setpoint_steps=windup.setpoint_steps)
        results[f"windup__{label}"] = data
        data.to_csv(output_dir / f"windup__{label}.csv", index=False)

    # Test fixed tuning on perturbed actual plants; no per-plant retuning.
    robustness = []
    variations = (("UA-20%", "ua", .8), ("UA+20%", "ua", 1.2),
                  ("hot-inlet-10%", "th_in", .9), ("hot-inlet+10%", "th_in", 1.1),
                  ("valve-tau-x2", "valve_tau", 2.0),
                  ("cold-flow+15%", "mc", 1.15))
    for label, field, multiplier in variations:
        altered = replace(params, **{field: getattr(params, field) * multiplier})
        d = simulate_closed_loop(altered, gains["PI-IMC"], duration_s=420,
                                 setpoint_steps=cases["positive_setpoint"].setpoint_steps)
        results[f"robust__{label}"] = d
        d.to_csv(output_dir / f"robust__{label}.csv", index=False)
        score = evaluate_control(d, window_start_s=60, reference_initial_c=params.setpoint)
        reachable = steady_state_for_valve(1.0, altered).tc >= params.setpoint + 2
        robustness.append({"variation": label, "field": field, "factor": multiplier,
                           "target_feasible": bool(reachable), "max_equilibrium_tc_c":
                           steady_state_for_valve(1.0, altered).tc,
                           "final_tc_c": float(d.tc_c.iloc[-1]), **score.as_dict()})

    summary = pd.DataFrame(records)
    summary.to_csv(output_dir / "controller_comparison.csv", index=False)
    robustness_df = pd.DataFrame(robustness)
    robustness_df.to_csv(output_dir / "robustness.csv", index=False)

    def save(figure, name):
        figure.savefig(output_dir / name, dpi=135)
        plt.close(figure)

    def subset(scenario, keys):
        return {name: results[f"{scenario}__{name}"] for name in keys}

    basic = ("P-manual", "PI-IMC", "PID-ZN")
    positive = subset("positive_setpoint", basic)
    save(comparison_figure(positive, title="55°C to 57°C: P / PI / PID tracking"),
         "figure_1_tracking.png")
    save(actuator_figure(positive), "figure_2_actuator.png")
    save(comparison_figure(subset("positive_setpoint", ("PI-ZN", "PI-IMC", "PI-IMC-conservative")),
                           title="Ziegler–Nichols vs IMC tuning"), "figure_3_tuning.png")
    cold_runs = {"Open loop": open_loop, "PI-IMC": results["cold_inlet__PI-IMC"],
                 "PID-ZN": results["cold_inlet__PID-ZN"]}
    save(comparison_figure(cold_runs, title="30°C to 27°C cold-inlet disturbance"),
         "figure_4_disturbance.png")
    save(comparison_figure(positive, title="Setpoint tracking error",
                           signal="error_c", ylabel="Error (°C)", include_setpoint=False),
         "figure_5_error.png")
    save(windup_figure({"With anti-windup": results["windup__PI-with-antiwindup"],
                        "Without anti-windup": results["windup__PI-no-antiwindup"]}),
         "figure_6_antiwindup.png")
    robustness_runs = {"Nominal": results["positive_setpoint__PI-IMC"],
                       "UA -20%": results["robust__UA-20%"],
                       "UA +20%": results["robust__UA+20%"]}
    save(comparison_figure(robustness_runs, title="Fixed IMC-PI with UA uncertainty"),
         "figure_7_robustness.png")
    save(metrics_figure(summary[summary.experiment == "positive_setpoint"]),
         "figure_8_metrics.png")
    tuning_data = {name: asdict(s) | {"ki": s.ki, "kd": s.kd} for name, s in gains.items()}
    safe = {"selected_controller": "PI-IMC", "selection": "Moderate IMC PI: small nominal overshoot, no sustained offset, interpretable model-based tuning",
            "source_identification": "configs/identified/phase3_fopdt_nominal.json",
            "phase3_process": asdict(model), "controllers": tuning_data,
            "metric_units": {"iae_c_s": "deg C*s", "ise_c2_s": "deg C^2*s",
                             "itae_c_s2": "deg C*s^2", "max_command": "fraction"},
            "comparison": records, "robustness": robustness,
            "note": "Phase 4 simulation evidence, not a guarantee of robust stability. Infeasible perturbed targets are identified explicitly."}
    (output_dir / "summary.json").write_text(json.dumps(safe, indent=2, allow_nan=False), encoding="utf-8")
    (output_dir / "selected_controller.json").write_text(
        json.dumps({"selected_controller": safe["selected_controller"],
                    "source_identification": safe["source_identification"],
                    "controller_settings": asdict(gains["PI-IMC"]),
                    "operating_point": asdict(eq), "validation_experiment":
                    "positive_setpoint__PI-IMC",
                    "metrics": next(x for x in records if x["experiment"] == "positive_setpoint" and x["controller"] == "PI-IMC")},
                   indent=2, allow_nan=False), encoding="utf-8")
    print(summary[summary.experiment == "positive_setpoint"][["controller", "kc", "ti_s", "td_s", "iae_c_s", "overshoot_c", "settling_time_s", "final_tc_c"]].to_string(index=False))
    print("Robustness:", robustness_df[["variation", "target_feasible", "final_tc_c"]].to_string(index=False))
    print(f"Wrote {len(records)} controller/scenario runs, {len(robustness)} robustness runs, "
          f"and eight scientific figures to {output_dir}")
    return safe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/phase4"))
    args = parser.parse_args()
    run(args.output_dir)


if __name__ == "__main__":
    main()
