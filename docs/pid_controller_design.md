# Phase 4 — Discrete P/PI/PID temperature control and nonlinear validation

## Scope, physical model and control objective

HEATWIN's **illustrative, simulated** two-lumped water-to-water heat exchanger has physical states `x=[Tc, Th, xv]`: cold and hot bulk/outlet temperatures (°C), and actual normalized valve opening (0–1). The **controlled output** is `Tc`, the measured output for Phase 4 is an ideal simulated `ym=Tc` (optional constant measurement offset for tests), and the manipulated **valve command** `u` is saturated to [0, 1]. A positive valve command increases hot-water mass flow and normally increases cold outlet temperature: *positive controller gain is the correct feedback polarity*. The reference plant is the **unchanged Phase 2** `heatwin.models.plant.rhs`; controller gains are derived from the **unchanged Phase 3** `configs/identified/phase3_fopdt_nominal.json`.

No predictive twin, sensor model, fault detection or full dashboard was implemented here. No equipment was tested.

## Operating-point and FOPDT basis

Phase 3 selected a deviation-variable transfer function around `u0=0.40`:

\[
G(s)=\frac{\Delta T_c(s)}{\Delta U(s)}=\frac{13.9565387\,e^{-7.44692445s}}{25.8624268s+1}.
\]

`K=13.9565387 °C/valve fraction`, `τ=25.8624 s`, `θ=7.4469 s`. A valve fraction is **not a percentage point**: using a 10 percentage-point increase in input means `Δu=0.10`. The empirical fit approximates three nonlinear physical states and is not global. The actual 55°C regulating equilibrium is independently calculated with `steady_state_for_target(55, params)`, obtaining approximately `u_eq=0.4083308598`, **not the training baseline `u0=0.40`**. The controller is initialized to track `u_eq` at zero error; it never jumps to the identification baseline.

## Parallel control law and sampling convention

Let `e[k]=r[k]-ym[k]` with sampling period `Ts` in seconds. The zero-order-held command for `[t_k,t_{k+1})` is calculated from only `ym[k]` and controller memory:

\[
 u_{raw}[k]=u_b+K_c e[k]+I[k]-K_d d_f[k],\qquad
 u[k]=\min(u_{max},\max(u_{min},u_{raw}[k])).
\]

- **P:** `I=0`, `Kd=0`; the runtime bias can track manual output. P may retain steady-state offset for nonzero disturbances/steps.
- **PI:** `Ki=Kc/Ti` in valve fraction/(°C·s), and after computing `u[k]` the next integral memory is updated with forward rectangular integration, `I[k+1]=I[k]+Ki e[k] Ts` unless anti-windup blocks it. This explicitly prevents the current sample from using future error.
- **PID:** `Kd=Kc Td`, in valve fraction·s/°C. The D term differentiates **measurement**, not the setpoint. A backward-Euler filtered measurement derivative is `d_f[k]=(τ_f d_f[k−1]+ym[k]−ym[k−1])/(τ_f+Ts)`. `τ_f>0` means derivative filtering is stable under positive `Ts`; no setpoint derivative kick occurs. `Td>=0`. A raw derivative of an unfiltered noisy signal is never used.

`Kc` is *controller* gain (valve fraction/°C), distinct from Phase 3 *process* gain (°C/valve fraction). `Ti`, `Td`, `τ_f`, `Ts` are seconds. `bias`, `P`, `I`, `D` and `u` are valve fractions.

The controller is called **only** at `t=k Ts`. A setpoint/inlet step on the grid is applied **before** that instant's controller update; an off-grid step changes the process input immediately, but the controller retains its most recent command until the next scheduled tick. Temperature and valve-position states remain continuous at discontinuities; the solver stops exactly at event times. `solve_ivp` integrates the original nonlinear `rhs` with a zero-order-held input and explicit `rtol=1e-9`, `atol=1e-11` by default. Rows at events are right-continuous in input columns; there is no preview of future plant measurements.

## Bumpless initialization, saturation, anti-windup

Initialization at `(Tc_eq, Th_eq, xv_eq)` uses `manual_command=u_eq` and the first measured temperature to set controller memory. PI/PID initialize `I0=u_eq−u_b−Kc e0` and the derivative state to zero. P instead adjusts its runtime bias to track the manual command; the configured bias remains unchanged. Repeated independent simulations each instantiate a fresh PIDController.

The valve has physical saturation `0<=u<=1`; `u_raw` is preserved for diagnosis. **Conditional integration** freezes the integral state whenever the unsaturated command is at/above the upper bound and `Ki*e` would push it further up, or at/below the lower bound and `Ki*e` would push it further down. This avoids persistent windup without introducing an arbitrary integral hard cap. A deliberate `anti_windup="none"` option is provided solely for an instructional comparison. The Phase 2 actuator `dxv/dt=(u−xv)/τv` remains unchanged, so actual `xv` lags `u` and hot flow depends on `xv`.

## Tuning rules derived from the saved Phase 3 process model

All methods read K, τ and θ from `configs/identified/phase3_fopdt_nominal.json` and validate finite parameters, correct units, nonzero K, positive τ and nonnegative θ. **Manual baseline** is a deliberately conservative, *not optimized* trial: `Kc=0.5/K`, `Ti=τ` for PI, or P alone with the same gain. These are stated design choices, not experimentally identified controller gains.

**Classical Ziegler–Nichols open-loop reaction-curve rules** (not ultimate gain):

| Mode | Controller gain `Kc` | Integral time `Ti` | Derivative time `Td` |
|---|---|---|---|
| P | `τ/(K θ)` | — | — |
| PI | `0.9 τ/(K θ)` | `3.33 θ` | — |
| PID | `1.2 τ/(K θ)` | `2 θ` | `0.5 θ` |

Z-N is explicitly rejected if θ is zero/near zero. The chosen PID derivative filter time is `max(Ts,Td/10)`. These classical rules tend to be aggressive; actuator saturation and nonlinear dynamics are verified experimentally.

**IMC/SIMC-style PI:** `Kc=τ/[K(λ+θ)]`, `Ti=min(τ,4(λ+θ))`, with λ positive in seconds. This is a documented SIMC-type approximation for a FOPDT plant; it is not a proof of robust performance. Three tested response-speed choices are `λ=0.5τ` (aggressive), `λ=τ` (moderate) and `λ=2τ` (conservative).

## Quantitative metrics and their meaning

`evaluate_control(frame, window_start_s=t_event, reference_initial_c=...)` integrates **sampled error** by trapezoids: `IAE=∫|e|dt` (°C·s), `ISE=∫e²dt` (°C²·s), `ITAE=∫(t−t_event)|e|dt` (°C·s²). Time in ITAE is measured **from the event**, not from the beginning of the experiment. Total command movement is `Σ|Δu|` (fraction), valve movement is `Σ|Δxv|` (fraction), and saturation duration sums zero-order-held saturated intervals (s). `max_command` is a valve fraction. `observed_final_error_c` is the observed final tracking error, **not** a claim of true steady-state error.

For a single setpoint change, overshoot/undershoot are measured in the direction of the step, rise time measures interpolated 10%-to-90% traversal, and settling time is first entry into a ±0.1°C band **followed by remaining in the band through the last sample**. If not observed, settling time is `null` rather than a fabricated number. For constant-setpoint disturbance experiments and multiple consecutive setpoint steps, the step-based overshoot/rise metrics are not claimed applicable.

## Executed experiments and scientific results

Reproduce exactly with:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
python scripts/phase4_control_experiments.py --output-dir outputs/phase4
```

The script simulates constant 55°C operation; 55→57°C and 55→53°C setpoint changes at 60 s; multiple changes at 60/180/300 s; cold inlet 30→27°C, hot inlet 80→75°C, and cold flow 0.030→0.035 kg/s at 100 s; an impossible 80°C step at 60 s returning to 55°C at 220 s; and fixed-tuning robustness under UA±20%, hot inlet±10%, double valve lag and increased cold flow. There are also matched open-loop cold-inlet trajectories. Seven controller tunings are compared on the positive setpoint step. The actual results are recorded in `outputs/phase4/controller_comparison.csv`, `robustness.csv`, `summary.json`, `selected_controller.json`, scenario CSVs and eight figures. `configs/control/phase4_recommended.json` stores the verified nominal recommendation and can be loaded without rerunning simulations.

**Measured positive-step results** (post-60s window, final sample at 420s):

| Controller | `Kc` (fraction/°C) | `Ti` (s) | `Td` (s) | IAE (°C·s) | Overshoot (°C) | Settling (s) | Final Tc (°C) |
|---|---:|---:|---:|---:|---:|---:|---:|
| P manual | 0.035826 | — | — | 488.665 | 0 | not observed | 55.6852 |
| PI manual | 0.035826 | 25.8624 | — | 111.315 | 0 | 160 | 56.9962 |
| PI IMC moderate | 0.055632 | 25.8624 | — | 71.478 | 0 | 92 | 56.9999 |
| PI Z-N | 0.223953 | 24.7983 | — | 34.051 | 0.4675 | 46 | 57.0000 |
| PID Z-N | 0.298604 | 14.8938 | 3.7235 | 32.656 | 0.4686 | 50 | 57.0000 |
| PI IMC conservative | 0.031317 | 25.8624 | — | 127.143 | 0 | 187 | 56.9914 |
| PI IMC aggressive | 0.090934 | 25.8624 | — | 43.461 | 0.0041 | 44 | 57.0000 |

**Physical feasibility warning:** If the actual hot inlet falls 10% (80→72°C), the maximum cold-outlet equilibrium (at fully open valve) is only **55.32736°C**, so a 57°C target cannot be achieved by *any* controller in this model. The recorded PI run saturates at 100% command and approaches 55.32736°C; it is **not** claimed as failed controller tuning or unstable behavior. The other listed parameter perturbations produce physically feasible 57°C targets within the tested duration. The time traces prove finite behavior for these cases, **not global or mathematical robust stability**.

The windup demonstration shows the conditional-integrator controller recovering toward 55°C after the infeasible demand ends; without anti-windup, accumulated integral holds the valve saturated at 100% and the process remains near its maximum temperature during the entire observation window.

### Why IMC-PI is recommended for Phase 5

Moderate IMC-PI is chosen as a physically interpretable, low-overshoot, stable **simulation-tested** controller with no sustained feasible-setpoint offset. Z-N PI/PID achieve smaller IAE in this nominal positive step but produce ~0.47°C overshoot and more aggressive valve action. A more aggressive IMC PI is a candidate for additional engineering review. **No claim is made that PID is always better than PI.** Controller performance has been evaluated only on this nonlinear simulator for these scenarios, with no real sensor noise or hardware uncertainty.

## Reusable interfaces and Phase 5 data boundary

```python
from pathlib import Path
from heatwin.config import load_config
from heatwin.control.tuning import load_identified_model, imc_pi
from heatwin.simulation.closed_loop import SetpointStep, simulate_closed_loop

params = load_config()
model = load_identified_model(Path("configs/identified/phase3_fopdt_nominal.json"))
settings = imc_pi(model, lambda_s=model.tau_s)
frame = simulate_closed_loop(params, settings,
                             setpoint_steps=[SetpointStep(60, 57)], duration_s=420)
```

The per-time output columns are `time_s`, `setpoint_c`, `tc_c`, `measurement_c`, `th_c`, `error_c`, `u`, `u_raw`, `xv`, `mh_kg_s`, `mc_kg_s`, `tc_in_c`, `th_in_c`, `q_w`, `p_term`, `i_term`, `d_term`, `saturated`, `controller_sample`. Output `DataFrame.attrs` stores parameters, settings, initial equilibrium, event lists, solver tolerances and sampling metadata. Phase 5 **must distinguish** real measurement channels (`measurement_c`, `u`, measured inlet signals) from hidden state/plant coefficients (`th_c`, `xv`, true `tc_c`, `ua`). A twin may use hidden signals only in a clearly identified benchmark or when a sensor is explicitly assumed available; do not leak reference-model parameters to its training logic.

## Scientific limitations

The first-law plant assumes two perfect mixes, constant liquid properties and UA, fixed hold-ups, no heat loss or hydraulic/transport delay, and a linear saturating valve characteristic with first-order lag. The FOPDT dead time approximates higher-order dynamics, not a measured physical delay. Tuning correlations are heuristic and continuous-time-inspired while controllers are sampled. No sensor dynamics/noise, actuator stiction, multivariable effects or industrial equipment were validated. Controller performance metrics depend on the window, tolerance band, model fidelity, event amplitudes and time horizon. Z-N aggressive behavior can be undesirable outside these tested cases. Future control retuning or robust stability analysis must be explicitly scoped and verified.
