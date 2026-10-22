from topologies.BaseTopology import SimpleTopology

from m5.objects import *
from m5.params import *

# 2D torus: Mesh_XY plus wraparound links in every row and column.
# Router i hosts cache i and directory i. X links have weight 1 and Y links
# weight 2 (same convention as Mesh_XY), so table routing resolves X first.
# No dateline VCs: the wraparound rings can deadlock near saturation.


class Torus(SimpleTopology):
    description = "Torus"

    def __init__(self, controllers):
        self.nodes = controllers

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        num_routers = options.num_cpus
        num_rows = options.mesh_rows
        assert num_rows > 0 and num_routers % num_rows == 0
        num_cols = num_routers // num_rows
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
                    int_node=routers[i % num_routers],
                    latency=link_latency,
                )
            )
            link_count += 1
        network.ext_links = ext_links

        def rid(row, col):
            return (row % num_rows) * num_cols + (col % num_cols)

        int_links = []

        def add(src, dst, out_dir, in_dir, weight):
            nonlocal link_count
            int_links.append(
                IntLink(
                    link_id=link_count,
                    src_node=routers[src],
                    dst_node=routers[dst],
                    src_outport=out_dir,
                    dst_inport=in_dir,
                    latency=link_latency,
                    weight=weight,
                )
            )
            link_count += 1

        for row in range(num_rows):
            for col in range(num_cols):
                here, east = rid(row, col), rid(row, col + 1)
                add(here, east, "East", "West", 1)
                add(east, here, "West", "East", 1)
        for row in range(num_rows):
            for col in range(num_cols):
                here, north = rid(row, col), rid(row + 1, col)
                add(here, north, "North", "South", 2)
                add(north, here, "South", "North", 2)

        network.int_links = int_links
