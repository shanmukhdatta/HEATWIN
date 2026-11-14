# HEATWIN implementation and verification checklist

The laboratory is a simulated educational prototype. Items marked incomplete are not represented as completed by the existing UI or automated checks.

- [x] Existing Python heat balances, sampled P/PI/PID, identification, tuning, twin and fault studies preserved.
- [x] FastAPI trajectory interface uses the Python simulation and a separately fitted twin; API tests cover validation, comparison and fault timing.
- [x] React/TypeScript/Vite frontend with React Three Fiber, Drei, illustrative exchanger, tubes, baffles, source, pump, valve and sensors.
- [x] Orbit, zoom, pan, camera reset/focus, cutaway and exploded end caps; animated illustrative particles and sensors follow the replay time and Python samples.
- [x] Configuration, manual/automatic replay, setpoint, gains, comparison, fault selection, timeline, pause, reset, playback speed and CSV export.
- [x] Comparison metrics, twin/residual charts, alarm indication and nine explanatory guided steps.
- [ ] Live edits to an already-running solver without a restart; two simultaneous 3D twin views; automatic guided camera choreography. The loop highlight follows the replay clock and focus/reset interpolate the camera.
- [ ] Full scientific or industrial validation: no physical data, no CFD, no boiler/pump dynamics; the included stuck valve can evade the residual alarm.
- [x] A clean source snapshot installed both locked dependency sets and passed 34 Python tests, two frontend unit tests, lint/format, production build, three browser tests and both experiment scripts; numerical summaries matched. Subsequent custom-initial-state, manual-valve and temperature-limit cases bring the local Python suite to 37 tests.
- [x] A clean clone of the implementation passed locked installation, formatting, build, 35 Python tests and all three browser tests. Subsequent manual-valve and temperature-limit regression tests bring the local Python suite to 37.
- [x] Remote delivery verified by comparing local HEAD with `git ls-remote`; repeat for any subsequent commit.

Detailed mathematical assumptions and previous experiment results are in `docs/engineering.md` and `results/studies/summary.json`. The older `IMPLEMENTATION_PLAN.md` is a historical roadmap, not a completion record.
