# Project Proposal: Why Do Some Chip Networks Perform Better Than Others?

**Team:** Steve Cho (`stevecho`) and Kushal Agrawal (`kushalag`)
**Tool:** gem5 simulator with its Garnet network model
**Full title:** *From Graph Structure to Saturation: Predicting Network-on-Chip Performance from Topology, Routing, and Traffic*

---

## 1. The project in one paragraph

Modern chips (CPUs, GPUs, AI accelerators) contain dozens of cores that constantly send data to each other over a tiny on-chip network called a **Network-on-Chip (NoC)**. How you wire the cores together (the **topology**) strongly affects how fast the chip runs. People usually compare topologies using simple graph numbers such as "how many hops between the farthest two cores." **We will show that those numbers are not enough.** You also need to know **which path each message takes (routing)** and **who talks to whom (traffic)**. We will build a tool that predicts NoC performance from the graph *plus* the routing, check the predictions against a detailed cycle-by-cycle simulator (gem5/Garnet), and use it to explain real design choices made by Intel, AMD, NVIDIA, and Google.

---

## 2. Key terms (read this first)

| Term | Plain-English meaning |
|---|---|
| **Node / router** | A stop on the network. Each core plugs into a router. |
| **Link** | A wire between two routers. It can carry one packet piece (a **flit**) per clock cycle. |
| **Topology** | The shape of the wiring: Mesh (grid), Ring, Torus (grid with wrap-around edges), Tree, etc. |
| **Routing** | The rule that picks a path. **XY routing** = "go all the way left/right first, then up/down." |
| **Traffic pattern** | Who sends to whom. *Uniform random* = anyone to anyone. *Transpose* = core (x,y) sends to (y,x). |
| **Hop count** | Number of links a packet crosses. |
| **Latency** | How many cycles a packet takes to arrive. |
| **Injection rate** | How often each core sends a packet (for example 0.1 = once every 10 cycles). |
| **Saturation throughput** | The highest injection rate the network can handle before latency explodes. **This is the main number we compare.** |
| **Betweenness centrality** | A graph-theory score: how many shortest paths go through a link. A high score means a likely bottleneck. |
| **Virtual channel (VC)** | Separate lanes inside one link, used to avoid traffic jams and deadlock. |
| **Deadlock** | Packets wait on each other in a circle and nothing ever moves. Ring and torus networks are prone to this. |

---

## 3. The big idea, explained with a city analogy

Think of the chip as a **city**:

- **Topology** = the road map
- **Routing** = the GPS rule every driver follows
- **Traffic pattern** = where everyone is trying to go
- **Saturation** = gridlock

The city gridlocks when its **single busiest road** fills up. So to predict gridlock you need to know which road gets the most cars, and that depends on the map, the GPS rule, *and* the destinations.

Standard graph analysis (betweenness centrality) quietly assumes *drivers spread evenly over every shortest route*. Real chips do not do that. A mesh with XY routing sends everyone "horizontal first," which piles traffic onto different roads.

```
   Same road map  +  different GPS rule  =  different busiest road  =  different gridlock point
```

**Our project:** compute the busiest link using the *real* routing rule, predict when the network saturates, and then check that prediction in the simulator, link by link.

---

## 4. What we already found (preliminary result)

We wrote a short script (`analysis/prelim_channel_load.py`) that computes the best possible throughput for a 64-core mesh (8×8 grid). The **network wiring is identical** in every row; only the routing rule changes:

| Routing rule on the same 8×8 mesh | Uniform random traffic | Bit-complement traffic |
|---|---:|---:|
| XY routing (what real chips use) | **0.50** | **0.25** |
| Random choice at every hop (Garnet's default table routing) | 0.40 | 0.13 |
| "Spread evenly over all shortest paths" (**what betweenness assumes**) | 0.37 | 0.11 |

*(Units: packets per core per cycle. Higher is better.)*

**What this means:** the standard graph metric is off by **25%** on uniform traffic and by **2.4×** on bit-complement traffic. Graph analysis alone gives the wrong answer unless you include routing. That is the central claim of our project.

The same script also confirms the textbook numbers. For example, a torus handles **2×** the uniform traffic of a mesh, and a ring handles only **¼** of a mesh's.

---

## 5. Questions we will answer

| # | Question | What we expect |
|---|---|---|
| Q1 | At low traffic, is latency just "number of hops × time per hop"? | Yes, almost exactly |
| Q2 | Can we predict the saturation point from the graph **plus routing**? | Yes, within about 15% of the simulator; plain graph metrics will do worse |
| Q3 | Do the links we predict to be busiest actually turn out busiest in simulation? | Yes, with our method; plain betweenness fails for XY routing |
| Q4 | Which topology is best for each traffic pattern, and why? | Ring and Tree saturate first (bottlenecks); Torus beats Mesh; topology barely matters for neighbor traffic |
| Q5 | Which topology gives the best performance **per wire / per router cost**? | Mesh and Torus are strong value picks; Flattened Butterfly is fast but expensive |

---

## 6. What we will do, in four phases

**Phase 1 — Set up (Week 1–2).** Build gem5 and confirm we can reproduce a known result (a standard 8×8 mesh).

**Phase 2 — Build the topologies (Week 2–4).** gem5 only includes Mesh, Crossbar, and a few others. **We must add Ring, Torus, Tree, and Flattened Butterfly ourselves.** Each topology is described once in a simple file, and our tool generates both:
- the graph, for analysis in Python, and
- the gem5 configuration, for simulation.

This guarantees we analyze exactly what we simulate.

**Phase 3 — Predict and simulate (Week 3–5).**
- *Predict:* for each topology, routing rule, and traffic pattern, compute hop counts, busiest link, and expected saturation point.
- *Simulate:* run gem5 while slowly increasing the injection rate until the network saturates. Record latency, hops, and per-link usage.

**Phase 4 — Compare and explain (Week 5–7).** Plot predicted vs. simulated results, find where the predictions fail and why, compare cost, and connect each finding to a real chip.

### Topologies we will test

| Topology | Picture in words | Real-world example |
|---|---|---|
| Mesh | Grid; each router talks to up/down/left/right | Intel Xeon, Tilera, Intel's 80-core chip |
| Ring | Everyone in a circle | Older Intel CPUs |
| Torus | Grid with wrap-around edges | Google TPU pods |
| Tree / Fat-Tree | Hierarchy; traffic goes up and back down | Some AI accelerators |
| Flattened Butterfly | Every router linked to all others in its row and column | Research design, very fast |
| Crossbar | Everyone directly connected | "Ideal" reference point |

### Traffic patterns we will test

gem5 already provides 8 patterns (uniform random, transpose, tornado, bit-complement, bit-reverse, shuffle, neighbor, bit-rotation). **We will add 3 realistic ones:**
- **Hotspot:** many cores send to a few memory controllers.
- **Many-to-few:** GPU-style traffic, where compute cores talk to memory.
- **Ring all-reduce:** AI-training style, where each core passes data to the next.

### What we measure

Average latency (total, time waiting, time in the network), average hops, packets delivered, and **usage of every individual link**. gem5 reports all of these.

---

## 7. Who does what

The rule of thumb: **Steve owns the simulator (C++ inside gem5). Kushal owns the modeling and experiments (Python).** Each person also owns one family of topologies from start to finish, so both of us can present a complete story in interviews.

### Steve: simulator lead

| Task | Done when |
|---|---|
| 1. Build gem5 on Mac and Linux; add an automatic build check (CI) | One command builds gem5; a small mesh test passes automatically |
| 2. Improve the run script: add a warm-up period before measuring; confirm the simulation length is right | Results stop changing between repeated runs |
| 3. **Make Ring and Torus deadlock-free** (C++ changes in gem5's routing and virtual-channel code) | A Torus runs all the way to saturation without freezing |
| 4. **Add the 3 new traffic patterns** (hotspot, many-to-few, all-reduce) and fix the small tornado bug | New patterns selectable with `--synthetic=...` |
| 5. Add two routing rules that handle bad traffic better (O1TURN and Valiant) | Both selectable from the command line |
| 6. Own **Ring, Torus, Flattened Butterfly**: build them, run them, write their analysis | Report section with figures |

### Kushal: modeling and experiments lead

| Task | Done when |
|---|---|
| 1. **Topology generator:** one file per topology produces both the Python graph and the gem5 config | Our generated mesh gives the same gem5 results as gem5's built-in mesh |
| 2. **Graph metrics:** hops, diameter, bottleneck cut, betweenness, connectivity | Table of metrics for every topology |
| 3. **Prediction model:** busiest link under the real routing rule leads to the predicted saturation point | Matches textbook answers (mesh = 0.5, torus = 1.0) |
| 4. **Experiment runner:** runs many simulations in parallel and finds each saturation point automatically; turns gem5 output into a spreadsheet-style table | Full sweep runs with one command |
| 5. **Compare predictions to the simulator** (overall and link by link) | The "predicted vs. simulated" headline plot |
| 6. Own **Mesh variants, Tree, Crossbar**; build the cost comparison | Report section with figures |

### Together

Agree on predictions *before* running experiments, meet weekly for 30 minutes, review each other's code, and write the final report and slides together.

---

## 8. Week-by-week plan

| Week | Dates | Steve | Kushal | Checkpoint |
|---|---|---|---|---|
| 1 | Oct 19–25 | Build gem5, run a first mesh test | Set up Python package, graph metrics | Both of us can run one simulation |
| 2 | Oct 26–Nov 1 | Run script with warm-up; start Ring | Topology generator | Generated mesh matches built-in mesh |
| 3 | Nov 2–8 | Deadlock-free Torus | Experiment runner and prediction model | First latency curves for all basic topologies |
| 4 | Nov 9–15 | New traffic patterns | Tree / Mesh variants; first prediction check | **Midpoint:** all basic topologies × built-in traffic done |
| 5 | Nov 16–22 | New routing rules; Flattened Butterfly | Full experiment sweep; link-by-link check | All simulations finished |
| 6 | Nov 23–29 | Analyze his topologies | Cost comparison; analyze his topologies | Every question in §5 has an answer and a figure |
| 7 | Nov 30–Dec 6 | Write simulator sections | Write modeling sections | Draft report and slides |
| 8 | Dec 7–13 | Polish, public README, stretch goals | Polish, stretch goals | Final submission |

*(Shift dates to match your course deadlines.)*

**If something goes wrong:**

| Problem | Fallback |
|---|---|
| gem5 won't build on Mac | Use a Linux machine or Docker |
| Torus deadlocks before Steve's fix is ready | Only test below saturation for now and note it in the results |
| Simulations are too slow | Use 16 cores instead of 64 for the extra experiments |

---

## 9. Stretch goals (if time allows, best first)

| Stretch goal | What it is | Why recruiters care |
|---|---|---|
| **1. Contribute to gem5** | Submit our new topologies, traffic patterns, and bug fix to the official gem5 project | "gem5 contributor" is public and verifiable |
| **2. Build a real router in hardware code** | Write a router in SystemVerilog, test it, and get real chip area/timing using free tools (Verilator, Yosys, OpenROAD) | Shows RTL + physical design skills, which NVIDIA/AMD interview for |
| **3. Chiplets** | Model a chip split into 4 pieces connected through a base layer (like AMD EPYC, NVIDIA multi-chip GPUs) | The hottest topic in chip design right now |
| **4. AI accelerator traffic** | Generate traffic from real neural-network layers | Directly relevant to NVIDIA / Google TPU teams |
| **5. Automatically design a better topology** | Use our fast prediction model to search for where to add extra links | "We found a topology X% better than a mesh" |
| **6. Machine-learning predictor** | Train a model that predicts performance from graph features | Combines ML with hardware |
| **7. Smarter routing** | Routing that avoids congested links on the fly | Classic NoC research topic |
| **8. Real programs** | Use traces from real benchmark programs instead of synthetic traffic | Proves conclusions hold on real workloads |

---

## 10. How to present this (slides outline)

1. **The problem** (1 slide): chips are networks; wiring choice affects speed; show an Intel mesh and an AMD chiplet picture.
2. **The common shortcut and why it fails** (1 slide): the city analogy + the table from §4.
3. **Our approach** (1 slide): one topology file → graph prediction + gem5 simulation → compare.
4. **Results** (2–3 slides): latency curves; predicted vs. simulated plot; busiest-link heatmap; cost comparison.
5. **What it means for real chips** (1 slide): why Intel moved from rings to meshes, why TPUs use tori, why GPUs care about many-to-few traffic.
6. **What we built** (1 slide): gem5 extensions + open-source tool.

**30-second pitch for interviews:**
> "We studied why some on-chip network designs outperform others. We showed that the standard graph metric can be wrong by more than 2× because it ignores how packets are routed. We built a model that includes routing, validated it link-by-link against the gem5 simulator, and extended gem5 with new topologies, deadlock-free torus routing, and GPU/AI-style traffic."

**Example résumé bullets (fill in the final numbers):**
- *Steve:* "Extended the gem5/Garnet simulator (C++) with deadlock-free torus routing, O1TURN/Valiant routing, and GPU/AI traffic models, enabling evaluation of 10+ NoC topologies."
- *Kushal:* "Built a routing-aware NoC performance model that predicts saturation throughput within X% of cycle-accurate simulation, showing that standard betweenness centrality mispredicts mesh throughput by up to 2.4×."

---

## 11. Reading list

Papers are cited in this document by **author and year**. Each title below is a link to a Google Scholar search, so you can click through to the PDF.

### Start here (the 8 most important)

| Paper | Why read it |
|---|---|
| **Dally & Towles (2004)** — [*Principles and Practices of Interconnection Networks*](https://scholar.google.com/scholar?q=Principles+and+Practices+of+Interconnection+Networks+Dally+Towles) (book) | The textbook. Chapter 3 has the "busiest link → throughput" math we use |
| **Enright Jerger, Krishna & Peh (2017)** — [*On-Chip Networks*, 2nd ed.](https://scholar.google.com/scholar?q=On-Chip+Networks+Enright+Jerger+Krishna+Peh) (short book) | Best modern intro to NoCs |
| **Dally & Towles (2001)** — [Route Packets, Not Wires](https://scholar.google.com/scholar?q=%22Route+Packets%2C+Not+Wires%22) | The paper that started NoC research |
| **Agarwal et al. (2009)** — [GARNET: A Detailed On-Chip Network Model](https://scholar.google.com/scholar?q=GARNET+detailed+on-chip+network+model+full-system+simulator) | The simulator we use |
| **Bharadwaj et al. (2020)** — [Kite: Heterogeneous Interposer Topologies](https://scholar.google.com/scholar?q=Kite+family+of+heterogeneous+interposer+topologies) | Garnet 3.0 and chiplet topologies |
| **Kim, Balfour & Dally (2007)** — [Flattened Butterfly Topology for On-Chip Networks](https://scholar.google.com/scholar?q=Flattened+Butterfly+Topology+for+On-Chip+Networks) | Main "fast but expensive" topology we compare |
| **Dally & Seitz (1987)** — [Deadlock-Free Message Routing](https://scholar.google.com/scholar?q=Deadlock-Free+Message+Routing+in+Multiprocessor+Interconnection+Networks) | How to make Ring/Torus deadlock-free (Steve's task 3) |
| **Bakhoda, Kim & Aamodt (2010)** — [Throughput-Effective On-Chip Networks for Manycore Accelerators](https://scholar.google.com/scholar?q=Throughput-Effective+On-Chip+Networks+for+Manycore+Accelerators) | GPU traffic patterns (Steve's task 4) |

### Simulators and tools

- **Binkert et al. (2011)** — [The gem5 Simulator](https://scholar.google.com/scholar?q=%22The+gem5+simulator%22+Binkert)
- **Lowe-Power et al. (2020)** — [The gem5 Simulator: Version 20.0+](https://scholar.google.com/scholar?q=The+gem5+Simulator+Version+20.0%2B)
- **gem5 docs** — [Garnet Synthetic Traffic](https://www.gem5.org/documentation/general_docs/ruby/garnet_synthetic_traffic/)
- **Jiang et al. (2013)** — [BookSim 2: Cycle-Accurate NoC Simulator](https://scholar.google.com/scholar?q=A+Detailed+and+Flexible+Cycle-Accurate+Network-on-Chip+Simulator)
- **Hagberg, Schult & Swart (2008)** — [NetworkX](https://scholar.google.com/scholar?q=Exploring+Network+Structure+Dynamics+and+Function+using+NetworkX) (the Python graph library)
- **Hestness, Grot & Keckler (2010)** — [Netrace: Trace-Based NoC Simulation](https://scholar.google.com/scholar?q=Netrace+dependency-driven+trace-based+network-on-chip+simulation)

### Topologies

- **Benini & De Micheli (2002)** — [Networks on Chips: A New SoC Paradigm](https://scholar.google.com/scholar?q=Networks+on+Chips+A+New+SoC+Paradigm)
- **Balfour & Dally (2006)** — [Design Tradeoffs for Tiled CMP On-Chip Networks](https://scholar.google.com/scholar?q=Design+Tradeoffs+for+Tiled+CMP+On-Chip+Networks) (concentrated mesh)
- **Grot et al. (2009)** — [Express Cube Topologies for On-Chip Interconnects](https://scholar.google.com/scholar?q=Express+Cube+Topologies+for+On-Chip+Interconnects)
- **Leiserson (1985)** — [Fat-Trees](https://scholar.google.com/scholar?q=Fat-Trees+Universal+Networks+for+Hardware-Efficient+Supercomputing)
- **Ogras & Marculescu (2006)** — [It's a Small World After All: NoC Long-Range Links](https://scholar.google.com/scholar?q=It%27s+a+small+world+after+all+NoC+long-range+link+insertion)
- **Kim et al. (2008)** — [Dragonfly Topology](https://scholar.google.com/scholar?q=Technology-Driven+Highly-Scalable+Dragonfly+Topology)
- **Besta & Hoefler (2014)** — [Slim Fly](https://scholar.google.com/scholar?q=Slim+Fly+A+Cost+Effective+Low-Diameter+Network+Topology)
- **Iff et al. (2023)** — [Sparse Hamming Graph NoC](https://scholar.google.com/scholar?q=Sparse+Hamming+Graph+Customizable+Network-on-Chip+Topology)
- **Kannan, Enright Jerger & Loh (2015)** — [Interposer-Based Disintegration of Multi-Core Processors](https://scholar.google.com/scholar?q=Enabling+Interposer-based+Disintegration+of+Multi-core+Processors) (chiplets)

### Routing and router design

- **Dally (1992)** — [Virtual-Channel Flow Control](https://scholar.google.com/scholar?q=Virtual-Channel+Flow+Control+Dally)
- **Glass & Ni (1992)** — [The Turn Model for Adaptive Routing](https://scholar.google.com/scholar?q=The+Turn+Model+for+Adaptive+Routing) (West-First routing)
- **Duato (1993)** — [A New Theory of Deadlock-Free Adaptive Routing](https://scholar.google.com/scholar?q=A+New+Theory+of+Deadlock-Free+Adaptive+Routing+in+Wormhole+Networks)
- **Seo et al. (2005)** — [O1TURN: Near-Optimal Worst-Case Throughput Routing](https://scholar.google.com/scholar?q=Near-Optimal+Worst-Case+Throughput+Routing+for+Two-Dimensional+Mesh+Networks)
- **Valiant & Brebner (1981)** — [Universal Schemes for Parallel Communication](https://scholar.google.com/scholar?q=Universal+Schemes+for+Parallel+Communication+Valiant)
- **Towles & Dally (2002)** — [Worst-Case Traffic for Oblivious Routing](https://scholar.google.com/scholar?q=Worst-case+Traffic+for+Oblivious+Routing+Functions)
- **Gratz, Grot & Keckler (2008)** — [Regional Congestion Awareness](https://scholar.google.com/scholar?q=Regional+Congestion+Awareness+for+Load+Balance+in+Networks-on-Chip)
- **Peh & Dally (2001)** — [Pipelined Router Delay Model](https://scholar.google.com/scholar?q=A+Delay+Model+and+Speculative+Architecture+for+Pipelined+Routers)
- **Kumar et al. (2007)** — [Express Virtual Channels](https://scholar.google.com/scholar?q=Express+Virtual+Channels+Towards+the+Ideal+Interconnection+Fabric)
- **Krishna et al. (2013)** — [SMART: Breaking the On-Chip Latency Barrier](https://scholar.google.com/scholar?q=Breaking+the+On-Chip+Latency+Barrier+Using+SMART)
- **Moscibroda & Mutlu (2009)** — [Bufferless Routing in On-Chip Networks](https://scholar.google.com/scholar?q=A+Case+for+Bufferless+Routing+in+On-Chip+Networks)

### Graph theory

- **Brandes (2001)** — [A Faster Algorithm for Betweenness Centrality](https://scholar.google.com/scholar?q=A+Faster+Algorithm+for+Betweenness+Centrality)
- **Fiedler (1973)** — [Algebraic Connectivity of Graphs](https://scholar.google.com/scholar?q=Algebraic+Connectivity+of+Graphs+Fiedler)
- **Hoory, Linial & Wigderson (2006)** — [Expander Graphs and Their Applications](https://scholar.google.com/scholar?q=Expander+Graphs+and+Their+Applications)
- **Watts & Strogatz (1998)** — [Small-World Networks](https://scholar.google.com/scholar?q=Collective+Dynamics+of+Small-World+Networks)
- **Karypis & Kumar (1998)** — [METIS Graph Partitioning](https://scholar.google.com/scholar?q=A+Fast+and+High+Quality+Multilevel+Scheme+for+Partitioning+Irregular+Graphs)

### Real chips (for the "what industry does" slides)

- **Intel 80-core:** Hoskote et al. (2007) — [A 5-GHz Mesh Interconnect for a Teraflops Processor](https://scholar.google.com/scholar?q=A+5-GHz+Mesh+Interconnect+for+a+Teraflops+Processor)
- **MIT Raw:** Taylor et al. (2002) — [The Raw Microprocessor](https://scholar.google.com/scholar?q=The+Raw+Microprocessor+A+Computational+Fabric)
- **Tilera:** Wentzlaff et al. (2007) — [On-Chip Interconnection Architecture of the Tile Processor](https://scholar.google.com/scholar?q=On-Chip+Interconnection+Architecture+of+the+Tile+Processor)
- **Intel Xeon Phi:** Sodani et al. (2016) — [Knights Landing](https://scholar.google.com/scholar?q=Knights+Landing+Second-Generation+Intel+Xeon+Phi+Product)
- **Intel Xeon:** Tam et al. (2018) — [Skylake-SP: A 14nm 28-Core Xeon](https://scholar.google.com/scholar?q=SkyLake-SP+14nm+28-Core+Xeon+Processor)
- **AMD:** Naffziger et al. (2021) — [Chiplet Technology for AMD EPYC and Ryzen](https://scholar.google.com/scholar?q=Pioneering+Chiplet+Technology+and+Design+for+the+AMD+EPYC+and+Ryzen)
- **NVIDIA:** Arunkumar et al. (2017) — [MCM-GPU](https://scholar.google.com/scholar?q=MCM-GPU+Multi-Chip-Module+GPUs+for+Continued+Performance+Scalability)
- **NVIDIA:** Shao et al. (2019) — [Simba](https://scholar.google.com/scholar?q=Simba+Scaling+Deep-Learning+Inference+with+Multi-Chip-Module-Based+Architecture)
- **NVIDIA:** Ishii & Wells (2022) — [NVLink-Network Switch (Hot Chips)](https://scholar.google.com/scholar?q=NVLink-Network+Switch+NVIDIA+Hot+Chips)
- **Google:** Jouppi et al. (2023) — [TPU v4](https://scholar.google.com/scholar?q=TPU+v4+Optically+Reconfigurable+Supercomputer+for+Machine+Learning)
- **MIT Eyeriss:** Chen et al. (2019) — [Eyeriss v2](https://scholar.google.com/scholar?q=Eyeriss+v2+Flexible+Accelerator+for+Emerging+Deep+Neural+Networks)
- **Georgia Tech MAERI:** Kwon, Samajdar & Krishna (2018) — [MAERI](https://scholar.google.com/scholar?q=MAERI+Flexible+Dataflow+Mapping+over+DNN+Accelerators)
- **Memory controller placement:** Abts et al. (2009) — [Better Memory Controller Placement in Many-Core CMPs](https://scholar.google.com/scholar?q=Achieving+Predictable+Performance+through+Better+Memory+Controller+Placement)
- **Chiplet routing:** Yin et al. (2018) — [Modular Routing Design for Chiplet-based Systems](https://scholar.google.com/scholar?q=Modular+Routing+Design+for+Chiplet-based+Systems)

### AI workloads, power models, and hardware code (for stretch goals)

- **Rashidi et al. (2020)** — [ASTRA-sim](https://scholar.google.com/scholar?q=ASTRA-SIM+SW%2FHW+Co-Design+Distributed+DL+Training)
- **Samajdar et al. (2020)** — [SCALE-Sim](https://scholar.google.com/scholar?q=Systematic+Methodology+Characterizing+Scalability+DNN+Accelerators+SCALE-Sim)
- **Patarasuk & Yuan (2009)** — [Bandwidth Optimal All-reduce](https://scholar.google.com/scholar?q=Bandwidth+Optimal+All-reduce+Algorithms+for+Clusters+of+Workstations)
- **Kahng et al. (2009)** — [ORION 2.0 NoC Power/Area Model](https://scholar.google.com/scholar?q=ORION+2.0+Fast+Accurate+NoC+Power+Area+Model)
- **Sun et al. (2012)** — [DSENT](https://scholar.google.com/scholar?q=DSENT+Tool+Connecting+Emerging+Photonics+with+Electronics)
- **Balkind et al. (2016)** — [OpenPiton](https://scholar.google.com/scholar?q=OpenPiton+Open+Source+Manycore+Research+Framework)
- **Kwon & Krishna (2017)** — [OpenSMART NoC Generator](https://scholar.google.com/scholar?q=OpenSMART+Single-Cycle+Multi-hop+NoC+Generator)
- **Zhao et al. (2022)** — [Constellation NoC Generator](https://scholar.google.com/scholar?q=Constellation+Open-Source+SoC-Capable+NoC+Generator)
- **Becker (2012)** — [Efficient Microarchitecture for NoC Routers (PhD thesis)](https://scholar.google.com/scholar?q=Efficient+Microarchitecture+for+Network-on-Chip+Routers+Becker)
- **Clark et al. (2016)** — [ASAP7 7nm Predictive PDK](https://scholar.google.com/scholar?q=ASAP7+7-nm+FinFET+Predictive+Process+Design+Kit)

---

## Appendix A: Technical details (for when you start building)

### A.1 The two formulas we use

**Latency when the network is empty:**

> latency ≈ (average hops) × (router delay + wire delay) + (packet length in flits − 1) + small fixed overhead

**Maximum throughput:**

> max throughput = link bandwidth ÷ (traffic on the busiest link)

"Traffic on the busiest link" is computed by adding up, over every sender/receiver pair, how much of that pair's traffic the routing rule sends over each link (Dally & Towles 2004, Ch. 3). Real networks reach only part of this ideal, so we fit one efficiency factor on the mesh and test whether it holds for the other topologies.

### A.2 Example gem5 command

```bash
./build/NULL/gem5.opt configs/example/garnet_synth_traffic.py \
  --network=garnet --num-cpus=64 --num-dirs=64 \
  --topology=Mesh_XY --mesh-rows=8 --routing-algorithm=1 \
  --synthetic=uniform_random --injectionrate=0.05 --inj-vnet=0 \
  --sim-cycles=100000
```

Results appear in `m5out/stats.txt`. Look for `system.ruby.network.average_packet_latency`, `average_hops`, `packets_received`, and `int_link_utilization`.

### A.3 Settings we hold constant

| Setting | Main value | Also try |
|---|---|---|
| Number of cores | 64 (8×8) | 16 |
| Virtual channels | 4 | 2, 8 |
| Router delay | 1 cycle | 2, 3 |
| Link width | 128 bits | 64, 256 |
| Packet size | 1 flit | 5 flits |
| Repeats per data point | 3 (different random seeds) | 5 for final plots |

A network is "saturated" when latency exceeds 3× its empty-network latency.

### A.4 Things we found in the gem5 code

| Finding | Where | What it means for us |
|---|---|---|
| No Ring, Torus, Tree, or Flattened Butterfly | `gem5/configs/topologies/` | We write them (Steve: Ring/Torus/FB; Kushal: Tree/Mesh variants) |
| Custom routing function is an empty placeholder | `RoutingUnit.cc`, `outportComputeCustom()` | Where Steve adds torus and O1TURN routing |
| Virtual channel is always "first free one" | `OutputUnit.cc`, `select_free_vc()` | Steve must split VCs into two groups to prevent torus deadlock |
| Traffic patterns assume a square, power-of-2 core count | `GarnetSyntheticTraffic.cc` | Use 16 or 64 cores only |
| "Tornado" pattern is wrong when grid width is odd | same file | Small bug we can fix and send upstream |
| No warm-up before measuring | `garnet_synth_traffic.py` | Steve adds a warm-up period |
| `--sim-cycles` is compared to time in picoseconds, not cycles | same tester | Double-check run length in Week 1 |
| gem5 reports usage of every link | `GarnetNetwork.cc` | Lets us check predictions link by link |

### A.5 Proposed folder layout

```
Network-On-Chip/
├── gem5/            our gem5 copy (new topologies, routing, traffic patterns)
├── noc/             Python: topology files -> graphs, metrics, predictions, result parsing
├── specs/           one file per topology
├── scripts/         experiment runner
├── analysis/        notebooks and prelim_channel_load.py
├── results/         raw simulation output (not committed)
└── Documentation/
```
