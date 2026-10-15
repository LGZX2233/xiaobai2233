"""1-D heat conduction inverse problem: shared data definition.

u_t = alpha * u_xx on [0, pi], u(0,t)=u(pi,t)=0, u(x,0)=sin(x).
Exact solution: u(x,t) = exp(-alpha*t) * sin(x). Sensors record u at t=T with
fixed-seed Gaussian noise. The goal is to recover alpha from the readings.
"""
from __future__ import annotations

import math
import random

ALPHA_TRUE = 0.37
T_OBS = 0.5
NOISE_SIGMA = 0.005
NOISE_SEED = 20261013
SENSOR_COUNT = 9
REL_TOLERANCE = 0.05


def analytic(x: float, t: float, alpha: float) -> float:
    return math.exp(-alpha * t) * math.sin(x)


def sensor_positions() -> list[float]:
    return [k * math.pi / (SENSOR_COUNT + 1) for k in range(1, SENSOR_COUNT + 1)]


def observations() -> list[float]:
    rng = random.Random(NOISE_SEED)
    return [analytic(x, T_OBS, ALPHA_TRUE) + rng.gauss(0.0, NOISE_SIGMA)
            for x in sensor_positions()]


def sse_analytic(alpha: float, readings: list[float]) -> float:
    return sum((analytic(x, T_OBS, alpha) - y) ** 2
               for x, y in zip(sensor_positions(), readings))
