"""Reproduce Phase 2 physics experiments A–E and export real CSV/PNG data.

Usage: python scripts/phase2_experiments.py --output-dir outputs/phase2
"""

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np

from heatwin.config import load_config
from heatwin.models.plant import (
    PlantInputs,
    rhs,
    steady_state_for_target,
    steady_state_for_valve,
)
from heatwin.simulation.open_loop import InputStep, simulate_open_loop
from heatwin.visualization.charts import make_open_loop_figure


def main() -> None:
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/phase2"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    params = load_config()
    nominal = steady_state_for_target(params.setpoint, params)
    initial_50 = steady_state_for_valve(0.50, params)

    experiments = {
        "A_nominal_hold": simulate_open_loop(
            params, initial_command=nominal.u, initial_state=nominal.state,
        ),
        "B_hot_flow_increase": simulate_open_loop(
            params, initial_command=0.40, steps=[InputStep(60.0, u=0.50)],
        ),
        "C_hot_flow_decrease": simulate_open_loop(
            params, initial_command=0.50, initial_state=initial_50.state,
            steps=[InputStep(60.0, u=0.30)],
        ),
        "D_cold_inlet_disturbance": simulate_open_loop(
            params, initial_command=0.40, steps=[InputStep(100.0, tc_in=27.0)],
        ),
    }

    report: dict[str, object] = {
        "nominal_target_equilibrium": {
            "tc_c": nominal.tc, "th_c": nominal.th, "u": nominal.u,
            "mh_kg_s": nominal.mh, "q_w": nominal.q,
            "max_abs_derivative": float(np.max(np.abs(rhs(
                0, nominal.state, PlantInputs.from_params(params, nominal.u), params
            )))),
        },
        "experiments": {},
    }

    for name, data in experiments.items():
        data.to_csv(args.output_dir / f"{name}.csv", index=False, float_format="%.15g")
        fig = make_open_loop_figure(data, title=name.replace("_", " "))
        fig.savefig(args.output_dir / f"{name}.png", dpi=140)
        plt.close(fig)
        report["experiments"][name] = {
            "initial_tc_c": float(data["tc_c"].iloc[0]),
            "final_tc_c": float(data["tc_c"].iloc[-1]),
            "initial_th_c": float(data["th_c"].iloc[0]),
            "final_th_c": float(data["th_c"].iloc[-1]),
            "final_xv": float(data["xv"].iloc[-1]),
            "final_mh_kg_s": float(data["mh_kg_s"].iloc[-1]),
            "final_q_w": float(data["q_w"].iloc[-1]),
        }

    # Experiment E: same physical scenario, different tolerances and output intervals.
    coarse = simulate_open_loop(params, steps=[InputStep(60.0, u=0.50)],
                                rtol=1e-7, atol=1e-9, sample_time_s=1.0)
    fine = simulate_open_loop(params, steps=[InputStep(60.0, u=0.50)],
                              rtol=1e-11, atol=1e-13, sample_time_s=0.25)
    # Both trajectories contain the exact integer-second grid points.
    fine_on_coarse = fine.loc[np.isin(fine["time_s"], coarse["time_s"])]
    if len(fine_on_coarse) != len(coarse):
        raise AssertionError("Convergence experiment does not share the same time grid.")
    differences = {
        name: float(np.max(np.abs(
            coarse[name].to_numpy() - fine_on_coarse[name].to_numpy()
        )))
        for name in ("tc_c", "th_c", "xv", "mh_kg_s", "q_w")
    }
    report["convergence_E_max_abs_difference"] = differences
    report["convergence_E_method"] = "RK45; rtol 1e-7 vs 1e-11; output 1 vs 0.25 s"
    (args.output_dir / "summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    print(f"Saved reproducible plots, CSV files and summary to {args.output_dir}")


if __name__ == "__main__":
    main()
