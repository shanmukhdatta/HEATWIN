# HEATWIN — Step-by-Step Implementation Plan

> **Companion to [README.md](README.md)**  
> **Project:** Heat Exchanger Digital Twin with PID Control  
> **Approach:** Software-only, physics-first, test-driven, reproducible experiments  
> **Status:** Milestones 0–3 (foundation, physics/open-loop, identification, sampled P/PI/PID) implemented on stacked feature branches with scientific tests and reproducible experiments. GitHub CI and PR review determine acceptance; predictive twin, advanced faults and full dashboard remain pending.

## 0. Definition of done

HEATWIN is **complete** when a collaborator can clone the repository, install dependencies, pass all automated tests, launch the dashboard, reproduce the planned heat-exchanger experiments, and explain what the predictive twin does differently from the virtual plant.

Minimum deliverables:

- Working **nonlinear dynamic plant** with two fluid temperatures and valve dynamics.
- Verified **steady state and energy balance**.
- **Open-loop** step test plus FOPDT / second-order identification.
- Working discrete **PI controller** and a P/PI/PID comparison.
- **Disturbance-rejection** experiments.
- A **separately identified** predictive twin with held-out error analysis.
- **Valve and sensor fault** scenarios with monitoring.
- Streamlit dashboard, exported results and short final report.
- GitHub README, documented run commands, unit tests, and a repeatable demo.

**Scope decision:** Start with an idealized two-lump water-to-water heat exchanger. Do not attempt computational fluid dynamics, real PLC connectivity, industrial certification, AI forecasting, or hardware until the core system works.

## 1. Development rules and conventions

- Python **3.11+**; numerical calculations in NumPy/SciPy.
- State vector: `y = [Tc, Th, xv]` (cold temperature °C, hot temperature °C, actual valve fraction).
- Commands and valve fractions are **dimensionless in [0, 1]**; show percentages in the UI.
- Flow rates are **kg/s**, heat duty in **W**, time in **seconds**, `UA` in **W/K**.
- Integration may use `scipy.integrate.solve_ivp` for each control interval; PID updates are discrete every **1 s**.
- Keep **simulation time** separate from wall-clock / UI refresh time.
- Do not mix raw noise with the underlying physical state. Sensor effects belong in `sensor.py`.
- Every experiment records parameter snapshot, initial conditions, sampling time, random seed, signals and evaluation metrics.
- Use separate training and test scenarios for identification and digital twin validation.
- Fail loudly for invalid parameters (negative volumes, flow rates outside defined conditions, time steps <= 0).
- Document any intentional approximations or mismatches.

### Baseline configuration

```yaml
# configs/default.yaml — proposed
rho: 1000.0         # kg/m^3
cp: 4180.0          # J/(kg K)
vc: 0.001           # m^3
vh: 0.001           # m^3
ua: 350.0           # W/K
tc_in: 30.0         # deg C
th_in: 80.0         # deg C
mc: 0.030           # kg/s
mh_min: 0.010       # kg/s
mh_max: 0.100       # kg/s
valve_tau: 4.0      # s
sample_time: 1.0    # s
setpoint: 55.0      # deg C
seed: 42
```

The initial configuration is **illustrative**, not calibrated to experimental equipment.

## 2. Physics and equilibrium calculations

### 2.1 Equations

The reference process starts from constant-property energy balances:

```text
Cc = rho * Vc * cp
Ch = rho * Vh * cp

dTc/dt = [mc*cp*(Tc_in-Tc) + UA*(Th-Tc)] / Cc
dTh/dt = [mh*cp*(Th_in-Th) - UA*(Th-Tc)] / Ch

dxv/dt = [clip(u,0,1)-xv] / valve_tau
mh = mh_min + (mh_max-mh_min)*clip(xv,0,1)
```

Heat transferred from hot to cold fluid:

```text
Q = UA*(Th-Tc)
```

These equations assume perfectly mixed fluid hold-ups and no ambient heat loss. They are not a distributed shell-and-tube exchanger design model.

### 2.2 Steady-state verification

For the example `Tc = 55 °C`, `Tc_in = 30 °C`, `Th_in = 80 °C`:

1. Cold-side heat uptake: `Q = mc*cp*(55-30) = 3135 W`.
2. Required hot-side bulk/outlet temperature: `Th = 55 + 3135/350 = 63.9571 °C`.
3. Required hot flow: `mh = Q / [cp*(80-Th)] ≈ 0.04677 kg/s`.
4. Valve fraction: `xv = (mh-0.010)/(0.100-0.010) ≈ 0.4085` (~40.85%).

Verification tests must use **unrounded** computed values and check the ODE derivatives are nearly zero. Do not hard-code 40.85% as the controller's universal equilibrium — it is specific to these parameters.

### 2.3 Conservation check

Adding both fluid energy balance equations must cancel the internal exchange term `UA*(Th-Tc)`:

```text
Cc*dTc/dt + Ch*dTh/dt =
    mc*cp*(Tc_in-Tc) + mh*cp*(Th_in-Th)
```

This identity is an essential physics unit test.

## 3. Planned repository structure

```text
HEATWIN/
├── README.md
├── IMPLEMENTATION_PLAN.md
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── app.py
├── configs/
│   ├── default.yaml
│   └── scenarios.yaml
├── src/heatwin/
│   ├── __init__.py
│   ├── config.py
│   ├── models/
│   │   ├── plant.py
│   │   ├── actuator.py
│   │   ├── sensor.py
│   │   └── twin.py
│   ├── control/
│   │   ├── pid.py
│   │   └── tuning.py
│   ├── identification/
│   │   ├── step_test.py
│   │   └── fit_models.py
│   ├── simulation/
│   │   ├── engine.py
│   │   └── scenarios.py
│   ├── diagnostics/
│   │   ├── metrics.py
│   │   └── alarms.py
│   └── visualization/
│       └── charts.py
├── tests/
│   ├── test_plant.py
│   ├── test_pid.py
│   ├── test_identification.py
│   ├── test_twin.py
│   └── test_scenarios.py
├── notebooks/
│   ├── 01_physics_validation.ipynb
│   ├── 02_system_identification.ipynb
│   └── 03_controller_comparison.ipynb
├── data/synthetic/
├── docs/
│   ├── mathematical_model.md
│   ├── experiments.md
│   └── final_report.md
└── .github/workflows/tests.yml
```

**Note:** This directory tree is a **target**. Do not create placeholder modules merely to appear complete; implement them with tests in milestone order.

## 4. Milestones and tasks

### Milestone 0 — Project setup (Day 1)

- [x] Add `.gitignore`, `pyproject.toml`, `requirements.txt`, package `__init__.py`.
- [ ] Create a fresh Python virtual environment.
- [x] Add `pytest`, formatting/linting conventions, and minimal GitHub Actions workflow.
- [x] Add `configs/default.yaml` and validate required configuration fields.
- [x] Write a single command for running the tests.
- [x] Verify installation on a second machine or clean environment.

**Acceptance:** environment installs successfully and `pytest -q` discovers a passing smoke test.

**Phase 1 verification:** GitHub Actions passed full installation, `pip check`, 72 tests, Ruff, and Streamlit placeholder smoke checks on Python 3.11 and 3.13. A fresh contributor-created local virtual environment is still a documented setup step rather than a separately verified manual run. Physical modeling and control implementation remain pending.

### Milestone 1 — Physics-based virtual plant (Days 2–4)

**Primary files:** `models/plant.py`, `models/actuator.py`, `config.py`, `tests/test_plant.py`.

- [x] Create a typed `PlantParameters` configuration model.
- [x] Implement `rhs(t, y, inputs, params)` returning temperature and actuator derivatives.
- [x] Add `steady_state(...)` for the nominal flow and temperatures.
- [x] Integrate for one sample or an arbitrary open-loop interval using SciPy.
- [x] Support fixed valve commands, inlet temperatures and cold-side flow.
- [x] Validate parameter signs and valve bounds.
- [x] Draw a 0–300 s nominal step response.
- [x] Save timeseries to a DataFrame / CSV.

**Tests:** mass/energy consistency, steady-state derivatives near zero, correct valve limits, finite states, reproducibility.

**Acceptance:** 55 °C nominal equilibrium is reproduced; increased hot-water flow initially drives the cold outlet in the expected direction; energy balance identity passes.

**Phase 2 numerical evidence:** exact nominal hot flow `0.046749777382 kg/s`, opening `0.408330859800`, heat duty `3135 W`; the unrounded inverse/forward steady states have near-zero ODE residuals. The Phase 2 test suite includes energy cancellation, valve bounds, disturbance direction, solver-step alignment, deterministic replay and convergence. Run `python scripts/phase2_experiments.py --output-dir outputs/phase2` to regenerate actual plots and time series.

### Milestone 2 — Experimental data and empirical models (Days 5–7)

**Primary files:** `identification/step_test.py`, `identification/fit_models.py`, `tests/test_identification.py`.

- [x] Start from a settled open-loop operating point.
- [x] Apply a step in valve command, e.g. 0.40 → 0.50.
- [x] Record `time, u, xv, mh, Tc, Th, Tc_in, Th_in, mc`.
- [x] Estimate `K = delta_Tc / delta_u` after settling.
- [x] Fit FOPDT gain, lag and effective dead time via optimization.
- [x] Fit a second-order comparison model (if stable and identifiable from the data).
- [x] Include training and held-out step inputs; report fit RMSE.
- [x] Present overlaid predicted and simulated response curves.

**Caution:** FOPDT is an approximation to the higher-order plant-plus-valve dynamics. Dead time need not be an actual physical transport delay.

**Acceptance:** model parameters are finite and meaningful; validation RMSE is reported; fits never use the future test points for estimation.

### Milestone 3 — Discrete-time controller (Days 8–11)

**Primary files:** `control/pid.py`, `control/tuning.py`, `tests/test_pid.py`.

- [x] Implement P and PI with explicit sample period and a configurable bias `u_bias`.
- [x] Add PID with derivative on measurement and derivative filtering.
- [x] Add valve output saturation and anti-windup (clamping or back-calculation).
- [x] Implement bumpless initialization at an operating point.
- [x] Implement manual tuning plus justified Ziegler–Nichols and IMC-style methods.
- [x] Record error, individual controller terms, output command, actual valve position.
- [x] Compare PI and PID for a feasible 55 → 57 °C setpoint change.
- [x] Record the tuning formula, model form, and the controller parameter convention.

**Tests:** correct error sign, zero error at equilibrium with bias, saturation limits, windup recovery, stable behavior for documented safe gains.

**Acceptance:** baseline PI tracks 57 °C after the step and recovers from a cold-inlet disturbance without sustained oscillation. Do not claim PID is inherently better; compare measured results.

**Phase 4 control acceptance:** local nonlinear sampled-control experiments and scientific tests pass; PI regulates near 55°C and tracks 57°C, with observed disturbance rejection and documented infeasible hot-inlet cases. See `docs/pid_controller_design.md` and reproducible `scripts/phase4_control_experiments.py`. Phase 4 does not implement the independent predictive twin or future advanced sensor/fault scenarios.

### Milestone 4 — Simulation scenarios and metrics (Days 12–13)

**Primary files:** `simulation/engine.py`, `simulation/scenarios.py`, `diagnostics/metrics.py`.

- [ ] Write one deterministic sample-by-sample simulation engine.
- [ ] Define input scenario changes by **simulation time**.
- [ ] Ensure state updates, sensor reads, PID execution and logs happen in a documented consistent order.
- [ ] Implement open-loop, closed-loop and disturbance scenarios.
- [ ] Calculate IAE, ISE, overshoot, settling time, steady-state error, valve movement, saturation duration.
- [ ] Report comparison metrics over the same time window and operating conditions.
- [ ] Export scenario CSV with metadata and parameters.

**Acceptance:** replaying a scenario with the same seed and parameters produces the same measurements and metrics.

### Milestone 5 — Independent predictive twin (Days 14–16)

**Primary files:** `models/twin.py`, `tests/test_twin.py`.

- [ ] Implement a **distinct prediction model**, initially FOPDT/state-space or two-lump model with **estimated** parameters.
- [ ] Fit parameters using only simulated **training data**.
- [ ] Feed observed operating inputs and available measured disturbances into the twin; explicitly log which signals are assumed known.
- [ ] Evaluate on **held-out** setpoint and disturbance scenarios.
- [ ] Compare plant vs twin predicted temperature and plot residuals.
- [ ] Calculate MAE, RMSE and maximum absolute error.
- [ ] Test sensitivity to incorrectly estimated `UA`, flow, noise and initial-state mismatch.
- [ ] Report whether twin estimates are open-loop predictions or measurement-corrected estimates; avoid mixing the two descriptions.

**Acceptance:** documented calibration protocol, real held-out prediction metrics, and a clear explanation of why the twin is not merely the exact same model copied twice.

### Milestone 6 — Faults and safety (Days 17–18)

**Primary files:** `models/sensor.py`, `diagnostics/alarms.py`, `tests/test_scenarios.py`.

- [ ] Add configurable sensor time constant, noise and bias.
- [ ] Add cold inlet 30 → 27 °C disturbance.
- [ ] Add stuck-valve and actuator lag / saturation cases.
- [ ] Add configurable high-temperature / low-temperature thresholds.
- [ ] Add residual-based anomaly alarm with persistence to suppress noise spikes.
- [ ] Log alert type, activation time and clearance time.
- [ ] Evaluate detection delay and false alarms.

**Important limitation:** fault residuals may respond to model mismatch and unknown disturbances as well as genuine sensor/valve faults. Do not call the system an industrial safety instrumented system.

**Acceptance:** known injected faults produce traceable alerts; normal noise does not repeatedly trigger the alarm with the chosen validated threshold.

### Milestone 7 — Streamlit dashboard (Days 19–20)

**Primary files:** `app.py`, `visualization/charts.py`.

Build these tabs:

1. **Simulation** — start/reset, temperatures, valve command and position, heat duty, operating scenario.
2. **System Identification** — run valve step test, fit models, show parameter table and overlays.
3. **Controller Tuning** — select P / PI / PID and compare tuning methods.
4. **Digital Twin** — observed/predicted temperature, residuals, RMSE.
5. **Fault & Safety** — disturbances, sensor bias, stuck valve, threshold indicators.
6. **Results** — experiment summaries, downloadable CSV and plots.

**Engineering rule:** Streamlit should display precomputed or incrementally advanced simulation results; its rerun mechanism must not silently reset plant state or change simulation time.

**Acceptance:** experiments run from the UI with no source-code editing and can be exported.

### Milestone 8 — Final QA, report and presentation (Day 21)

- [ ] Run `pytest -q` on a clean environment.
- [ ] Verify every README command.
- [ ] Verify units and chart labels.
- [ ] Export the same scenario results from the dashboard and a script; compare.
- [ ] Write the model assumptions and limitations.
- [ ] Add controller comparison table and twin validation table.
- [ ] Prepare 5–7 slides and a 5–6 minute live demo.
- [ ] Record fallback screenshots / plots in case the demo environment fails.
- [ ] Mark implemented vs pending features accurately in README.

**Acceptance:** another team member can reproduce the final demonstration without the original developer present.

## 5. Team division (adapt to your team size)

| Workstream | Suggested owner | Dependencies | Main deliverables |
|---|---|---|---|
| Physics and numerical model | Member A | Configuration | `plant.py`, equilibrium, tests |
| PID and tuning | Member B | Plant interface | `pid.py`, tuning, control tests |
| Identification and twin | Member A + B | Open-loop data | Fit functions, twin, metrics |
| Scenarios, safety and UI | Member C / shared | Core simulation | Scenarios, alarms, dashboard |
| Documentation and integration | All | All modules | PR reviews, runbook, report |

**For a two-person team:** Person 1 owns physics, identification, and twin; Person 2 owns controller, scenarios and dashboard. **Both** review tests, run integration experiments, and write the report.

A task is not complete until another collaborator can execute its tests.

## 6. Testing matrix

| Test ID | What to verify | Expected behavior |
|---|---|---|
| PHY-01 | Two heat-transfer terms sum to zero | Energy exchange cancels algebraically |
| PHY-02 | ODE derivative at nominal equilibrium | Approx. zero |
| PHY-03 | Hot flow rise at fixed inlet conditions | Cold-side outlet approaches higher steady temperature |
| PHY-04 | Valves at 0 and 1 | No out-of-range commands or flow |
| ID-01 | FOPDT fit on synthetic response | Stable finite parameters |
| ID-02 | Hold-out validation | Error reported on unused data |
| PID-01 | Error sign | Low measured temp requests more heating |
| PID-02 | Output saturation | Command limited to [0,1] |
| PID-03 | Anti-windup | Integral recovers after saturation |
| PID-04 | Setpoint change | Feasible setpoint reached stably |
| PID-05 | Inlet disturbance | Closed-loop returns near target |
| TWIN-01 | Independent parameter fitting | No hidden plant parameters leaked |
| TWIN-02 | Held-out scenarios | MAE and RMSE computed correctly |
| SAFE-01 | +2 °C sensor bias | Residual / anomaly response logged |
| SAFE-02 | Stuck valve | Diagnostic response logged |
| REPRO-01 | Same seed and configuration | Same numerical results |
| UI-01 | Export | CSV reproduces displayed signals |

Use physical tolerances derived from integration accuracy, sensor noise, and metric definitions. Avoid arbitrary assertions such as “RMSE is always below 0.1 °C” until experiments justify them.

## 7. Canonical demo scenarios

### Demo A — Identify the plant (open loop)
- Equilibrate near 55 °C cold outlet.
- Hold valve at 40%, step to 50%.
- Record complete hot/cold responses.
- Estimate gain, lag and effective dead time.
- Plot model prediction against an independent validation step.

### Demo B — Track a new setpoint
- Initialize at an equilibrium around 55 °C.
- At `t=60 s`, change setpoint to 57 °C.
- Compare PI and PID with documented gains.
- Display outlet temperature, setpoint and valve position.
- Report overshoot, IAE, settling time and actuator effort.

### Demo C — Reject an inlet disturbance
- Initialize closed loop at 55 °C.
- At `t=100 s`, step cold inlet from 30 to 27 °C.
- Show temperature deviation and recovery.
- Compare open loop versus closed loop using equal operating conditions.

### Demo D — Validate the twin
- Run a disturbance scenario excluded from parameter fitting.
- Use recorded inputs in the prediction model.
- Plot virtual plant output, predicted output and residual.
- Report held-out MAE/RMSE with explicit assumptions.

### Demo E — Monitor a simulated sensor fault
- Apply sensor bias of +2 °C at a chosen simulation time.
- Show true plant temperature, measured temperature, predicted temperature.
- Display alarm activation, threshold and detection delay.
- Discuss limitations of residual-based diagnosis.

## 8. Final report outline

1. Abstract and problem statement
2. Industrial motivation and project objectives
3. System architecture and modeling assumptions
4. Energy-balance derivation, parameters and steady-state analysis
5. Numerical method and simulation implementation
6. Open-loop experiments and empirical system identification
7. PI/PID design and tuning methods
8. Closed-loop comparisons and disturbance rejection
9. Digital twin design, training/validation split and prediction accuracy
10. Actuator/sensor faults, process monitoring and safety limitations
11. Results and discussion: tables and graphs
12. Limitations, possible physical validation and future work
13. Conclusion and references

Do not state measured plant accuracy or industrial safety compliance; the data are simulated.

## 9. Final demo: six-minute run of show

| Time | Presenter action |
|---|---|
| 0:00–0:45 | Explain plant, hot/cold streams and controlled temperature |
| 0:45–1:30 | Show energy balances and computed equilibrium |
| 1:30–2:15 | Show valve step response and fitted transfer function |
| 2:15–3:30 | Run 55 → 57 °C PI vs PID comparison |
| 3:30–4:30 | Inject 30 → 27 °C inlet disturbance and show recovery |
| 4:30–5:30 | Show twin prediction and sensor-bias alarm |
| 5:30–6:00 | Summarize quantitative results, limitations and syllabus mapping |

Prepare static exported graphs as backup; the dashboard should remain demonstrable without internet access.

## 10. Branch, PR and review workflow

Suggested GitHub workflow:

1. Assign a milestone-specific issue.
2. Branch from `main` (e.g. `feat/plant-model`, `feat/pid-controller`).
3. Commit small, reviewable changes.
4. Add/modify tests in the same branch as the code.
5. Open a PR: purpose, equations/assumptions, sample graph, tests run, known limitations.
6. Have a teammate review scientific correctness and code quality.
7. Merge only after tests pass.

Suggested initial issues:
- `[M0] Python project bootstrap + test CI`
- `[M1] Heat exchanger ODEs and equilibrium solver`
- `[M1] Energy-balance and valve-limit unit tests`
- `[M2] Step test generation + FOPDT fitting`
- `[M3] PI controller with anti-windup`
- `[M4] Deterministic scenario engine and metrics`
- `[M5] Calibrated twin and held-out validation`
- `[M6] Sensor/valve fault scenarios and alarms`
- `[M7] Streamlit interface and exports`
- `[M8] Scientific report and live demo`

## 11. Priorities if the deadline is close

**Priority 1 (must work):** valid nonlinear plant, nominal equilibrium, open-loop plot, PI, disturbance rejection, dashboard.  
**Priority 2 (strong course project):** PID tuning comparisons, FOPDT identification, metric tables, valve model, alarms.  
**Priority 3 (distinguishing feature):** genuinely calibrated independent twin, held-out accuracy and sensor-fault studies.  
**Stretch:** online parameter estimation; only after every main test passes.

## 12. First coding checkpoint

Begin with **Milestone 0 and Milestone 1**, in this exact order:

1. Create package skeleton and parameter loader.
2. Implement energy-balance `rhs` with correct units.
3. Implement analytic steady-state solver for nominal conditions.
4. Write steady-state and energy-conservation tests.
5. Generate the first open-loop temperature response.
6. Commit the result in a reviewed PR.

**Stop/go condition:** no PID, digital twin or dashboard development until the physics milestone passes its tests.

---

**Project philosophy:** A smaller, physically correct and reproducible simulator with justified control design is better than a visually sophisticated dashboard with unverifiable dynamics.
