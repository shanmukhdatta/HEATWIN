"""Local sampled closed-loop stability near a fixed unsaturated equilibrium."""

import numpy as np
from scipy.integrate import solve_ivp

from heatwin.core import PID, Parameters, equilibrium, rhs


def local_stability(gains, p=None, command=0.4, dt=1.0):
    """Linearize one exact plant interval and PID update by central differences.

    Tests local asymptotic stability only, with no saturation, disturbance or noise.
    Integral gain must be positive so the integral state is active.
    """
    p = Parameters() if p is None else p
    if len(gains) != 3 or gains[1] <= 0 or not 0 < command < 1 or dt <= 0:
        raise ValueError("requires PI/PID gains and an interior operating point")
    y0 = equilibrium(command, p)
    setpoint = y0[0]
    state0 = np.r_[y0, 0.0, y0[0], 0.0]

    def step(state):
        controller = PID(*gains, dt=dt, bias=command)
        controller.integral, controller.previous, controller.derivative = state[3:]
        output = controller.update(setpoint, state[0])
        sol = solve_ivp(
            lambda _, y: rhs(y, output, p), (0, dt), state[:3], rtol=1e-10, atol=1e-11
        )
        if not sol.success:
            raise RuntimeError("local stability integration failed")
        return np.r_[
            sol.y[:, -1],
            controller.integral,
            controller.previous,
            controller.derivative,
        ]

    eps = 1e-5
    jac = np.column_stack(
        [
            (step(state0 + np.eye(6)[i] * eps) - step(state0 - np.eye(6)[i] * eps))
            / (2 * eps)
            for i in range(6)
        ]
    )
    eigenvalues = np.linalg.eigvals(jac)
    radius = float(np.max(np.abs(eigenvalues)))
    return {
        "spectral_radius": radius,
        "stable": bool(radius < 1),
        "eigenvalues": [[float(z.real), float(z.imag)] for z in eigenvalues],
    }
