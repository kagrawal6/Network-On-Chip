"""Run Garnet synthetic-traffic sweeps and collect results into a CSV.

Each run is one (topology, traffic pattern, injection rate) point. Our custom
topologies in topologies/ are symlinked into gem5/configs/topologies first.

Usage:
    python scripts/sweep.py --num-cpus 16 --out results/prelim_fine.csv
"""

import argparse
import csv
import itertools
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEM5 = ROOT / "gem5"
GEM5_BIN = GEM5 / "build" / "NULL" / "gem5.opt"
RUN_DIR = ROOT / "results" / "runs"

TOPOLOGIES = ["Mesh_XY", "Torus", "Ring", "Tree"]
GRID_TOPOLOGIES = {"Mesh_XY", "Torus"}
TICKS_PER_CYCLE = 1000  # 1 ps ticks, 1 GHz clocks
PATTERNS = [
    "uniform_random",
    "transpose",
    "bit_complement",
    "bit_reverse",
    "bit_rotation",
    "shuffle",
    "tornado",
    "neighbor",
]
RATES = [0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8]

STATS = {
    "avg_latency": "system.ruby.network.average_packet_latency",
    "avg_network_latency": "system.ruby.network.average_packet_network_latency",
    "avg_queueing_latency": "system.ruby.network.average_packet_queueing_latency",
    "avg_hops": "system.ruby.network.average_hops",
    "packets_injected": "system.ruby.network.packets_injected::total",
    "packets_received": "system.ruby.network.packets_received::total",
    "sim_ticks": "simTicks",
}


def link_topologies():
    for f in (ROOT / "topologies").glob("*.py"):
        dst = GEM5 / "configs" / "topologies" / f.name
        if not dst.exists():
            dst.symlink_to(f)


def parse_stats(path):
    out = {}
    text = path.read_text() if path.exists() else ""
    for key, stat in STATS.items():
        m = re.search(rf"^{re.escape(stat)}\s+(\S+)", text, re.MULTILINE)
        out[key] = float(m.group(1)) if m and m.group(1) != "nan" else None
    return out


def run_one(topology, pattern, rate, args):
    tag = f"{topology}_{pattern}_{rate:.3f}_n{args.num_cpus}"
    outdir = RUN_DIR / tag
    cmd = [
        str(GEM5_BIN),
        "-q",
        f"--outdir={outdir}",
        str(GEM5 / "configs" / "example" / "garnet_synth_traffic.py"),
        "--network=garnet",
        f"--num-cpus={args.num_cpus}",
        f"--num-dirs={args.num_cpus}",
        f"--topology={topology}",
        f"--mesh-rows={args.mesh_rows if topology in GRID_TOPOLOGIES else 0}",
        f"--synthetic={pattern}",
        f"--injectionrate={rate}",
        "--inj-vnet=0",
        # The tester stops when curTick() >= sim_cycles, so pass ticks.
        f"--sim-cycles={args.sim_cycles * TICKS_PER_CYCLE}",
        f"--vcs-per-vnet={args.vcs}",
        # Run tester and network on the same clock so that injection rate
        # and latency are both in network cycles.
        "--sys-clock=1GHz",
        "--ruby-clock=1GHz",
    ]
    row = {"topology": topology, "pattern": pattern, "rate": rate}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT,
                              timeout=args.timeout)
        returncode, stderr = proc.returncode, proc.stderr
    except subprocess.TimeoutExpired:
        returncode, stderr = -1, "timeout"
    row.update(parse_stats(outdir / "stats.txt"))
    row["status"] = "ok" if returncode == 0 else "fail"
    if returncode != 0:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "stderr.txt").write_text(stderr[-4000:])
    for key in ("avg_latency", "avg_network_latency", "avg_queueing_latency"):
        if row[key] is not None:
            row[key] /= TICKS_PER_CYCLE
    if row["packets_received"] and row["sim_ticks"]:
        cycles = row["sim_ticks"] / TICKS_PER_CYCLE
        row["throughput"] = row["packets_received"] / (args.num_cpus * cycles)
    else:
        row["throughput"] = None
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--num-cpus", type=int, default=16)
    p.add_argument("--mesh-rows", type=int, default=4)
    p.add_argument("--sim-cycles", type=int, default=20_000)
    p.add_argument("--vcs", type=int, default=4)
    p.add_argument("--timeout", type=int, default=600, help="seconds per run")
    p.add_argument("--jobs", type=int, default=os.cpu_count())
    p.add_argument("--topologies", nargs="+", default=TOPOLOGIES)
    p.add_argument("--patterns", nargs="+", default=PATTERNS)
    p.add_argument("--rates", nargs="+", type=float, default=RATES)
    p.add_argument("--out", default="results/prelim_fine.csv")
    args = p.parse_args()

    if not GEM5_BIN.exists():
        sys.exit(f"missing {GEM5_BIN}; build gem5 first")
    link_topologies()

    points = list(itertools.product(args.topologies, args.patterns, args.rates))
    rows = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_one, t, pat, r, args) for t, pat, r in points]
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            print(f"[{i}/{len(points)}] {rows[-1]['topology']} "
                  f"{rows[-1]['pattern']} {rows[-1]['rate']} "
                  f"lat={rows[-1]['avg_latency']} {rows[-1]['status']}",
                  flush=True)

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["topology"], r["pattern"], r["rate"]))
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
