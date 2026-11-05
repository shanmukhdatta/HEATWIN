# Phase 3 — System identification and local transfer-function validation

## Objective and scientific boundaries

HEATWIN performs **simulation-based empirical identification** using the independently implemented **Phase 2 nonlinear heat-exchanger reference plant**, rather than fitting synthetic textbook curves and calling them physical experiments. The reference process contains two thermal states and one first-order actuator state. All identification fits here describe the **overall normalized valve-command → cold-outlet temperature** relationship. No controller, predictive twin, or fault detector is implemented in Phase 3.

For the reference plant, with state `x = [Tc, Th, xv]` and command `u`:

\[
\dot T_c = \frac{m_c c_p(T_{c,in}-T_c)+UA(T_h-T_c)}{\rho V_c c_p},\quad
\dot T_h = \frac{m_h c_p(T_{h,in}-T_h)-UA(T_h-T_c)}{\rho V_h c_p},
\]
\[
\dot x_v = [\operatorname{clip}(u,0,1)-x_v]/\tau_v,\quad
m_h=m_{h,min}+(m_{h,max}-m_{h,min})\operatorname{clip}(x_v,0,1).
\]

The plant parameters remain those in `configs/default.yaml`: `rho=1000 kg/m³`, `cp=4180 J/(kg·K)`, `Vc=Vh=0.001 m³`, `UA=350 W/K`, `Tc_in=30°C`, `Th_in=80°C`, `mc=0.030 kg/s`, `mh_min=0.010 kg/s`, `mh_max=0.100 kg/s`, valve time constant `4 s`, sampling interval `1 s`. The configuration describes *illustrative* water properties; all results are simulated and are not validated against industrial equipment.

## Experimental design and equilibrium selection

The `create_step_experiment()` API computes an **analytical equilibrium** with `steady_state_for_valve(u0, params)`, initializes the physical state `y=[Tc0,Th0,u0]`, and invokes the existing `simulate_open_loop()` function. That Phase 2 integrator restarts SciPy `solve_ivp` at input step times (including nongrid timestamps), retaining continuous states and right-continuous commands. The exported DataFrame includes `time_s, tc_c, th_c, u, xv, mh_kg_s, q_w, tc_in_c, th_in_c, mc_kg_s`. Each CSV has a companion JSON containing the exact source parameter snapshot, solver settings, equilibrium and split label. The initial and final equilibria are saved as **reference checks**, but never passed to the empirical optimizer as parameter estimates.

The nominal operating point `u0=0.40` has `Tc0≈54.869935°C` and `Th0≈63.780477°C`. A commanded positive step `+0.10` at `t_s=60 s` gives `0.40→0.50`; the plant is simulated for `480 s`, giving `420 s` after the step to approach its computed terminal equilibrium. A separate validation experiment uses `0.40→0.45`; the *final test* uses `0.40→0.35`. Validation and test trajectories are **never** supplied to `fit_step_response()`; fitting is performed only on nominal training samples. Additional **diagnostic studies**, not used in choosing the final model, independently test positive and negative amplitudes `±0.05`, `±0.10` at 0.40 and operating points `0.30`, `0.40`, `0.50`, `0.60` with `+0.05` steps. A counterfactual study across operating points should not be conflated with validation at the same point.

Data-derived finite-step process gain is `K_process=(mean(Tc_final_tail)-mean(Tc_pre_step))/(mean(u_final_tail)-mean(u_pre_step))`, with 20-second baseline and settled-tail windows. This has units **°C per full unit of valve fraction**, not per percentage point (divide by 100 for °C per 1 percentage point). `process_gain` is **not** PID `controller_kp`. For the nominal +0.10 step, empirical steady gain is ≈13.9415 °C/fraction while the infinitesimal derivative at u0=0.4 is ≈15.7844 °C/fraction; nonlinear saturation/operating-point dependence explains the difference.

## Deviations and empirical model forms

All transfer functions map **deviations**:

\[
\Delta u = u-u_0,\quad \Delta T_c=T_c-T_{c,0},\quad
G(s)=\Delta T_c(s)/\Delta U(s).
\]

Absolute predictions add the observed pre-step baseline back: `Tc_pred(t)=Tc0+ΔTc_pred(t)`. The actuator is included because the **input is `u`, not `xv`**.

- **FO:** `G_fo(s)=K/(τs+1)`, with `τ>0`. The 63.2% crossing method linearly interpolates the recorded threshold `Tc0+0.6321205588(Tc_final−Tc0)` and subtracts *actual step time*; it is an approximation for the three-state plant, not an exact physical time constant. The numerical FO fit uses bounded nonlinear least squares.
- **FOPDT:** `G_fopdt(s)=K exp(−θs)/(τs+1)` with `τ>0, θ≥0`. The analytical step response is `ΔTc=K Δu [1−exp(−(t−ts−θ)/τ)]` after `ts+θ`, otherwise zero. `θ` is an **effective lag**, not a proven transport delay.
- **Second order:** `G_2(s)=K/[(τ₁s+1)(τ₂s+1)]`, `τ₁,τ₂>0`. The analytic real-pole step response is used, including the repeated-pole limit `1−(1+t/τ)e^(−t/τ)`. This approximation has **two poles**, while the physical valve+two-thermal-state model has **three**, so no exact equality is claimed. Non-oscillatory water-to-water responses do not require an invented oscillatory model.

`scipy.optimize.least_squares` uses finite gain limits informed by the measured step, positive time-scale bounds, nonnegative delay, a physically valid pole pair, reaction-curve initial guesses from interpolated 28.3% and 63.2% crossings (or a documented fallback for degenerate curves), and strict optimizer-success checks. Optimization uses **post-event samples** so long pre-event plateaus do not dilute the error; independent metrics are also calculated over the post-event period. Synthetic FO/FOPDT/SO benchmark curves appear **only in unit tests to check estimator recovery**. Actual physical identification uses Phase 2 trajectories.

`predict_piecewise_steps()` handles multiple normalized valve-command steps under the local **linear time-invariant superposition** assumption. The single-step analytic response formula is never misapplied to arbitrary multiple-step signals without superposition. This predictor must be used with initial states settled at the specified operating point; it is not a globally nonlinear simulation.

## Analytical local linearization

At an **interior valve equilibrium** (`0<u0<1`, away from non-differentiable clipped endpoints) let

\[
a_c=\frac{m_c}{\rho V_c},\quad b_c=\frac{UA}{\rho V_c c_p},\quad
 a_h=\frac{m_h}{\rho V_h},\quad b_h=\frac{UA}{\rho V_h c_p},
\]
\[
g_v=\frac{(m_{h,max}-m_{h,min})(T_{h,in}-T_{h,0})}{\rho V_h},\quad \lambda_v=1/\tau_v.
\]

The exact Jacobian for deviations `δx=[δTc,δTh,δxv]` and `δu` is

\[
A=\begin{bmatrix}
-(a_c+b_c)&b_c&0\\
b_h&-(a_h+b_h)&g_v\\
0&0&-\lambda_v
\end{bmatrix},\quad
B=\begin{bmatrix}0\\0\\\lambda_v\end{bmatrix},\quad
C=\begin{bmatrix}1&0&0\end{bmatrix},\quad D=0.
\]

This yields a *third-order* analytical local transfer function:

\[
G_{local}(s)=\frac{b_c g_v\lambda_v}{(s+\lambda_v)[(s+a_c+b_c)(s+a_h+b_h)-b_c b_h]}.
\]

The numerator is constant and the cubic denominator is monic; `scipy.signal.TransferFunction` and `StateSpace` are constructed from these coefficients. Finite-difference derivatives of the **original Phase 2 `rhs()`** verify both analytical matrices. Poles must lie in the left-half plane. The local state-space step response is obtained directly from the matrix exponential, and tested against the nonlinear plant for a small valve perturbation (where deviations are expected to agree).

At `u0=0.40`, the nominal derived Jacobian and poles are recorded by the executed script in `summary.json`. The linear state-space model is exact to first order at that point but may have a *larger* error on the `+0.10` training step than simpler empirical models fitted to that finite amplitude, because the process gain changes with valve opening.

## Independent validation and model selection

`error_metrics()` reports `MAE`, `RMSE`, maximum absolute error, and `fit% = 100 × [1−||y−ŷ||₂ / ||y−mean(y)||₂]`; for constant reference signals the normalized fit percentage is explicitly **undefined** (`null`) rather than dividing by zero. All dimensions and finiteness are checked. The systematic errors in these noise-free simulations arise predominantly from **model-order reduction and operating-point nonlinearities**, not measurement noise.

### Executed nominal comparison (Python 3.13.5, 480-second experiments)

| Model | Gain (°C/fraction) | Lag(s) (s) | Effective θ (s) | Train RMSE (°C) | Validation RMSE (°C) | Final-test RMSE (°C) |
|---|---:|---|---:|---:|---:|---:|
| FO | 14.038299 | 33.957303 | 0 | 0.041315 | 0.044901 | 0.135794 |
| FOPDT | 13.956539 | 25.862427 | 7.446924 | 0.008731 | 0.039541 | 0.133798 |
| Two-pole | 13.932491 | 10.538866, 21.787097 | 0 | 0.005482 | 0.039387 | 0.133763 |
| Analytical local model | 15.784375 | three physical poles | 0 | 0.167050 | 0.044244 | 0.050203 |

All errors are calculated **after the step**, without pre-step dilution. Validation (`u=.40→.45`) and final test (`u=.40→.35`) were held out from fitting. The 0.05-step validation difference between FOPDT and the two-pole model is about **0.000154°C RMSE**, negligible relative to their complexity difference. On the **negative** held-out step, both empirical models have larger errors (≈0.134°C), warning that one +0.10 experiment does not establish a global linear model. The analytic linear model yields smaller error on that particular negative perturbation, without contradicting the finite-amplitude training fit.

**Recommended Phase 4 starting point: FOPDT** around `u0=0.40`, because it gives nearly second-order validation accuracy with a one-lag-plus-delay form widely usable for interpretable PI/PID tuning and disturbance analysis. This does **not** imply that FOPDT is exact or that tuning is guaranteed stable. The selected result is saved at `outputs/phase3/selected_model.json` during script execution with the operating point, numerator/denominator, sampling interval, fitted coefficients, training/validation/final-test RMSE, tested command interval and units; load it directly instead of re-running optimization. The interval `[0.30,0.50]` denotes explored inputs, not a demonstrated accuracy guarantee.

## Figures and reproducibility

Run from the repository root after installation:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
python scripts/phase3_identification.py --output-dir outputs/phase3
```

Figures 1–7 are generated from *real* `create_step_experiment()` trajectories and fitted predictions: plant step response; FO fit; FOPDT fit; second-order fit; five-way comparison; residuals; operating-point gain/lag sensitivity. `model_comparison.csv`, `amplitude_sensitivity.csv`, `operating_point_sensitivity.csv`, per-experiment `*_metadata.json` and raw CSV signals, `summary.json`, and `selected_model.json` are regenerated by the script. GitHub Actions also runs the experiment script and uploads an archive of the generated outputs. Do not claim those figures are measurements from actual hardware.

Notebook `notebooks/02_system_identification.ipynb` calls these tested routines without duplicating fitting logic. The CI workflow retains Phases 1–2 tests and adds the Phase 3 suite. The final main-branch merge must follow Phase 1 and Phase 2 because this PR is stacked on Phase 2.

## Limits and future phases

The reference model assumes fixed density, heat capacity, `UA`, perfect mixing, no heat losses, no phase change, and a linearized valve characteristic with a first-order lag. The identification models describe **local open-loop deviations** for settled initial conditions, no measurement noise, and known command step times. Fitted dead time is effective. The two-pole model does not capture all three physical poles; plant time constants are not globally identical across valve operating points. Identification of hot inlet disturbances, sensor dynamics, control signals or an independently calibrated predictive twin is deliberately outside Phase 3. Phase 4 must verify closed-loop tuning against the nonlinear physical plant under multiple perturbations and saturation, not rely solely on the fitted transfer function.
