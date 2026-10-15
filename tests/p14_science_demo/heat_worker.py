"""External scientific capability: finite-difference solver + parameter inversion.

Runs as a separate process. Usage:
  heat_worker.py <method> [--step S] [--iters N] [--hang SECONDS]
Writes result.json into the current directory (the isolated execution root).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heat_data as hd  # noqa: E402

NX = 41
DT = 0.002


def fd_solve(alpha: float) -> list[float]:
    """Explicit FTCS scheme; returns u at the sensor positions at T_OBS."""
    dx = math.pi / (NX - 1)
    r = alpha * DT / dx ** 2
    if r > 0.5:
        raise ValueError(f"unstable scheme: r={r:.3f}")
    u = [math.sin(i * dx) for i in range(NX)]
    for _ in range(round(hd.T_OBS / DT)):
        nxt = u[:]
        for i in range(1, NX - 1):
            nxt[i] = u[i] + r * (u[i + 1] - 2 * u[i] + u[i - 1])
        u = nxt
    out = []
    for x in hd.sensor_positions():
        pos = x / dx
        i = min(int(pos), NX - 2)
        w = pos - i
        out.append(u[i] * (1 - w) + u[i + 1] * w)
    return out


def sse(alpha: float, readings: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(fd_solve(alpha), readings))


def grid_search(readings: list[float], step: float) -> float:
    n = round((1.0 - 0.05) / step)
    candidates = [0.05 + k * step for k in range(n + 1)]
    return min(candidates, key=lambda a: sse(a, readings))


def golden_section(readings: list[float], iters: int) -> float:
    lo, hi = 0.05, 1.0
    g = (math.sqrt(5) - 1) / 2
    c, d = hi - g * (hi - lo), lo + g * (hi - lo)
    fc, fd = sse(c, readings), sse(d, readings)
    for _ in range(iters):
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - g * (hi - lo)
            fc = sse(c, readings)
        else:
            lo, c, fc = c, d, fd
            d = lo + g * (hi - lo)
            fd = sse(d, readings)
    return (lo + hi) / 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("method", choices=["grid", "golden", "stall"])
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--hang", type=float, default=60.0)
    args = ap.parse_args()
    if args.method == "stall":
        time.sleep(args.hang)
        return 0
    readings = hd.observations()
    started = time.perf_counter()
    if args.method == "grid":
        alpha = grid_search(readings, args.step)
        params = {"step": args.step}
    else:
        alpha = golden_section(readings, args.iters)
        params = {"iters": args.iters}
    result = {
        "method": args.method, "params": params, "alpha_fit": alpha,
        "sse_fd": sse(alpha, readings), "readings": readings,
        "solver": {"scheme": "FTCS", "nx": NX, "dt": DT, "t_obs": hd.T_OBS},
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    Path("result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{args.method}: alpha_fit={alpha:.5f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
