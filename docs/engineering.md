# Engineering model and verification

All values are simulated; there are no plant measurements or industrial safety claims. The reference plant is a water-to-water exchanger with one perfectly mixed state per side and a first-order hot-flow valve. Inlet and outlet temperatures are in °C; temperature differences have the same magnitude in K. With `Cc=rho Vc cp`, `Ch=rho Vh cp` (J/K), `mc,mh` (kg/s), `cp` (J/kg/K), and `UA` (W/K):

```text
Cc dTc/dt = mc cp (Tc,in - Tc) + UA (Th - Tc)
Ch dTh/dt = mh cp (Th,in - Th) - UA (Th - Tc)
tau_v dx/dt = clip(u, 0, 1) - x
mh = mh_min + (mh_max - mh_min) clip(x, 0, 1)
```

Summing the energy balances cancels the internal heat transfer. Constant density, heat capacity and UA, no heat loss, fixed holdup, no phase change, no pressure dynamics, and perfect mixing are assumed. `Parameters` validates positive physical quantities; `configs/default.json` specifies the nominal plant. For a 55 °C cold outlet, independent algebra gives Q = 3135 W, hot outlet 63.957 °C and valve opening approximately 0.4085. Tests check the unrounded equilibrium, energy balance, response direction and solver grid. RK45 runs with relative tolerance 1e-8 and absolute tolerance 1e-9 on each zero-order-held sample interval. The nominal open-loop 0.5 s versus 1 s grid maximum difference is saved in the study summary; this is one convergence comparison, not a universal error bound.

## Identification and twin

The 0.4 to 0.5 command step beginning at 60 s supplies training data. The first-order and FOPDT models fit the normalized cold-outlet change by least squares. They are validated without refitting against a separate 0.4 to 0.3 step, with predictions and residuals saved in `results/studies/identification_validation.*`. The nominal process is nonlinear in hot flow, so gain depends on operating point; the estimated FOPDT delay represents unmodelled lag, not measured transport delay. A single noiseless simulated training step does not quantify parameter uncertainty.

The twin superposes FOPDT responses to recorded command increments, initialized from the known initial cold temperature. Custom initial plant temperatures or valve positions need not be at equilibrium; the FOPDT model assumes a settled starting point, so its prediction may be poor for those starts. It runs open loop with no hidden plant state or correction. It does not know inlet disturbances, UA changes or valve sticking. Consequently model mismatch, sensor faults and disturbances all affect residuals. The held-out closed-loop runs in `results/studies/case_*.csv` include independent perturbations; they are not used for fitting. Comparison to a simulator is not experimental validation.

## Controller and tuning

`e=SP-measurement`; gains use parallel form `u=bias+Kp e+Ki integral(e dt)+Kd derivative`, in fraction/°C, fraction/(°C s), and fraction s/°C. The derivative is filtered and defaults to derivative on measurement; derivative on error is selectable in the API. The integral is conditionally clamped when saturation would worsen, and explicit initialization permits transfer from manual output. Sampling is explicit. The normal experiments use 1 s. Controller and valve command are bounded to [0,1].

For FOPDT gain K, lag τ and effective delay θ, reaction-curve Ziegler–Nichols PID uses `Kp=1.2τ/(Kθ)`, `Ti=2θ`, `Td=θ/2`; Cohen–Coon uses `r=θ/τ`, `Kp=(4/3+r/4)/(Kr)`, `Ti=θ(32+6r)/(13+8r)`, `Td=4θ/(11+2r)`. Both require positive K, τ and θ and can be aggressive. IMC uses `Kp=(τ+θ/2)/(K(λ+θ/2))`, `Ti=τ+θ/2`, `Td=τθ/(2τ+θ)`, with λ=max(τ,3θ) by default. `Ki=Kp/Ti`, `Kd=Kp Td`. The optimization searches bounded parallel gains to minimize absolute error plus valve movement on a discretized identified model; validation uses the nonlinear plant. A numerical linearization of the sampled PID plus nonlinear plant at the nominal unsaturated equilibrium gives spectral radii in `results/studies/summary.json`; all five tested PID tunings are locally asymptotically stable there. This check does not cover saturation, parameter ranges or global nonlinear stability. Correlations and an optimizer cannot establish robustness or stability in general. Compare the finite-horizon responses, saturation and valve travel in `results/studies/summary.json` and `tuning.png`.

## Monitoring and metrics

A residual exceeds 1 °C for three consecutive samples before an anomaly alarm is asserted; the threshold and persistence are configurable in the API. Temperature safety monitoring uses observed sensor temperature outside 25–65 °C; neither monitor is a safety instrumented system. Individual scenarios include bias, drift, cold flow, cold inlet temperature, UA degradation and a mechanically stuck valve. Noise, persistent parameter mismatch and infeasible setpoint cases begin before 300 s and are explicitly marked as not injected at 300 s. `fault_active` in CSV indicates the time window at or after the configured fault time; it is not used as a detector input. A stuck valve near equilibrium was not detected by the example threshold: limited excitation makes this an important blind spot. Ten normal-noise seeds provide only a small illustrative false-alarm sample, not a statistical guarantee. No fault classification accuracy is claimed.

IAE, ISE and ITAE are trapezoidal integrals. Settling time is the first sample after the final departure from a band of 2% of the initial setpoint step (minimum 0.01 °C), within the finite horizon; no crossing returns null. Rise time is time to 90% of the step from the initial value. Overshoot is the largest directional deviation beyond target, in °C. Valve travel is total absolute command increments. The step-based rise and settling definitions are not suitable as general disturbance recovery metrics; compare IAE and final error for the regulatory study. Sample-based false-alarm fraction is not a rate of independent alarm events.
