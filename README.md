# HEATWIN — Heat Exchanger Digital Twin with PID Control

> **A software-only Process Dynamics and Control project**  
> Dynamic modeling · System identification · P/PI/PID tuning · Digital twin prediction · Disturbance rejection · Fault monitoring

**Repository:** https://github.com/shanmukhdatta/HEATWIN  
**Course:** Process Dynamics and Control (ICDC0307)  
**Context:** Undergraduate Chemical Engineering project, NIT Jalandhar  
**Status:** 🧭 Planning / implementation not yet started

> **Important:** This README describes the **target system**, not currently implemented features. HEATWIN is a **simulation-based digital twin prototype**, not a validated industrial plant twin.

## 1. Project overview

Industrial heat exchangers transfer energy from a hot fluid to a cold fluid. Their outlet temperatures change when inlet temperatures, flow rates, or valve positions change. In industry, feedback control is used to hold the process temperature near a desired **setpoint** even when disturbances occur.

**HEATWIN** will simulate a hot-water/cold-water heat exchanger and use a discrete-time **P / PI / PID controller** to regulate the cold-side outlet temperature by manipulating hot-side flow through a simulated control valve. An independently calibrated **digital twin** will predict the temperature response and compare its estimates with the simulated reference plant. A Streamlit dashboard will expose controls, trends, diagnostics, and reproducible experiments.

**Example:** Cold water enters at **30 °C** and hot water at **80 °C**. The controller seeks to maintain a cold-side outlet setpoint of **55 °C**. If cold inlet temperature falls or cold flow changes, the control valve adjusts the hot-water flow.

No pumps, sensors, heaters, microcontrollers, or other physical hardware are required.

## 2. Why this project?

The project combines the five course sections in one coherent application:

| Syllabus area | Planned HEATWIN work |
|---|---|
| Modeling for Process Dynamics | Degrees of freedom, assumptions, lumped energy balances, nonlinear ODEs, dynamic response |
| Development of Empirical Models | Open-loop step testing, first-order plus dead time (FOPDT), second-order fitting, model validation |
| Industrial Controller Design and Tuning | P, PI, PID, Ziegler–Nichols, IMC-inspired tuning, servo/regulatory response metrics |
| Final Control Elements | Valve position, hot-side flow mapping, actuator time constant, saturation and anti-windup |
| Process Applications, Safety & Hazards | Inlet disturbances, valve faults, sensor bias, overtemperature alarms, diagnostic residuals |

## 3. Project objectives

1. Derive and implement a physically consistent dynamic heat-exchanger model.
2. Verify model equilibria and conservation of energy.
3. Identify empirical transfer-function models from simulated open-loop step tests.
4. Design discrete-time P, PI, and PID controllers and compare tuning approaches.
5. Evaluate setpoint tracking, disturbance rejection, actuator saturation, and control effort.
6. Build a predictive twin **separate from** the simulated reference plant, estimate its parameters from training data, and validate it on held-out scenarios.
7. Add virtual sensors, fault scenarios, process alarms, and model-error monitoring.
8. Deliver an interactive, repeatable Streamlit dashboard and technical report.

## 4. How the system works

```text
                         +--------------------+
 Temperature setpoint -->|  P / PI / PID       |--> Valve command
          ^              |  controller         |         |
          |              +--------------------+         v
          |                                       +-------------+
          |                                       | Valve model |
          |                                       +-------------+
          |                                              |
          |                                     Hot-side flow rate
          |                                              |
          |                                              v
          |                                   +--------------------+
          |    Temperature measurement <------| Virtual heat       |
          +------(feedback via error)---------| exchanger plant    |
                                              +--------------------+
                                                        |
                                  Time-stamped operating inputs + measurements
                                                        |
                                                        v
                                              +--------------------+
                                              | Predictive twin    |
                                              | and residuals      |
                                              +--------------------+
                                                        |
                                                        v
                                              Dashboard + alarms
```

**Controlled variable:** cold-side outlet temperature, `T_c`.  
**Manipulated variable:** hot-side valve command, `u`, which determines hot-side mass flow.  
**Disturbances:** cold inlet temperature, hot inlet temperature, cold-side flow, heat-transfer degradation.  
**Measured signal:** simulated temperature sensor (optional lag, bias, and noise).

The reference plant uses the physics-based dynamic model. The twin is **identified independently** and should not share hidden plant states or hidden true parameters. Its prediction accuracy will be evaluated against data **not used for calibration**.

## 5. Mathematical model (baseline)

The first release uses a **two-lumped-capacitance** heat exchanger: one well-mixed thermal state per fluid. It is intentionally simpler than a distributed countercurrent shell-and-tube model.

For water on both sides:

```text
rho * Vc * cp * dTc/dt = mc * cp * (Tc_in - Tc) + UA * (Th - Tc)
rho * Vh * cp * dTh/dt = mh * cp * (Th_in - Th) - UA * (Th - Tc)
```

**Definitions:** `Tc, Th` = cold/hot fluid bulk/outlet temperatures (°C); `Tc_in, Th_in` = inlet temperatures (°C); `mc, mh` = mass flow rates (kg/s); `rho` = density (kg/m³); `Vc, Vh` = hold-up volumes (m³); `cp` = specific heat (J/kg/K); `UA` = effective heat conductance (W/K).

**Heat transfer:** `Q = UA * (Th - Tc)`.

**Valve dynamics:**

```text
tau_v * dx_v/dt = clip(u, 0, 1) - x_v
mh = mh_min + (mh_max - mh_min) * clip(x_v, 0, 1)
```

`x_v` is normalized actual valve position, `u` is normalized controller command, and `tau_v` is actuator time constant. The actuator and plant are advanced at the same simulated time base.

**Modeling assumptions:** constant liquid properties, constant effective `UA` in the baseline, perfect mixing within each side, no phase change, no ambient heat loss, fixed hold-up, and no hydraulic pressure-drop model. These limitations must be stated in the final report.

### Nominal parameters (illustrative; not measured)

| Parameter | Value |
|---|---:|
| Cold inlet temperature | 30 °C |
| Hot inlet temperature | 80 °C |
| Cold-side mass flow `mc` | 0.030 kg/s |
| Hot-side flow bounds `mh_min`, `mh_max` | 0.010–0.100 kg/s |
| Cold-side hold-up `Vc` | 0.001 m³ |
| Hot-side hold-up `Vh` | 0.001 m³ |
| Density `rho` | 1000 kg/m³ |
| Specific heat `cp` | 4180 J/(kg·K) |
| Effective conductance `UA` | 350 W/K |
| Valve time constant `tau_v` | 4 s |
| Controller sampling interval | 1 s |
| Example controlled outlet setpoint | 55 °C |

At the ideal steady state for `Tc = 55 °C`, the cold side absorbs approximately **3.135 kW**, the corresponding hot-side outlet is about **63.96 °C**, and nominal valve opening is about **40.8%**. Code must calculate, rather than hard-code, this equilibrium.

### System identification

Conduct an open-loop valve step test, for example `u: 0.40 → 0.50`, and fit an empirical model:

```text
G(s) = K * exp(-theta * s) / (tau * s + 1)
```

Here `K` is gain, `tau` is response time constant and `theta` is effective dead time. Compare against a second-order candidate; hold out separate data to evaluate fit quality.

### Controller

The control error is `e = T_setpoint - T_measured`. The target controller includes proportional action, integral action, optional filtered derivative on measurement, output limiting, and anti-windup. **PI is the baseline**; PID is added for comparison after PI has been validated. All tuning parameters must state their units and sampling period.

## 6. Expected features (roadmap, not yet implemented)

- Interactive Streamlit dashboard: setpoint, P/PI/PID selection, gains, valve position, temperatures, heat duty, alarms.
- Virtual process simulation: deterministic seeded runs, user-specified disturbances, selectable initial conditions.
- System identification: step tests, FOPDT / second-order fits, actual-versus-predicted plots.
- Controller study: manual tuning, Ziegler–Nichols comparison, IMC-style tuning, overshoot, settling time, IAE/ISE and valve effort.
- Digital twin: calibrated predictive model, held-out validation, MAE/RMSE, residual trend.
- Faults and monitoring: cold inlet temperature disturbance, valve sticking/saturation, sensor bias, threshold and residual alarms.
- Export: CSV files, comparison figures, scenario configurations, final report results.

## 7. Planned software stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Main language |
| NumPy and SciPy | Physics simulation, ODE integration, estimation |
| python-control | Transfer functions and response analysis |
| Pandas | Results and CSV export |
| Plotly | Interactive plots |
| Streamlit | Dashboard |
| PyYAML | Parameter / scenario configurations |
| pytest | Automated physics, controller and integration tests |

### Planned installation (after source files are added)

```bash
git clone https://github.com/shanmukhdatta/HEATWIN.git
cd HEATWIN
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
pytest -q
streamlit run app.py
```

> **Not runnable yet:** These commands become applicable after `requirements.txt`, `src/`, `tests/`, and `app.py` are implemented. This repository initially contains project documentation only.

## 8. Proposed repository layout

```text
HEATWIN/
├── README.md
├── IMPLEMENTATION_PLAN.md
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── app.py
├── configs/
│   ├── default.yaml
│   └── scenarios.yaml
├── src/heatwin/
│   ├── __init__.py
│   ├── config.py
│   ├── models/{plant.py,actuator.py,sensor.py,twin.py}
│   ├── control/{pid.py,tuning.py}
│   ├── identification/{step_test.py,fit_models.py}
│   ├── simulation/{engine.py,scenarios.py}
│   ├── diagnostics/{alarms.py,metrics.py}
│   └── visualization/charts.py
├── tests/
├── notebooks/
├── data/synthetic/
├── docs/
└── .github/workflows/tests.yml
```

The dashboard should **not** contain core numerical algorithms. All calculations belong in reusable, testable modules.

## 9. Demonstration experiments

| Experiment | Input / test | Result to show |
|---|---|---|
| A: Open-loop identification | Valve step from 40% to 50% | Temperature response, fitted process parameters |
| B: Setpoint tracking | 55 → 57 °C | PI vs PID, setpoint error, overshoot, settling time |
| C: Disturbance rejection | Cold inlet 30 → 27 °C | Closed-loop recovery and valve response |
| D: Twin prediction | New test scenario unseen in fitting | Plant vs twin trajectories, MAE/RMSE |
| E: Fault monitoring | +2 °C sensor bias or valve sticking | Residual, alarm and detection behavior |
| F: Actuator limitation | Infeasible setpoint / flow limit | Saturation, anti-windup and warnings |

All comparisons must use identical initial conditions, disturbances, simulation horizons and random seeds.

## 10. Success criteria and verification

- Energy-balance conservation and steady state verified against analytical values.
- The open-loop temperature response is physically plausible.
- Controller output remains within 0–100%; integral action behaves sensibly under saturation.
- PI tracks an achievable setpoint and rejects an inlet-temperature disturbance.
- Controller comparisons report reproducible metrics, not just aesthetically pleasing graphs.
- The twin is evaluated on **held-out** simulated measurements and discloses calibration assumptions.
- Sensor-bias and actuator-fault experiments produce testable alarms.
- A clean environment passes `pytest` and runs a reproducible dashboard demo.

These are **acceptance goals**; no experimental results or test passes are claimed before the implementation exists.

## 11. Team collaboration

Suggested workstreams for collaborators:

- **Modeling:** assumptions, equations, equilibria, physics tests.
- **Control:** discrete PI/PID, tuning, saturation and tests.
- **Identification & twin:** step tests, model fitting and independent validation.
- **UI & integration:** scenarios, dashboard, plots, CSV export.
- **Documentation & QA:** experiment scripts, plots, report, presentation, GitHub Actions.

Use one feature branch and pull request per task. A PR should explain what changed, the test performed, expected behavior, and any known limitations. Avoid merging untested physics or control changes directly into `main`.

## 12. Documentation and project progress

See **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)** for the ordered milestones, file-by-file work, responsibility suggestions, numerical checks, test matrix, and final demo plan.

**Initial recommended task:** implement `src/heatwin/models/plant.py`, compute the nominal equilibrium, and write `tests/test_plant.py` before building any dashboard components.

## 13. References

- Seborg et al., *Process Dynamics and Control*.
- Coughanowr and LeBlanc, *Process Systems Analysis and Control*.
- [SciPy `solve_ivp`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html)
- [Python Control Systems Library](https://python-control.readthedocs.io/)
- [Streamlit documentation](https://docs.streamlit.io/)
- [pytest documentation](https://docs.pytest.org/)

---

**HEATWIN** — connecting process engineering theory, classical control, predictive modeling and accessible software demonstrations.
