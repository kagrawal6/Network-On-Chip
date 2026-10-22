"""Milestone 1 preliminary results: graph predictions vs. gem5/Garnet.

Reads the injection sweep from scripts/sweep.py, computes graph-based
predictions for the same 16-core networks, and writes:
    results/saturation_summary.csv
    figures/prelim_results.png

Usage:
    python scripts/sweep.py --rates $(seq 0.025 0.025 0.8) --out results/prelim_fine.csv
    python analysis/prelim_results.py results/prelim_fine.csv
"""

import itertools
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
K = 4
N = K * K
MAX_RATE = 0.8

LABELS = {"Mesh_XY": "Mesh", "Torus": "Torus", "Ring": "Ring", "Tree": "Tree"}
COLORS = {"Mesh_XY": "#1f77b4", "Torus": "#2ca02c", "Ring": "#d62728", "Tree": "#9467bd"}
MARKERS = {"Mesh_XY": "s", "Torus": "D", "Ring": "o", "Tree": "^"}


def coords(i):
    return i % K, i // K


def idx(x, y):
    return y * K + x


def traffic_matrix(name):
    """Destination functions from GarnetSyntheticTraffic.cc."""
    T = np.zeros((N, N))
    for s in range(N):
        x, y = coords(s)
        if name == "uniform_random":
            T[s, :] = 1.0 / N
            continue
        d = {
            "transpose": idx(y, x),
            "bit_complement": idx(K - x - 1, K - y - 1),
            "tornado": idx((x + K // 2 - 1) % K, y),
            "neighbor": idx((x + 1) % K, y),
            "shuffle": s * 2 if s < N // 2 else s * 2 - N + 1,
            "bit_reverse": int(format(s, f"0{int(np.log2(N))}b")[::-1], 2),
            "bit_rotation": s // 2 if s % 2 == 0 else s // 2 + N // 2,
        }[name]
        T[s, d] = 1.0
    return T


def dimension_order_paths(s, d, wrap):
    """X then Y. On a torus take the shorter direction; split exact ties."""
    def legs(a, b):
        if a == b:
            return [[]]
        if not wrap:
            return [[1 if b > a else -1] * abs(b - a)]
        fwd, bwd = (b - a) % K, (a - b) % K
        if fwd != bwd:
            return [[1] * fwd] if fwd < bwd else [[-1] * bwd]
        return [[1] * fwd, [-1] * bwd]

    (x, y), (dx, dy) = coords(s), coords(d)
    paths = []
    for lx in legs(x, dx):
        for ly in legs(y, dy):
            p, cx, cy = [s], x, y
            for step in lx:
                cx = (cx + step) % K
                p.append(idx(cx, cy))
            for step in ly:
                cy = (cy + step) % K
                p.append(idx(cx, cy))
            paths.append(p)
    return paths


RING = nx.cycle_graph(N)
TREE = nx.balanced_tree(2, int(np.log2(N)))
TREE_LEAVES = list(range(N - 1, 2 * N - 1))

ROUTES = {
    "Mesh_XY": lambda s, d: dimension_order_paths(s, d, wrap=False),
    "Torus": lambda s, d: dimension_order_paths(s, d, wrap=True),
    "Ring": lambda s, d: list(nx.all_shortest_paths(RING, s, d)),
    "Tree": lambda s, d: list(nx.all_shortest_paths(TREE, TREE_LEAVES[s], TREE_LEAVES[d])),
}


def predicted_saturation(topology, pattern):
    """1 / (load on the busiest directed link), capped at 1 packet/core/cycle."""
    T, route = traffic_matrix(pattern), ROUTES[topology]
    load = {}
    for s, d in itertools.product(range(N), range(N)):
        if s == d or T[s, d] == 0:
            continue
        paths = route(s, d)
        for p in paths:
            for link in zip(p, p[1:]):
                load[link] = load.get(link, 0.0) + T[s, d] / len(paths)
    return min(1.0, 1.0 / max(load.values())) if load else 1.0


def summarize(df):
    rows = []
    for (topo, pat), g in df.groupby(["topology", "pattern"]):
        g = g.sort_values("rate")
        t0 = g["avg_latency"].iloc[0]
        unstable = g[(g["avg_latency"] > 3 * t0) | (g["throughput"] < 0.95 * g["rate"])]
        deadlock = g[g["throughput"] < 0.1 * g["rate"]]
        rows.append({
            "topology": topo,
            "pattern": pat,
            "avg_hops": g["avg_hops"].iloc[0],
            "zero_load_latency": t0,
            "predicted_saturation": predicted_saturation(topo, pat),
            "simulated_saturation": unstable["rate"].min() if len(unstable) else np.nan,
            "deadlock_rate": deadlock["rate"].min() if len(deadlock) else np.nan,
        })
    return pd.DataFrame(rows)


def main():
    csv = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "prelim_fine.csv"
    df = pd.read_csv(csv)
    s = summarize(df)
    s.to_csv(ROOT / "results" / "saturation_summary.csv", index=False)

    slope, intercept = np.polyfit(s["avg_hops"], s["zero_load_latency"], 1)
    fit = slope * s["avg_hops"] + intercept
    r2 = 1 - ((s["zero_load_latency"] - fit) ** 2).sum() / (
        (s["zero_load_latency"] - s["zero_load_latency"].mean()) ** 2).sum()

    FIG.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(19, 5.3))

    # (A) latency vs. load, uniform random
    ax = axes[0]
    for topo in LABELS:
        g = df[(df["topology"] == topo) & (df["pattern"] == "uniform_random")].sort_values("rate")
        ok = g[(g["avg_latency"] <= 60) & (g["throughput"] >= 0.5 * g["rate"])]
        ax.plot(ok["rate"], ok["avg_latency"], marker=MARKERS[topo], color=COLORS[topo],
                lw=2, ms=4, label=LABELS[topo])
    dl = s[(s["topology"] == "Ring") & (s["pattern"] == "uniform_random")]["deadlock_rate"].iloc[0]
    if not np.isnan(dl):
        ax.axvline(dl, color=COLORS["Ring"], ls=":", lw=1.5)
        ax.text(dl + 0.01, 52, "Ring\ndeadlocks", color=COLORS["Ring"], fontsize=10)
    ax.set_xlim(0, MAX_RATE)
    ax.set_ylim(0, 60)
    ax.set_xlabel("injection rate (packets / core / cycle)")
    ax.set_ylabel("average packet latency (cycles)")
    ax.set_title("A. Latency vs. load (uniform random traffic)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)

    # (B) zero-load latency vs. hop count
    ax = axes[1]
    for topo in LABELS:
        g = s[s["topology"] == topo]
        ax.scatter(g["avg_hops"], g["zero_load_latency"], marker=MARKERS[topo],
                   color=COLORS[topo], s=55, label=LABELS[topo], edgecolors="black", lw=0.5)
    xs = np.linspace(0.8, 8.2, 10)
    ax.plot(xs, slope * xs + intercept, "k--", lw=1)
    ax.text(0.9, 20.5, f"latency = {slope:.2f} x hops + {intercept:.1f}\n$R^2$ = {r2:.3f}",
            fontsize=11)
    ax.set_xlabel("average hops (graph shortest path)")
    ax.set_ylabel("low-load latency (cycles)")
    ax.set_title("B. Low load: latency is set by hop count")
    ax.grid(alpha=0.3)

    # (C) predicted vs. simulated saturation
    ax = axes[2]
    shown = s[s["predicted_saturation"] < MAX_RATE]
    for topo in LABELS:
        g = shown[shown["topology"] == topo]
        ax.scatter(g["predicted_saturation"], g["simulated_saturation"].fillna(MAX_RATE),
                   marker=MARKERS[topo], color=COLORS[topo], s=60, label=LABELS[topo],
                   edgecolors="black", lw=0.5)
    ax.plot([0, MAX_RATE], [0, MAX_RATE], "k--", lw=1)
    ax.text(0.03, 0.08, "prediction = simulation", rotation=40, fontsize=10, color="0.3")
    ax.legend(loc="upper left")
    ring_ur = s[(s["topology"] == "Ring") & (s["pattern"] == "uniform_random")].iloc[0]
    ax.annotate("Ring, uniform:\ndeadlock before\nbandwidth limit",
                (ring_ur["predicted_saturation"], ring_ur["simulated_saturation"]),
                xytext=(0.52, 0.12), fontsize=10, color=COLORS["Ring"],
                arrowprops=dict(arrowstyle="->", color=COLORS["Ring"]))
    ax.set_xlim(0, MAX_RATE)
    ax.set_ylim(0, MAX_RATE)
    ax.set_xlabel("predicted saturation = 1 / load on busiest link")
    ax.set_ylabel("simulated saturation (gem5)")
    ax.set_title("C. High load: the busiest link predicts saturation")
    ax.grid(alpha=0.3)

    fig.suptitle("Preliminary results: 4 topologies x 8 traffic patterns x 32 injection rates "
                 "= 1,024 gem5/Garnet simulations (16 cores, 1-flit packets)", fontsize=13, y=1.01)
    fig.tight_layout()
    out = FIG / "prelim_results.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"wrote {out}")
    print(f"zero-load fit: latency = {slope:.3f} * hops + {intercept:.2f}, R^2 = {r2:.4f}")
    err = shown.dropna(subset=["simulated_saturation"])
    err = err[~((err["topology"] == "Ring") & (err["pattern"] == "uniform_random"))]
    mape = (abs(err["simulated_saturation"] - err["predicted_saturation"])
            / err["predicted_saturation"]).mean()
    print(f"saturation prediction error (excluding the deadlock point): {100 * mape:.1f}% "
          f"over {len(err)} cases")
    for col in ["predicted_saturation", "simulated_saturation"]:
        print(col)
        print(s.pivot(index="topology", columns="pattern", values=col).round(3).to_string())


if __name__ == "__main__":
    main()
