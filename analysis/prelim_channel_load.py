"""Preliminary analytical study: graph metrics and ideal saturation throughput.

For each (topology, routing function, traffic pattern) triple, computes the
per-channel load gamma_c and the ideal throughput bound
    theta* = b / max_c gamma_c          (Dally & Towles, 2004, Ch. 3)
with b = 1 flit/cycle per channel and injection capped at 1 flit/node/cycle.

Traffic patterns reproduce the destination functions in gem5's
src/cpu/testers/garnet_synthetic_traffic/GarnetSyntheticTraffic.cc.

Usage:
    pip install networkx numpy scipy
    python analysis/prelim_channel_load.py
"""

import itertools

import networkx as nx
import numpy as np

K = 8
N = K * K

PATTERNS = [
    "uniform_random",
    "transpose",
    "bit_complement",
    "tornado",
    "neighbor",
    "shuffle",
    "bit_reverse",
]


def coords(i):
    return i % K, i // K


def idx(x, y):
    return y * K + x


def traffic_matrix(name):
    """Row-stochastic N x N matrix, matching Garnet's generatePkt()."""
    T = np.zeros((N, N))
    nbits = int(np.log2(N))
    for s in range(N):
        x, y = coords(s)
        if name == "uniform_random":
            T[s, :] = 1.0 / N
            continue
        if name == "transpose":
            d = idx(y, x)
        elif name == "bit_complement":
            d = idx(K - x - 1, K - y - 1)
        elif name == "tornado":
            d = idx((x + K // 2 - 1) % K, y)
        elif name == "neighbor":
            d = idx((x + 1) % K, y)
        elif name == "shuffle":
            d = s * 2 if s < N // 2 else s * 2 - N + 1
        elif name == "bit_reverse":
            d = int(format(s, f"0{nbits}b")[::-1], 2)
        else:
            raise ValueError(name)
        T[s, d] = 1.0
    return T


def directed_mesh(periodic):
    G = nx.DiGraph()
    for i in range(N):
        x, y = coords(i)
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx_, ny = x + dx, y + dy
            if periodic:
                nx_, ny = nx_ % K, ny % K
            if 0 <= nx_ < K and 0 <= ny < K:
                G.add_edge(i, idx(nx_, ny))
    return G


def directed_ring():
    G = nx.DiGraph()
    for i in range(N):
        G.add_edge(i, (i + 1) % N)
        G.add_edge((i + 1) % N, i)
    return G


def directed_fbfly():
    G = nx.DiGraph()
    for i in range(N):
        x, y = coords(i)
        for x2 in range(K):
            if x2 != x:
                G.add_edge(i, idx(x2, y))
        for y2 in range(K):
            if y2 != y:
                G.add_edge(i, idx(x, y2))
    return G


# Each routing function returns {channel: fraction of the (s, d) flow}.


def path_split(paths):
    load = {}
    for p in paths:
        for a, b in zip(p, p[1:]):
            load[(a, b)] = load.get((a, b), 0.0) + 1.0 / len(paths)
    return load


def mesh_xy(s, d):
    (x, y), (dx, dy) = coords(s), coords(d)
    p = [s]
    while x != dx:
        x += 1 if dx > x else -1
        p.append(idx(x, y))
    while y != dy:
        y += 1 if dy > y else -1
        p.append(idx(x, y))
    return path_split([p])


def fbfly_dor(s, d):
    (x, y), (dx, dy) = coords(s), coords(d)
    p = [s]
    if x != dx:
        p.append(idx(dx, y))
    if y != dy:
        p.append(idx(dx, dy))
    return path_split([p])


def all_shortest_paths(G):
    """Uniform split over all minimal paths -- what betweenness centrality assumes."""
    return lambda s, d: path_split(list(nx.all_shortest_paths(G, s, d)))


def mesh_per_hop_random(s, d):
    """Uniform choice among productive ports at every hop.

    Approximates Garnet's table routing (lookupRoutingTable) when all link
    weights are equal.
    """
    sx, sy = coords(s)
    dx, dy = coords(d)
    order = sorted(range(N), key=lambda v: abs(coords(v)[0] - sx) + abs(coords(v)[1] - sy))
    flow, load = {s: 1.0}, {}
    for v in order:
        if v not in flow or v == d:
            continue
        x, y = coords(v)
        nxt = []
        if x != dx:
            nxt.append(idx(x + (1 if dx > x else -1), y))
        if y != dy:
            nxt.append(idx(x, y + (1 if dy > y else -1)))
        for n in nxt:
            share = flow[v] / len(nxt)
            load[(v, n)] = load.get((v, n), 0.0) + share
            flow[n] = flow.get(n, 0.0) + share
    return load


def ideal_throughput(T, route):
    gamma = {}
    for s, d in itertools.product(range(N), range(N)):
        if s == d or T[s, d] == 0:
            continue
        for ch, frac in route(s, d).items():
            gamma[ch] = gamma.get(ch, 0.0) + T[s, d] * frac
    return min(1.0, 1.0 / max(gamma.values())) if gamma else 1.0


def graph_metrics():
    undirected = {
        "Ring-64": nx.cycle_graph(N),
        "Mesh 8x8": nx.grid_2d_graph(K, K),
        "Torus 8x8": nx.grid_2d_graph(K, K, periodic=True),
        "Hypercube 6D": nx.hypercube_graph(6),
        "FlatButterfly 8x8": nx.Graph(directed_fbfly()),
    }
    print(f"{'topology':20s}{'links':>7s}{'degree':>9s}{'diam':>6s}{'ASPL':>7s}"
          f"{'lambda2':>9s}{'maxEB/meanEB':>14s}")
    for name, G in undirected.items():
        degs = [deg for _, deg in G.degree()]
        eb = list(nx.edge_betweenness_centrality(G, normalized=False).values())
        lam2 = sorted(nx.laplacian_spectrum(G))[1]
        print(f"{name:20s}{G.number_of_edges():7d}{f'{min(degs)}-{max(degs)}':>9s}"
              f"{nx.diameter(G):6d}{nx.average_shortest_path_length(G):7.2f}"
              f"{lam2:9.3f}{max(eb) / np.mean(eb):14.2f}")


def throughput_table():
    mesh, torus, ring = directed_mesh(False), directed_mesh(True), directed_ring()
    configs = [
        ("Ring-64, minimal", all_shortest_paths(ring)),
        ("Mesh, XY (DOR)", mesh_xy),
        ("Mesh, per-hop random min", mesh_per_hop_random),
        ("Mesh, all-min-paths split", all_shortest_paths(mesh)),
        ("Torus, minimal", all_shortest_paths(torus)),
        ("FlatButterfly, DOR", fbfly_dor),
    ]
    print("\nIdeal saturation throughput theta* (flits/node/cycle)")
    print(f"{'topology / routing':28s}" + "".join(f"{p[:10]:>11s}" for p in PATTERNS))
    for name, route in configs:
        row = [ideal_throughput(traffic_matrix(p), route) for p in PATTERNS]
        print(f"{name:28s}" + "".join(f"{v:11.3f}" for v in row))


if __name__ == "__main__":
    graph_metrics()
    throughput_table()
