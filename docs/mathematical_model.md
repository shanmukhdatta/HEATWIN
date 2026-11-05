# Phase 2 — Two-lumped-capacitance heat exchanger model

## Purpose, scope and system boundary

HEATWIN's **virtual reference plant** is an illustrative **water-to-water, two-fluid-hold-up** exchanger. It models one perfectly mixed bulk/outlet temperature on each side and one actuated hot-water valve position. The model is not an experimentally calibrated industrial digital twin, nor a spatially distributed countercurrent shell-and-tube exchanger. Phase 2 covers only **open-loop physics**; no PID, system identification, noise, diagnosis or predictive twin is implemented.

For clarity, use `Tc` and `Th` for the cold-side and hot-side bulk/outlet temperatures; `Tc_in` and `Th_in` for stream inlet temperatures; and the normalized valve position `xv` for the dynamic actuator. All temperature **differences** use kelvin or degrees Celsius equivalently, while displayed absolute temperatures are degrees Celsius.

## First-law derivation

For a perfectly mixed side of a heat exchanger with fixed water hold-up volume `V`, conservation of energy is

> accumulation = mass-flow enthalpy entering − mass-flow enthalpy leaving + net heat added.

With constant water density `rho` and specific heat capacity `cp`, each side has thermal capacity `C = rho * V * cp`, measured in joules per kelvin (J/K). Defining the positive interstream heat duty as transfer from the hot fluid to the cold fluid,

\[
Q = UA(T_h-T_c), \qquad [Q]=\mathrm{W},\quad [UA]=\mathrm{W/K}.
\]

**Cold-side accumulation:**

\[
\rho V_c c_p\frac{dT_c}{dt} = \dot m_c c_p(T_{c,in}-T_c)+UA(T_h-T_c).
\]

**Hot-side accumulation:**

\[
\rho V_h c_p\frac{dT_h}{dt} = \dot m_h c_p(T_{h,in}-T_h)-UA(T_h-T_c).
\]

These are coupled energy balances, not separate exponential curve fits. The two equal-and-opposite heat-transfer terms cancel in the summed balance:

\[
\rho V_c c_p\dot T_c+\rho V_h c_p\dot T_h
=\dot m_c c_p(T_{c,in}-T_c)+\dot m_h c_p(T_{h,in}-T_h).
\]

In particular, the **sum of stored energies** is not generally constant: the flowing inlet/outlet streams exchange energy with the system boundary. Only the **internal** heat exchange cancels. This identity is checked in `tests/test_plant.py` and again on simulated trajectories in `tests/test_open_loop.py`.

## Actuator and state-space representation

Normalize the commanded opening `u` and actual opening `xv` to the interval `[0,1]`. The commanded opening is saturated, while the physical initial valve position is validated:

\[
\dot x_v = \frac{\operatorname{clip}(u,0,1)-x_v}{\tau_v},\qquad
\dot m_h = \dot m_{h,min}+(\dot m_{h,max}-\dot m_{h,min})\operatorname{clip}(x_v,0,1).
\]

The `dot m_h` symbol denotes a mass flow **rate** (kg/s), not the time derivative of the flow. The actual state derivative is `dxv/dt`.

The state vector and operating inputs are

\[
\mathbf{x}=\begin{bmatrix}T_c&T_h&x_v\end{bmatrix}^{\!T},\qquad
\mathbf{w}=\begin{bmatrix}u&T_{c,in}&T_{h,in}&\dot m_c\end{bmatrix}^{\!T}.
\]

The function `rhs(t, y, inputs, params)` in `src/heatwin/models/plant.py` implements

\[
\dot{\mathbf{x}}=\begin{bmatrix}
[\dot m_c c_p(T_{c,in}-T_c)+UA(T_h-T_c)]/(\rho V_cc_p)\\
[\dot m_h c_p(T_{h,in}-T_h)-UA(T_h-T_c)]/(\rho V_hc_p)\\
[\operatorname{clip}(u,0,1)-x_v]/\tau_v
\end{bmatrix}.
\]

The actuator is represented by `hot_mass_flow` and `valve_derivative` in `models/actuator.py`. The model is physically nonlinear in its inputs and states because hot mass flow multiplies `(Th_in - Th)` and varies with valve position.

## Baseline parameters (illustrative, from existing Phase 1 YAML)

| Key | Description | Value | Unit |
|---|---|---:|---|
| `rho` | Water density | 1000 | kg/m³ |
| `cp` | Heat capacity | 4180 | J/(kg·K) |
| `vc`, `vh` | Both fluid hold-up volumes | 0.001 each | m³ |
| `ua` | Overall conductance | 350 | W/K |
| `tc_in`, `th_in` | Inlet temperatures | 30, 80 | °C |
| `mc` | Cold mass flow | 0.030 | kg/s |
| `mh_min`, `mh_max` | Hot flow limits | 0.010, 0.100 | kg/s |
| `valve_tau` | Valve time constant | 4 | s |
| `sample_time` | Default output interval | 1 | s |
| `setpoint` | Illustrative target *for equilibrium only* | 55 | °C |

Temperature setpoint **does not control the system** in Phase 2. The Phase 1 `seed` is retained in configuration for later-phase repeatability; Phase 2 is noise-free and deterministic without random draws.

## Analytical equilibria

Set all three derivatives to zero. At equilibrium the valve position equals its (bounded) command. With `A = mc*cp`, `B = mh*cp` and `H = UA`, the thermal balances become

\[
\begin{bmatrix}A+H&-H\\-H&B+H\end{bmatrix}
\begin{bmatrix}T_c\\T_h\end{bmatrix}=
\begin{bmatrix}AT_{c,in}\\BT_{h,in}\end{bmatrix},
\quad D=AB+H(A+B).
\]

For a specified feasible valve setting, `steady_state_for_valve(u, params, inputs=...)` evaluates the explicit solution

\[
T_c=\frac{AT_{c,in}(B+H)+HB T_{h,in}}{D},\qquad
T_h=\frac{BT_{h,in}(A+H)+HA T_{c,in}}{D}.
\]

A unique thermal equilibrium requires `D>0` (at least one nonzero stream flow when `UA>0`).

For a specified cold outlet target, `steady_state_for_target(Tc_target, params, inputs=...)` inverts the equations:

\[
Q=\dot m_c c_p(T_{c,target}-T_{c,in}),\qquad
T_h=T_{c,target}+Q/UA,
\]

\[
\dot m_h=\frac{Q}{c_p(T_{h,in}-T_h)},\qquad
x_v=\frac{\dot m_h-\dot m_{h,min}}{\dot m_{h,max}-\dot m_{h,min}}.
\]

The implementation checks flow bounds, zero driving force, and degenerate/undefined inversion cases. It **does not clip infeasible target flows** to create a false solution: `ModelError` is raised.

### Nominal 55°C reference state

Using the exact YAML values, not rounding intermediate steps:

- `Q = 0.030*4180*(55 - 30) = 3135 W`
- `Th = 55 + 3135/350 = 63.9571428571°C`
- `mh = 3135 / [4180*(80 - 63.9571428571)] = 0.04674977738 kg/s`
- `xv = (mh - 0.010)/(0.100 - 0.010) = 0.4083308598`, or `40.83308598%`

Older planning notes round this operating point to around 0.04677 kg/s and 40.85%. This report retains the **unrounded derived values**; no physical parameter was changed. Tests verify `||rhs||∞ < 10⁻¹²` at the analytically computed equilibrium.

## Numerical method and discontinuities

`simulate_open_loop()` integrates the coupled three-state ODE using SciPy `solve_ivp` (`RK45` by default, also `DOP853`, `Radau`, `BDF`). The default tolerances are `rtol=1e-9` and `atol=1e-11`. Every input step defines an **exact segment boundary**; the solver never integrates across a discontinuity in `u`, inlet temperature or cold mass flow. The state remains continuous, while input columns at step rows use **right-continuous values**. The output includes regular samples, every exact step time, and the requested final time.

The output is a Pandas DataFrame with columns:

`time_s`, `tc_c`, `th_c`, `xv`, `u`, `mh_kg_s`, `q_w`, `tc_in_c`, `th_in_c`, `mc_kg_s`.

`DataFrame.attrs` contains a parameter snapshot, original initial state, input steps, solver tolerances, sample interval and duration; CSV export uses a separate JSON summary to preserve metadata. All ordinary open-loop runs are deterministic.

Numerical tolerances, step times and initial state shape/physical valve range are validated, integration errors are raised rather than ignored, and non-finite results trigger errors. A maximum output size prevents accidental runaway memory use.

### Reproducing experiments A–E

From an environment with the project installed:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/phase2_experiments.py --output-dir outputs/phase2
```

The script exports **actual** CSV time series, five-panel PNG plots for experiments A–D, and `summary.json` including experiment E's numerical convergence comparison.

- **A:** initialize exactly at computed 55°C equilibrium and hold valve constant for 300 s; no meaningful drift.
- **B:** settle initially at 40%, step valve command to 50% at 60 s, run to 300 s; cold outlet rises.
- **C:** settle initially at 50%, step to 30% at 60 s; cold outlet falls.
- **D:** settle at 40%, change cold inlet from 30°C to 27°C at 100 s; open-loop cold outlet falls.
- **E:** compare B using RK45 `rtol=1e-7`, `atol=1e-9`, output `1 s`, against `rtol=1e-11`, `atol=1e-13`, output `0.25 s`; compare common time instants.

**Finite-duration caution:** 300 s is *not* infinite steady-state time. A 0.1–2 millikelvin residual relative to the new analytical steady state can remain after a large step. Testing the 300 s trajectory against the exact equilibrium to sub-microkelvin tolerance would incorrectly confuse physical transient decay with numerical integration error.

## Assumptions and limitations

1. Both fluids remain in the liquid phase.
2. Density and specific heat are constant.
3. Each side is a perfectly mixed fluid hold-up with one thermal state.
4. No phase change.
5. Overall heat conductance `UA` is constant.
6. No ambient thermal losses.
7. Both hold-up volumes remain fixed.
8. No hydraulic pressure-drop model or hydraulics/transient flow storage.
9. The valve uses an idealized linear flow characteristic with a first-order lag.
10. No spatial profiles, local driving-force variation or distributed shell-and-tube effectiveness modeling.

This model cannot demonstrate real equipment accuracy, fault safety, heat-transfer coefficient variation with flow, or countercurrent terminal-temperature approaches. Exchanger performance and all plotted signals are **simulated**, not measured. Controller design, empirical model identification and separate digital-twin evaluation are **future phases**.
