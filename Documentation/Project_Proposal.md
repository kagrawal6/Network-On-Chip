# From Graph Structure to Saturation: Predicting Network-on-Chip Performance from Topology, Routing, and Traffic

**Team:** Steve Cho (`stevecho`) · Kushal Agrawal (`kushalag`)
**Simulator:** gem5 / Garnet 3.0 (`Garnet_standalone`, pinned at gem5 `f5c5a6e390`, Sep 2026)
**Status:** Proposal (expands Milestone 0)

---

## 1. Abstract

On-chip interconnect is now a first-order limit on performance and energy in many-core CPUs, GPUs, and ML accelerators [1, 2, 4, 36]. Topology choices are often explained with coarse graph statistics such as diameter, degree, and bisection width. These statistics ignore two things that decide real performance: the **routing function** and the **traffic matrix**. We will build an end-to-end framework that:

1. defines each topology once and generates both a graph model and a runnable Garnet configuration from it;
2. predicts zero-load latency and saturation throughput analytically using **routing-aware channel load**, a generalization of edge-betweenness centrality;
3. validates those predictions against cycle-level Garnet simulation **per link**, not just on aggregate averages;
4. extends Garnet with the missing pieces: Ring, Torus, Tree/Fat-Tree, Flattened Butterfly, and express/small-world topologies; deadlock-free torus routing with dateline virtual channels; and GPU- and ML-style traffic patterns.

The deliverable has two parts. The first is a quantitative answer to *when and why graph structure predicts NoC performance, and when it does not*. The second is a reusable, open-source design-space-exploration (DSE) tool built on gem5.

---

## 2. Motivation and Industry Relevance

| System | NoC topology | Why it matters to us |
|---|---|---|
| Intel Polaris (80-core) [41], Tilera TILE64 [43], MIT Raw [42] | 2D mesh | Established the tiled-mesh paradigm we use as a baseline |
| Intel Knights Landing [44], Skylake-SP Xeon [45] | 2D mesh, replacing rings | Rings stopped scaling as core counts grew; we will quantify the crossover |
| AMD EPYC / Ryzen (Infinity Fabric) [46] | Hierarchical, chiplet-based | Intra-die and inter-die links have very different costs (heterogeneous links) |
| NVIDIA MCM-GPU [47], Simba [48], NVSwitch [52] | Multi-chip modules, switch fabrics | Traffic is *many-to-few-to-many* (SMs to memory partitions), not uniform [36] |
| Google TPU v4 [49] | 3D torus (system level) | Torus wraparound links and their deadlock-avoidance cost |
| Eyeriss v2 [50], MAERI [51] | Hierarchical mesh, tree-based fabrics | Accelerator dataflows produce multicast and reduction traffic |

Two trends make this question especially relevant now:

- **Disaggregation into chiplets.** Interposer topologies such as Kite [8], Butter Donut [39], and modular routing [40] mean architects now design *irregular, heterogeneous* graphs where the textbook intuitions for regular graphs no longer apply.
- **Specialized traffic.** GPU and ML traffic is highly non-uniform. Hotspots, collectives, and many-to-few patterns stress the worst-case channel, which averages such as mean hop count cannot capture [27, 36].

---

## 3. Research Questions and Hypotheses

**RQ1.** How much of measured NoC latency and throughput can pure graph metrics explain, and which metrics matter?
**RQ2.** Does adding the routing function to the graph model (routing-aware channel load) close the gap between graph analysis and cycle-level simulation?
**RQ3.** For realistic CPU, GPU, and ML traffic, which topology gives the best performance per unit cost (links, router radix, wire length), and how does that compare with what industry builds?

Each hypothesis below is falsifiable and tied to a specific experiment.

| ID | Hypothesis | Test |
|---|---|---|
| **H1** | Below about 10% load, average packet latency is linear in average hop count: \(T_0 \approx H_{avg}(t_r + t_w) + T_{ser}\), with \(R^2 > 0.95\) across all topologies | Low-load sweep, regression of `average_packet_network_latency` against average shortest path length |
| **H2** | Saturation throughput is predicted by \(\Theta^* = b/\gamma_{max}\) computed **under the routing function actually used**, within ±15% of the simulated value (after one constant microarchitecture efficiency factor). Plain bisection width and plain betweenness predict it noticeably worse | Injection sweeps; compare three predictors by mean absolute percentage error |
| **H3** | The busiest links in simulation (`int_link_utilization`) are the links with the highest routing-aware load. Plain betweenness ranks them correctly for minimal-adaptive routing but **not** for dimension-order routing | Per-link Spearman rank correlation |
| **H4** | Tree and Ring saturate first under uniform and permutation traffic because their max/mean betweenness is high (a root bottleneck) or their algebraic connectivity \(\lambda_2\) is low | Correlate \(\lambda_2\) and max/mean edge betweenness with \(\Theta_{sat}\) |
| **H5** | Torus roughly doubles mesh throughput under uniform traffic (twice the bisection), but splitting VCs into dateline classes for deadlock freedom takes back part of that gain at a fixed VC budget | Torus with 2×2 vs. 2×4 VCs, compared with a mesh at equal buffers |
| **H6** | The Flattened Butterfly wins on latency and throughput per node but loses on throughput per unit cost because of high router radix and long wires | Cost-normalized Pareto plot |
| **H7** | Topology barely matters for nearest-neighbor traffic (\(\Theta^* = 1\) everywhere) and matters most for adversarial permutations such as transpose and bit-complement | Throughput spread across topologies for each pattern |

---

## 4. Background and Related Work

**NoC foundations.** Dally and Towles argued for routing packets instead of wires [1], and Benini and De Micheli framed NoCs as a system-on-chip paradigm [2]. Our analytical tools come from Dally and Towles' textbook [3]: channel load, ideal throughput, and the zero-load latency model. Enright Jerger, Krishna, and Peh [4] give the modern on-chip treatment. Garnet [5] is the cycle-level NoC model inside gem5 [6, 7]. Garnet 3.0 added heterogeneous links and routers and network bridges, introduced with Kite [8]. BookSim 2 [9] is the standard alternative simulator that we will use for cross-validation in a stretch goal.

**Topologies.** We cover:

- the concentrated mesh [13];
- the flattened butterfly [10];
- express cubes / MECS [11];
- fat-trees [14];
- small-world NoCs with long-range links [18, 19];
- the low-diameter graphs used at datacenter scale: Dragonfly [15], Slim Fly [16], and Jellyfish [17];
- the recent Sparse Hamming Graph NoC [20].

**Routing and deadlock.** We draw on:

- channel-dependency graphs and dateline VCs [21];
- virtual-channel flow control [22];
- the turn model, which gives West-First routing [23];
- Duato's escape-channel theory [24];
- O1TURN [25] and Valiant load balancing [26] for worst-case throughput;
- worst-case traffic for oblivious routing [27];
- congestion-aware adaptive routing [28].

**Router microarchitecture.** Pipelined and speculative routers [29], Express Virtual Channels [12], and SMART [30] explain why per-hop router latency (\(t_r\)) is a design knob. Bufferless routing [64] is a contrasting design point.

**Graph theory.** We use:

- Brandes' betweenness algorithm [31];
- algebraic connectivity / Fiedler value [32];
- expander theory, which links the spectral gap to bottlenecks [33];
- multilevel graph partitioning for bisection width [62];
- NetworkX [61] for the implementation.

**Power, area, and RTL.** ORION 2.0 [34] and DSENT [35] give early-stage power and area estimates. OpenPiton [56], OpenSMART [57], Constellation [58], and Stanford's open-source router [59] are RTL references for our stretch goals. ASAP7 [60] is the predictive PDK we would use.

**Traffic and workloads.** We draw on:

- the many-to-few-to-many pattern of GPU memory traffic [36];
- trace-based NoC simulation with Netrace [37];
- memory-controller placement [38];
- ML collectives (ring all-reduce [55], ASTRA-sim [53]);
- accelerator dataflow modeling with SCALE-Sim [54].

**Our contribution relative to prior work.** Topology comparisons usually report either graph metrics or simulation results, rarely both, and almost never validate per link. Our work is to **bridge the two systematically**: we show where standard network-science metrics such as betweenness, \(\lambda_2\), and average shortest path length succeed or fail, and we fix the failures with a routing-aware formulation.

---

## 5. Current State of the Repository and What We Learned from the Code

**What exists:** a pinned gem5 submodule (`f5c5a6e390`, built as `build_opts/Garnet_standalone`), a macOS `clang++-sdk` wrapper that works around stale CommandLineTools libc++ headers, and the Milestone 0 write-up. Everything else is proposed below.

**What we found in gem5 that shapes the plan:**

1. **Topologies available upstream:** `Mesh_XY`, `Mesh_westfirst`, `MeshDirCorners_XY`, `CustomMesh`, `Crossbar`, `CrossbarGarnet`, `Pt2Pt`, `Cluster`. **There is no Ring, Torus, Tree, or Flattened Butterfly**, so we must implement them.
2. **Routing** (`src/mem/ruby/network/garnet/RoutingUnit.cc`):
   - `--routing-algorithm=0` uses table routing. It picks the minimum-*weight* output port and breaks ties **at random at every hop**. `Mesh_XY` gets XY routing only by giving X links weight 1 and Y links weight 2.
   - `--routing-algorithm=1` is hard-coded XY for meshes.
   - `outportComputeCustom()` is an **unimplemented `panic()` placeholder**. That is where our custom routing (torus dateline routing, O1TURN, West-First, adaptive) will go.
3. **VC allocation** (`OutputUnit::select_free_vc(vnet)`) always picks the first idle VC in the virtual network. A torus is deadlock-free only if VCs are split into classes at a dateline [21]. That split has to be added here and in `SwitchAllocator::vc_allocate()`.
4. **Traffic generator** (`src/cpu/testers/garnet_synthetic_traffic/GarnetSyntheticTraffic.cc`):
   - All patterns compute coordinates on a `radix = sqrt(num_dest)` grid, so they are only well-defined for **square, power-of-two node counts**. We will use N = 16 and N = 64.
   - On non-mesh topologies, "neighbor" and "tornado" are defined by **logical grid coordinates, not physical adjacency**. For example, "neighbor" 7→0 on a 64-node ring is 7 hops. We will make the logical-to-physical mapping explicit.
   - Tornado computes `ceil(radix/2)` with **integer division**, so it is wrong for odd radix. Possible small upstream fix.
   - The tester stops when `curTick() >= sim_cycles`. That compares **ticks (1 ps)** with a value named *cycles*, so in Week 1 we will confirm the real measured window from `simTicks`.
   - There is **no warm-up phase**, and statistics include cold-start transients. We will add `m5.stats.reset()` after warm-up in our own run script.
   - Injection is a Bernoulli process per node per cycle. Vnets 0 and 1 carry 1-flit packets and vnet 2 carries 5-flit packets.
5. **Statistics available** (in `m5out/stats.txt` under `system.ruby.network.`): `average_packet_latency` (split into `_network_` and `_queueing_`), `average_hops`, `packets_injected` / `packets_received` per vnet, flit-level equivalents, **per-link `int_link_utilization`**, and `avg_vc_load`. Per-link utilization is what makes the per-link validation in H3 possible.

### 5.1 Preliminary result: plain betweenness mispredicts the throughput of an XY-routed mesh

We computed exact graph metrics and ideal throughput bounds (\(\Theta^* = 1/\gamma_{max}\), in flits/node/cycle, capped at injection bandwidth 1.0) for 64-node networks. The traffic matrices exactly reproduce Garnet's destination functions. Reproduce with `python analysis/prelim_channel_load.py`.

**Graph metrics (N = 64):**

| Topology | Links | Degree | Diameter | ASPL | \(\lambda_2\) | max/mean edge betweenness |
|---|---:|---:|---:|---:|---:|---:|
| Ring | 64 | 2 | 32 | 16.25 | 0.010 | 1.00 |
| Mesh 8×8 | 112 | 2–4 | 14 | 5.33 | 0.152 | 1.78 |
| Torus 8×8 | 128 | 4 | 8 | 4.06 | 0.586 | 1.00 |
| Hypercube 6-D | 192 | 6 | 6 | 3.05 | 2.000 | 1.00 |
| Flattened Butterfly 8×8 | 448 | 14 | 2 | 1.78 | 8.000 | 1.00 |

**Ideal saturation throughput \(\Theta^*\):**

| Topology / routing | uniform | transpose | bit-compl. | tornado | neighbor | shuffle | bit-rev. |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ring, minimal | 0.125 | 0.100 | 0.062 | 0.333 | 1.000 | 0.062 | 0.100 |
| **Mesh, XY (dimension-order)** | **0.500** | 0.143 | **0.250** | 0.333 | 1.000 | 0.250 | 0.143 |
| Mesh, per-hop random minimal (approximates Garnet table routing with equal weights) | 0.397 | 0.344 | 0.134 | 0.333 | 1.000 | 0.308 | 0.269 |
| Mesh, all-minimal-paths split (**what betweenness assumes**) | **0.374** | 0.327 | **0.105** | 0.333 | 1.000 | 0.371 | 0.342 |
| Torus, minimal | 1.000 | 0.614 | 0.323 | 0.333 | 1.000 | 0.441 | 0.714 |
| Flattened Butterfly, dimension-order | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

**Takeaway.** The *same 8×8 mesh graph* gives bounds that differ by up to **2.4×** (bit-complement: 0.105 vs. 0.25) depending only on the routing function. Standard betweenness centrality assumes traffic is split evenly over all shortest paths. That understates XY throughput under uniform traffic by 25% and overstates it under transpose by 2.3×. This motivates RQ2 and is the central technical idea of the project: **the right graph metric for a NoC is betweenness computed under the actual routing function** (channel load, [3] Ch. 3).

---

## 6. Methodology

### 6.1 Topology suite

All topologies are defined in one spec format (YAML or JSON) listing routers, endpoints, links (with port directions, weights, latency, and width), and physical placement. One spec produces both a NetworkX graph (for analysis) and a Garnet topology (through a generic `FromGraph.py` topology class), so **the analyzed graph and the simulated network are the same object by construction**.

| Tier | Topologies | Owner |
|---|---|---|
| Core (must have) | Mesh 4×4 and 8×8 (XY, West-First), Ring 16/64, Torus 4×4 and 8×8, Binary Tree / Fat-Tree, Crossbar (ideal reference) | Split (see §8) |
| Extended | Concentrated Mesh (CMesh) [13], Flattened Butterfly [10], folded-torus physical layout, express mesh / small-world (random long links) [18] | Split |
| Stretch | Kite / Butter Donut chiplet topologies on heterogeneous Garnet links [8, 39], Sparse Hamming Graph [20], Slim Fly-style low-diameter graph [16] | Stretch |

### 6.2 Routing functions

| Routing | Topologies | Implementation |
|---|---|---|
| Table, weight-biased (Garnet default) | All | Topology weights |
| XY / dimension-order | Mesh, CMesh, Flattened Butterfly | Built in (`--routing-algorithm=1`) / weights |
| West-First turn model [23] | Mesh | Upstream `Mesh_westfirst` |
| Torus minimal + **dateline VCs** [21] | Ring, Torus | **New:** `outportComputeCustom()` + VC classes in `select_free_vc` |
| Up*/Down* or nearest-common-ancestor | Tree / Fat-Tree | Weights or custom |
| O1TURN [25], Valiant [26] | Mesh, Torus | **New** (O1TURN uses 2 VC classes) |
| Minimal adaptive (credit-based) [28] | Mesh | Stretch |

### 6.3 Traffic

- **Built-in Garnet patterns:** `uniform_random`, `transpose`, `bit_complement`, `bit_reverse`, `bit_rotation`, `shuffle`, `tornado`, `neighbor`.
- **New patterns** (added to `GarnetSyntheticTraffic.cc`):
  - `hotspot(p, set)`: a fraction *p* of traffic goes to a few nodes, for example memory controllers at the corners or along a diamond pattern [38].
  - `many_to_few`: compute nodes send to a small set of memory-partition nodes, modeling GPU traffic [36].
  - `ring_allreduce`: each node sends to its successor in a logical ring [55], to see whether the logical ring maps well onto the physical topology.
  - Explicit `node -> (x, y)` coordinate maps for non-mesh topologies.
- **Stretch:** Netrace PARSEC traces [37]; accelerator traffic from SCALE-Sim / ASTRA-sim [53, 54]; full-system Ruby MESI runs.

### 6.4 Graph metrics (structural features)

- Degree and radix
- Diameter
- Average shortest path length (ASPL) and its efficiency relative to the Moore bound
- Bisection width (exact for small graphs; METIS for larger [62])
- Edge and node betweenness [31]
- Algebraic connectivity \(\lambda_2\) and spectral gap [32, 33]
- Path diversity (number of minimal paths per pair)
- Link count and total wire length (Manhattan distance on the floorplan)
- **Routing-aware channel load** \(\gamma_c = \sum_{s,d} \lambda_{sd} \Pr[c \in R(s,d)]\)

### 6.5 Analytical performance model

- **Zero-load latency:** \(T_0 = H_{avg}\,(t_r + t_w) + \lceil L/b \rceil - 1 + T_{NI}\). Here \(t_r\) and \(t_w\) are `--router-latency` and `--link-latency`, \(L\) is packet size, \(b\) is link width (128 bits, so a 5-flit data packet), and \(T_{NI}\) is the network-interface overhead, fitted once.
- **Ideal throughput:** \(\Theta^* = b / \max_c \gamma_c\).
- **Realized throughput:** \(\Theta_{sat} \approx \eta \cdot \Theta^*\), where \(\eta\) captures allocator and flow-control inefficiency. We fit \(\eta\) once for the mesh and test whether it transfers to the other topologies.
- **Stretch:** an M/D/1-style queueing extension per channel, to predict the whole latency-vs-load curve rather than just its two endpoints.

### 6.6 Simulation protocol

Example run:

```bash
./build/NULL/gem5.opt configs/example/garnet_synth_traffic.py \
  --network=garnet --num-cpus=64 --num-dirs=64 \
  --topology=Mesh_XY --mesh-rows=8 --routing-algorithm=1 \
  --vcs-per-vnet=4 --link-width-bits=128 --router-latency=1 --link-latency=1 \
  --synthetic=uniform_random --inj-vnet=0 --injectionrate=0.05 \
  --sim-cycles=<calibrated>
```

| Parameter | Baseline | Sensitivity sweep |
|---|---|---|
| N | 64 (8×8) | 16 |
| VCs per vnet | 4 | 2, 8 |
| Router latency | 1 | 2, 3 (deeper pipeline) |
| Link width | 128 bits | 64, 256 |
| Packet size | 1 flit (vnet 0) | 5 flits (vnet 2), mixed |
| Warm-up / measure | 10k / 100k cycles (confirm tick semantics) | — |
| Seeds | 3 (5 for headline plots) | — |

- **Saturation point:** the lowest offered load at which average latency exceeds 3× \(T_0\), or accepted throughput falls below 95% of offered load [3]. We find it by **adaptive bisection on the injection rate**, which needs about 8 runs per curve instead of about 40.
- **Throughput accounting:** accepted throughput = `packets_received / (N × measured_cycles)`, broken down by vnet.
- **Scale estimate:** about 10 topologies × 10 patterns × 1.5 routings × about 15 load points × 3 seeds ≈ 7,000 short runs. That fits on a laptop or a cluster node in hours. We will confirm runtime per run in Week 1.
- **Reporting:** mean with 95% confidence intervals. Every figure is regenerated from raw `stats.txt` by one script.

### 6.7 Cost model

Throughput alone flatters high-radix topologies, so we report performance per unit cost:

- link count × width;
- total wire length from placement, with an optional repeater-energy model;
- router cost proxies: crossbar area \(\propto (p \cdot w)^2\) and buffer area \(\propto p \cdot v \cdot d \cdot w\);
- **stretch:** DSENT [35] or ORION 2.0 [34] numbers, or our own synthesized RTL (§9).

### 6.8 Validation

- **Analytical vs. simulation:** compare \(T_0\) with low-load latency, and \(\Theta^*\) with \(\Theta_{sat}\).
- **Per link:** Spearman ρ between predicted \(\gamma_c\) and measured `int_link_utilization` at 50% of saturation.
- **Sanity checks:** Crossbar as the ideal reference, `neighbor` traffic at \(\Theta^* = 1\), and a mesh/XY result that must match known Garnet results.
- **Stretch:** cross-simulator check against BookSim 2 [9].

---

## 7. Proposed Software Architecture

```
Network-On-Chip/
├── gem5/                      # submodule -> our fork, branch `noc-research`
│   ├── configs/topologies/    #   FromGraph.py, Ring.py, Torus.py, FatTree.py, FlatBfly.py
│   ├── configs/example/       #   noc_sweep_traffic.py (warm-up + stats reset)
│   └── src/.../garnet/        #   custom routing, dateline VCs, new traffic patterns
├── noc/                       # Python package (pip install -e .)
│   ├── spec.py                #   topology spec <-> NetworkX <-> Garnet JSON
│   ├── metrics.py             #   graph metrics
│   ├── analytic.py            #   channel load, T0, theta*
│   ├── stats.py               #   stats.txt -> tidy DataFrame (Parquet)
│   └── plots.py
├── specs/                     # *.yaml topology definitions
├── scripts/sweep.py           # parallel sweeps + adaptive saturation search
├── analysis/                  # notebooks + prelim_channel_load.py
├── results/                   # raw runs (gitignored); data/ holds summarized CSV/Parquet
└── Documentation/
```

**Engineering practices** (these are what reviewers notice):

- pinned gem5 fork;
- a one-command build;
- GitHub Actions CI that builds `gem5.opt` with ccache and runs a 4×4 mesh smoke test;
- unit tests that check the analytical model against closed-form results (for example, 8×8 mesh XY uniform = 0.5 and torus = 1.0, both reproduced above);
- deterministic seeds;
- every figure regenerated with one command.

---

## 8. Division of Labor

Ownership is split by **layer**: Steve owns the simulator and microarchitecture, Kushal owns modeling, analytics, and experiments. Each person also owns **one topology family end-to-end**, from spec through analysis to the write-up section, so both of us can tell a complete hardware story in interviews. All code changes go through PRs reviewed by the other person.

### Steve Cho: simulator and microarchitecture lead

| # | Work item | Concrete output |
|---|---|---|
| S1 | gem5 bring-up: `Garnet_standalone` build on macOS (with `clang++-sdk`) and Linux/Docker; ccache; CI smoke test | Reproducible `make gem5`, CI badge |
| S2 | Run-script hygiene: warm-up plus `m5.stats.reset()`, confirm `sim_cycles` tick semantics, seed control | `noc_sweep_traffic.py` |
| S3 | **Torus/Ring deadlock freedom:** dateline routing in `outportComputeCustom()` and VC-class partitioning in `OutputUnit::select_free_vc` / `SwitchAllocator::vc_allocate` | Deadlock-free torus up to saturation (no `garnet-deadlock-threshold` trips) |
| S4 | **New traffic patterns** in `GarnetSyntheticTraffic.cc`: hotspot, many-to-few, ring-allreduce, explicit coordinate maps; fix tornado for odd radix | Patterns plus unit checks of destination distributions |
| S5 | **O1TURN and Valiant routing** (mesh/torus) | Two routing modes selectable from the command line |
| S6 | **Topology family: direct/regular networks.** Ring, Torus (folded layout), Flattened Butterfly, Hypercube | Specs, Garnet configs, analysis section |
| S7 | Analysis of his family: when wraparound links and high radix pay off (H5, H6) | Report §, figures |

### Kushal Agrawal: modeling, analytics, and experiments lead

| # | Work item | Concrete output |
|---|---|---|
| K1 | **Topology spec and generator:** YAML to NetworkX and Garnet `FromGraph.py` (one source of truth); validate that generated `Mesh_XY` matches upstream results exactly | `noc/spec.py`, `FromGraph.py` |
| K2 | **Graph-metrics library:** ASPL, diameter, bisection (exact/METIS), betweenness, \(\lambda_2\), path diversity, wire length | `noc/metrics.py` with tests |
| K3 | **Analytical model:** routing-aware channel load for every routing function, \(T_0\), \(\Theta^*\); extend the preliminary script into a library | `noc/analytic.py` |
| K4 | **Sweep orchestration:** parallel runner, adaptive saturation search, `stats.txt` parser to Parquet, per-link utilization extraction | `scripts/sweep.py`, `noc/stats.py` |
| K5 | **Validation and statistics:** H1–H3 regressions, per-link Spearman ρ, confidence intervals, predictor comparison (bisection vs. betweenness vs. routing-aware) | Validation section, figures |
| K6 | **Topology family: mesh-derived and indirect networks.** Mesh (XY/West-First), CMesh, MeshDirCorners, express/small-world mesh, Binary Tree / Fat-Tree, Crossbar reference | Specs, analysis section |
| K7 | Cost model and Pareto analysis (perf/link, perf/wire, perf/router-area) | Pareto figure |

### Shared

- Write the hypotheses down before running experiments (pre-registration discipline).
- Weekly 30-minute sync plus asynchronous PR reviews.
- Final report, poster/slides, demo, and a cleaned-up public repo with README.
- Case-study section mapping our results to Intel's move from ring to mesh, AMD chiplets, NVIDIA MCM-GPU/Simba, and TPU tori.

---

## 9. Timeline (starting Mon Oct 19, 2026; adjust to course deadlines)

| Week | Dates | Steve | Kushal | Exit criterion |
|---|---|---|---|---|
| 1 | Oct 19 – 25 | S1 build + CI; reproduce 8×8 mesh UR curve | Set up `noc/` package; K2 metrics for the core suite | Both of us can run a sweep point; metrics table regenerated |
| 2 | Oct 26 – Nov 1 | S2 run script; start S3 (Ring first) | K1 spec → `FromGraph`; validate mesh equivalence | Generated mesh = upstream mesh, bit-for-bit statistics |
| 3 | Nov 2 – 8 | S3 Torus dateline VCs; S6 specs | K4 sweep runner + saturation search; K3 channel load for XY/table/minimal | First latency-vs-load curves for all core topologies |
| 4 | Nov 9 – 15 | S4 new traffic patterns | K6 CMesh/Tree/express specs; **H1, H2 first validation** | **Midpoint milestone:** core suite × built-in patterns done |
| 5 | Nov 16 – 22 | S5 O1TURN/Valiant; Flattened Butterfly | Full sweeps; K5 per-link validation (H3) | All core + extended runs complete |
| 6 | Nov 23 – 29 | S7 analysis (H5, H6) | K7 cost model + Pareto; H4, H7 | All hypotheses answered with figures |
| 7 | Nov 30 – Dec 6 | Report: simulator and direct-network sections | Report: modeling and validation sections | Draft report + poster |
| 8 | Dec 7 – 13 | Buffer, polish, public README, stretch | Buffer, polish, stretch | Final submission |

**Risks and mitigations**

- **gem5 build friction on macOS:** Docker/Linux fallback (S1).
- **Torus deadlocks before dateline routing is ready:** run below saturation with a high `--garnet-deadlock-threshold` as an interim measure, and flag it in results.
- **Sweep runtime:** adaptive saturation search, then reduce to N = 16 for the sensitivity sweeps.
- **Garnet traffic semantics on non-mesh topologies:** explicit coordinate maps (S4).

---

## 10. Stretch Goals (ordered by impact per effort)

1. **Upstream contribution to gem5.** Contribute the Ring/Torus/Fat-Tree topologies, the tornado fix, and the new traffic patterns as gem5 PRs. *"gem5 contributor"* is a strong, verifiable résumé line.
2. **RTL router and silicon-cost grounding.** Write a parameterized SystemVerilog input-queued VC router (route compute, VC allocation, switch allocation, crossbar; credit-based flow control), modeled on [29, 59]. Verify it with Verilator against Garnet-generated flit traces, and synthesize it with Yosys and OpenROAD on ASAP7 [60] or SKY130 for area, timing, and power versus radix and VC count. These numbers would replace the analytical cost model in §6.7, and they tie simulation to RTL and silicon, which is exactly the skill set NVIDIA and AMD interview for.
3. **Chiplet / heterogeneous NoC.** Use Garnet 3.0 heterogeneous links and `NetworkBridge` [8] to model 4 chiplets on an interposer (Kite, Butter Donut, mesh-of-meshes). Study how inter-die latency and width affect saturation, in the spirit of AMD's EPYC and NVIDIA's MCM-GPU.
4. **ML-accelerator traffic.** Generate traffic from DNN layer mappings (SCALE-Sim [54]) and collectives (ASTRA-sim [53]), and evaluate tree vs. mesh vs. torus for reduction-heavy traffic (MAERI [51], Eyeriss v2 [50]).
5. **Learned or optimized topology design.** Use the validated analytical model as a fast cost function to search for express-link placement (greedy, simulated annealing, or ILP) under a wire budget [18, 20]. Re-simulate the top candidates in Garnet. Result: "found an 8×8 topology with X% higher saturation than the mesh at the same wire budget."
6. **Predictive surrogate model.** Train a regressor (GBM or a small GNN) from graph and routing features to \(\Theta_{sat}\) and \(T_0\), using leave-one-topology-out cross-validation, and compare it with the analytical model.
7. **Adaptive routing.** Minimal-adaptive routing with Duato escape VCs [24] and regional congestion awareness [28], evaluated on adversarial permutations.
8. **Full-system validation.** Run PARSEC or Netrace traces [37] with Ruby MESI coherence to test whether conclusions from synthetic traffic hold for real coherence traffic.
9. **Cross-simulator check.** Compare saturation points from BookSim 2 [9] and Garnet on identical configurations.

---

## 11. Deliverables and Planned Figures

1. Latency-vs-offered-load curves: one panel per pattern, all topologies overlaid.
2. Predicted vs. simulated saturation throughput (scatter, y = x line, mean absolute percentage error for each of the three predictors). **This is the headline figure.**
3. Per-link heatmaps: predicted channel load next to measured `int_link_utilization` (8×8 mesh XY vs. table routing).
4. \(T_0\) vs. average hop count regression across all topologies (H1).
5. Graph metrics vs. \(\Theta_{sat}\): partial-correlation matrix showing which structural features matter.
6. Pareto frontier: throughput per link and per router area vs. latency.
7. Torus VC-partitioning cost (H5) and O1TURN/Valiant worst-case results.
8. Industry case-study table connecting each finding to a shipped design.

---

## 12. How This Maps to Hardware Roles (NVIDIA, AMD, Intel, Apple, Google)

| Role skill | Where we demonstrate it |
|---|---|
| Performance modeling / architecture simulation | gem5/Garnet C++ changes (routing, VC allocation, traffic), validated analytical models |
| Interconnect / NoC microarchitecture | Deadlock avoidance (dateline VCs, turn model), VC and switch allocation, flow control |
| Design-space exploration and methodology | Single-source spec, adaptive saturation search, confidence intervals, per-link validation |
| RTL / physical awareness (stretch) | SystemVerilog router, Verilator, Yosys/OpenROAD area and timing |
| Industry context | Case studies of Intel mesh, AMD Infinity Fabric chiplets, NVIDIA MCM-GPU / NVSwitch, TPU torus |

**Example résumé bullets (fill in the measured numbers):**

- *Extended gem5/Garnet (C++) with deadlock-free torus routing using dateline virtual-channel partitioning, plus O1TURN and Valiant routing, enabling evaluation of 10+ NoC topologies up to saturation.* (Steve)
- *Built a routing-aware analytical NoC model that predicts saturation throughput within X% of cycle-level simulation across N topologies × M traffic patterns, and showed that plain betweenness centrality mispredicts XY-mesh throughput by up to 2.4×.* (Kushal)
- *Designed a single-source topology DSE framework (spec to graph analysis to gem5 config to parallel sweeps), running about 7k simulations with per-link validation against Garnet link-utilization statistics.* (Kushal)
- *Implemented GPU- and ML-style traffic models (many-to-few, hotspot, ring all-reduce) in gem5 and quantified mesh vs. torus vs. flattened-butterfly trade-offs per unit wire and router cost.* (Steve)

---

## 13. References

[1] W. J. Dally and B. Towles, "Route Packets, Not Wires: On-Chip Interconnection Networks," *DAC*, 2001.
[2] L. Benini and G. De Micheli, "Networks on Chips: A New SoC Paradigm," *IEEE Computer*, 35(1), 2002.
[3] W. J. Dally and B. Towles, *Principles and Practices of Interconnection Networks*, Morgan Kaufmann, 2004.
[4] N. Enright Jerger, T. Krishna, and L.-S. Peh, *On-Chip Networks*, 2nd ed., Synthesis Lectures on Computer Architecture, Morgan & Claypool, 2017.
[5] N. Agarwal, T. Krishna, L.-S. Peh, and N. K. Jha, "GARNET: A Detailed On-Chip Network Model inside a Full-System Simulator," *ISPASS*, 2009.
[6] N. Binkert et al., "The gem5 Simulator," *ACM SIGARCH Computer Architecture News*, 39(2), 2011.
[7] J. Lowe-Power et al., "The gem5 Simulator: Version 20.0+," arXiv:2007.03152, 2020.
[8] S. Bharadwaj, J. Yin, B. Beckmann, and T. Krishna, "Kite: A Family of Heterogeneous Interposer Topologies Enabled via Accurate Interconnect Modeling," *DAC*, 2020.
[9] N. Jiang et al., "A Detailed and Flexible Cycle-Accurate Network-on-Chip Simulator," *ISPASS*, 2013.
[10] J. Kim, J. Balfour, and W. J. Dally, "Flattened Butterfly Topology for On-Chip Networks," *MICRO*, 2007.
[11] B. Grot, J. Hestness, S. W. Keckler, and O. Mutlu, "Express Cube Topologies for On-Chip Interconnects," *HPCA*, 2009.
[12] A. Kumar, L.-S. Peh, P. Kundu, and N. K. Jha, "Express Virtual Channels: Towards the Ideal Interconnection Fabric," *ISCA*, 2007.
[13] J. Balfour and W. J. Dally, "Design Tradeoffs for Tiled CMP On-Chip Networks," *ICS*, 2006.
[14] C. E. Leiserson, "Fat-Trees: Universal Networks for Hardware-Efficient Supercomputing," *IEEE Trans. Computers*, C-34(10), 1985.
[15] J. Kim, W. J. Dally, S. Scott, and D. Abts, "Technology-Driven, Highly-Scalable Dragonfly Topology," *ISCA*, 2008.
[16] M. Besta and T. Hoefler, "Slim Fly: A Cost Effective Low-Diameter Network Topology," *SC*, 2014.
[17] A. Singla, C.-Y. Hong, L. Popa, and P. B. Godfrey, "Jellyfish: Networking Data Centers Randomly," *NSDI*, 2012.
[18] U. Y. Ogras and R. Marculescu, "'It's a Small World After All': NoC Performance Optimization via Long-Range Link Insertion," *IEEE TVLSI*, 14(7), 2006.
[19] D. J. Watts and S. H. Strogatz, "Collective Dynamics of 'Small-World' Networks," *Nature*, 393, 1998.
[20] P. Iff, M. Besta, et al., "Sparse Hamming Graph: A Customizable Network-on-Chip Topology," *DAC*, 2023.
[21] W. J. Dally and C. L. Seitz, "Deadlock-Free Message Routing in Multiprocessor Interconnection Networks," *IEEE Trans. Computers*, C-36(5), 1987.
[22] W. J. Dally, "Virtual-Channel Flow Control," *IEEE TPDS*, 3(2), 1992.
[23] C. J. Glass and L. M. Ni, "The Turn Model for Adaptive Routing," *ISCA*, 1992.
[24] J. Duato, "A New Theory of Deadlock-Free Adaptive Routing in Wormhole Networks," *IEEE TPDS*, 4(12), 1993.
[25] D. Seo, A. Ali, W.-T. Lim, N. Rafique, and M. Thottethodi, "Near-Optimal Worst-Case Throughput Routing for Two-Dimensional Mesh Networks," *ISCA*, 2005.
[26] L. G. Valiant and G. J. Brebner, "Universal Schemes for Parallel Communication," *STOC*, 1981.
[27] B. Towles and W. J. Dally, "Worst-Case Traffic for Oblivious Routing Functions," *SPAA*, 2002.
[28] P. Gratz, B. Grot, and S. W. Keckler, "Regional Congestion Awareness for Load Balance in Networks-on-Chip," *HPCA*, 2008.
[29] L.-S. Peh and W. J. Dally, "A Delay Model and Speculative Architecture for Pipelined Routers," *HPCA*, 2001.
[30] T. Krishna, C.-H. O. Chen, W. C. Kwon, and L.-S. Peh, "Breaking the On-Chip Latency Barrier Using SMART," *HPCA*, 2013.
[31] U. Brandes, "A Faster Algorithm for Betweenness Centrality," *Journal of Mathematical Sociology*, 25(2), 2001.
[32] M. Fiedler, "Algebraic Connectivity of Graphs," *Czechoslovak Mathematical Journal*, 23(2), 1973.
[33] S. Hoory, N. Linial, and A. Wigderson, "Expander Graphs and Their Applications," *Bulletin of the AMS*, 43(4), 2006.
[34] A. B. Kahng, B. Li, L.-S. Peh, and K. Samadi, "ORION 2.0: A Fast and Accurate NoC Power and Area Model for Early-Stage Design Space Exploration," *DATE*, 2009.
[35] C. Sun et al., "DSENT – A Tool Connecting Emerging Photonics with Electronics for Opto-Electronic Networks-on-Chip Modeling," *NOCS*, 2012.
[36] A. Bakhoda, J. Kim, and T. M. Aamodt, "Throughput-Effective On-Chip Networks for Manycore Accelerators," *MICRO*, 2010.
[37] J. Hestness, B. Grot, and S. W. Keckler, "Netrace: Dependency-Driven Trace-Based Network-on-Chip Simulation," *NoCArc*, 2010.
[38] D. Abts, N. Enright Jerger, J. Kim, D. Gibson, and M. H. Lipasti, "Achieving Predictable Performance through Better Memory Controller Placement in Many-Core CMPs," *ISCA*, 2009.
[39] A. Kannan, N. Enright Jerger, and G. H. Loh, "Enabling Interposer-based Disintegration of Multi-core Processors," *MICRO*, 2015.
[40] J. Yin et al., "Modular Routing Design for Chiplet-based Systems," *ISCA*, 2018.
[41] Y. Hoskote, S. Vangal, A. Singh, N. Borkar, and S. Borkar, "A 5-GHz Mesh Interconnect for a Teraflops Processor," *IEEE Micro*, 27(5), 2007.
[42] M. B. Taylor et al., "The Raw Microprocessor: A Computational Fabric for Software Circuits and General-Purpose Programs," *IEEE Micro*, 22(2), 2002.
[43] D. Wentzlaff et al., "On-Chip Interconnection Architecture of the Tile Processor," *IEEE Micro*, 27(5), 2007.
[44] A. Sodani et al., "Knights Landing: Second-Generation Intel Xeon Phi Product," *IEEE Micro*, 36(2), 2016.
[45] S. M. Tam et al., "SkyLake-SP: A 14nm 28-Core Xeon Processor," *ISSCC*, 2018.
[46] S. Naffziger et al., "Pioneering Chiplet Technology and Design for the AMD EPYC and Ryzen Processor Families," *ISCA* (Industry Track), 2021.
[47] A. Arunkumar et al., "MCM-GPU: Multi-Chip-Module GPUs for Continued Performance Scalability," *ISCA*, 2017.
[48] Y. S. Shao et al., "Simba: Scaling Deep-Learning Inference with Multi-Chip-Module-Based Architecture," *MICRO*, 2019.
[49] N. P. Jouppi et al., "TPU v4: An Optically Reconfigurable Supercomputer for Machine Learning with Hardware Support for Embeddings," *ISCA*, 2023.
[50] Y.-H. Chen, T.-J. Yang, J. Emer, and V. Sze, "Eyeriss v2: A Flexible Accelerator for Emerging Deep Neural Networks on Mobile Devices," *IEEE JETCAS*, 9(2), 2019.
[51] H. Kwon, A. Samajdar, and T. Krishna, "MAERI: Enabling Flexible Dataflow Mapping over DNN Accelerators via Reconfigurable Interconnects," *ASPLOS*, 2018.
[52] A. Ishii and R. Wells, "The NVLink-Network Switch: NVIDIA's Switch Chip for High Communication-Bandwidth SuperPODs," *Hot Chips 34*, 2022.
[53] S. Rashidi, S. Sridharan, S. Srinivasan, and T. Krishna, "ASTRA-SIM: Enabling SW/HW Co-Design Exploration for Distributed DL Training Platforms," *ISPASS*, 2020.
[54] A. Samajdar et al., "A Systematic Methodology for Characterizing Scalability of DNN Accelerators using SCALE-Sim," *ISPASS*, 2020.
[55] P. Patarasuk and X. Yuan, "Bandwidth Optimal All-reduce Algorithms for Clusters of Workstations," *JPDC*, 69(2), 2009.
[56] J. Balkind et al., "OpenPiton: An Open Source Manycore Research Framework," *ASPLOS*, 2016.
[57] H. Kwon and T. Krishna, "OpenSMART: Single-Cycle Multi-hop NoC Generator in BSV and Chisel," *ISPASS*, 2017.
[58] J. Zhao, A. Agrawal, B. Nikolić, and K. Asanović, "Constellation: An Open-Source SoC-Capable NoC Generator," *NOCS*, 2022.
[59] D. U. Becker, "Efficient Microarchitecture for Network-on-Chip Routers," PhD thesis, Stanford University, 2012.
[60] L. T. Clark et al., "ASAP7: A 7-nm FinFET Predictive Process Design Kit," *Microelectronics Journal*, 53, 2016.
[61] A. Hagberg, D. Schult, and P. Swart, "Exploring Network Structure, Dynamics, and Function using NetworkX," *SciPy*, 2008.
[62] G. Karypis and V. Kumar, "A Fast and High Quality Multilevel Scheme for Partitioning Irregular Graphs," *SIAM J. Scientific Computing*, 20(1), 1998.
[63] gem5 documentation, "Garnet Synthetic Traffic," https://www.gem5.org/documentation/general_docs/ruby/garnet_synthetic_traffic/
[64] T. Moscibroda and O. Mutlu, "A Case for Bufferless Routing in On-Chip Networks," *ISCA*, 2009.
