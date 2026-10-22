"""Draw the four 16-core topologies, color links by edge betweenness, and
print their graph metrics.

Usage:
    python analysis/plot_networks.py      # writes figures/networks.png
"""

from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
K = 4
N = K * K


def mesh():
    G = nx.grid_2d_graph(K, K)
    G = nx.relabel_nodes(G, {(x, y): y * K + x for x, y in G})
    pos = {i: (i % K, i // K) for i in G}
    return G, pos, set(G)


def torus():
    G = nx.grid_2d_graph(K, K, periodic=True)
    G = nx.relabel_nodes(G, {(x, y): y * K + x for x, y in G})
    pos = {i: (i % K, i // K) for i in G}
    return G, pos, set(G)


def ring():
    G = nx.cycle_graph(N)
    ang = 2 * np.pi * np.arange(N) / N
    pos = {i: (np.cos(a), np.sin(a)) for i, a in enumerate(ang)}
    return G, pos, set(G)


def tree():
    G = nx.balanced_tree(2, int(np.log2(N)))
    pos = {}
    depth = int(np.log2(N))
    for v in G:
        level = int(np.floor(np.log2(v + 1)))
        idx = v - (2**level - 1)
        pos[v] = ((idx + 0.5) * 2 ** (depth - level), -level)
    leaves = {v for v in G if G.degree(v) == 1}
    return G, pos, leaves


TOPS = {"Mesh 4x4": mesh, "Torus 4x4": torus, "Ring 16": ring, "Binary Tree (16 leaves)": tree}


def metrics(G, endpoints):
    d = dict(nx.all_pairs_shortest_path_length(G))
    ep = sorted(endpoints)
    dists = [d[a][b] for a in ep for b in ep if a != b]
    eb = list(nx.edge_betweenness_centrality(G, normalized=False).values())
    return {
        "routers": G.number_of_nodes(),
        "links": G.number_of_edges(),
        "diameter": max(dists),
        "avg_hops": float(np.mean(dists)),
        "max_betweenness": max(eb),
        "lambda2": float(sorted(nx.laplacian_spectrum(G))[1]),
    }


def main():
    FIG.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 4, figsize=(20, 5),
                             gridspec_kw={"width_ratios": [1, 1, 1, 1.7]})
    print(f"{'topology':26s}{'routers':>8s}{'links':>7s}{'diam':>6s}"
          f"{'avg hops':>10s}{'max EB':>8s}{'lambda2':>9s}")
    for ax, (name, make) in zip(axes, TOPS.items()):
        G, pos, endpoints = make()
        m = metrics(G, endpoints)
        print(f"{name:26s}{m['routers']:8d}{m['links']:7d}{m['diameter']:6d}"
              f"{m['avg_hops']:10.2f}{m['max_betweenness']:8.0f}{m['lambda2']:9.3f}")
        eb = nx.edge_betweenness_centrality(G, normalized=True)
        edges = list(G.edges())
        colors = [eb[e] if e in eb else eb[e[::-1]] for e in edges]
        if name.startswith("Torus"):
            # draw wraparound links as arcs so they are visible
            straight = [e for e in edges if abs(pos[e[0]][0] - pos[e[1]][0]) + abs(pos[e[0]][1] - pos[e[1]][1]) == 1]
            wrap = [e for e in edges if e not in straight]
            ecol = {e: c for e, c in zip(edges, colors)}
            nx.draw_networkx_edges(G, pos, edgelist=straight, ax=ax, width=3,
                                   edge_color=[ecol[e] for e in straight],
                                   edge_cmap=plt.cm.plasma, edge_vmin=0, edge_vmax=0.6)
            nx.draw_networkx_edges(G, pos, edgelist=wrap, ax=ax, width=2,
                                   edge_color=[ecol[e] for e in wrap],
                                   edge_cmap=plt.cm.plasma, edge_vmin=0, edge_vmax=0.6,
                                   connectionstyle="arc3,rad=0.35", arrows=True,
                                   arrowstyle="-")
        else:
            nx.draw_networkx_edges(G, pos, ax=ax, width=3, edge_color=colors,
                                   edge_cmap=plt.cm.plasma, edge_vmin=0, edge_vmax=0.6)
        core = [v for v in G if v in endpoints]
        switch = [v for v in G if v not in endpoints]
        nx.draw_networkx_nodes(G, pos, nodelist=core, ax=ax, node_size=260,
                               node_color="#f28c28", edgecolors="black")
        nx.draw_networkx_nodes(G, pos, nodelist=switch, ax=ax, node_size=200,
                               node_color="#9db4c0", edgecolors="black", node_shape="s")
        ax.set_title(f"{name}\ndiameter {m['diameter']}, avg hops {m['avg_hops']:.2f}",
                     fontsize=13)
        ax.set_axis_off()
        if name.startswith("Ring"):
            ax.set_aspect("equal")
    sm = plt.cm.ScalarMappable(cmap=plt.cm.plasma, norm=plt.Normalize(0, 0.6))
    cbar = fig.colorbar(sm, ax=axes, fraction=0.015, pad=0.01)
    cbar.set_label("edge betweenness (normalized)")
    fig.suptitle("16-core NoC topologies as graphs  (orange = router with a core, grey square = switch-only router)",
                 fontsize=14, y=1.08)
    out = FIG / "networks.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
