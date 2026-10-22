from topologies.BaseTopology import SimpleTopology

from m5.objects import *
from m5.params import *

# Binary tree. num_cpus leaf routers (power of two) host the endpoints:
# leaf i holds cache i and directory i. Internal routers only forward.
# Router ids follow heap order: root = 0, children of k are 2k+1 and 2k+2,
# leaves are num_cpus-1 .. 2*num_cpus-2. Paths are unique, so routing is
# deadlock-free (no cycles).


class Tree(SimpleTopology):
    description = "Tree"

    def __init__(self, controllers):
        self.nodes = controllers

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        num_leaves = options.num_cpus
        assert num_leaves & (num_leaves - 1) == 0, "num_cpus must be 2^k"
        num_routers = 2 * num_leaves - 1
        first_leaf = num_leaves - 1
        link_latency = options.link_latency
        router_latency = options.router_latency

        routers = [
            Router(router_id=i, latency=router_latency)
            for i in range(num_routers)
        ]
        network.routers = routers

        link_count = 0
        ext_links = []
        for i, n in enumerate(self.nodes):
            ext_links.append(
                ExtLink(
                    link_id=link_count,
                    ext_node=n,
                    int_node=routers[first_leaf + (i % num_leaves)],
                    latency=link_latency,
                )
            )
            link_count += 1
        network.ext_links = ext_links

        int_links = []
        for child in range(1, num_routers):
            parent = (child - 1) // 2
            side = "Left" if child % 2 == 1 else "Right"
            for src, dst, out_dir, in_dir in [
                (child, parent, "Up", side),
                (parent, child, side, "Up"),
            ]:
                int_links.append(
                    IntLink(
                        link_id=link_count,
                        src_node=routers[src],
                        dst_node=routers[dst],
                        src_outport=out_dir,
                        dst_inport=in_dir,
                        latency=link_latency,
                        weight=1,
                    )
                )
                link_count += 1
        network.int_links = int_links
