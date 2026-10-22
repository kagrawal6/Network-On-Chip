from topologies.BaseTopology import SimpleTopology

from m5.objects import *
from m5.params import *

# Bidirectional ring of num_cpus routers. Router i hosts cache i and directory i.
# All links have weight 1, so table routing takes the shortest direction
# (ties at distance N/2 are broken randomly per hop).
# No dateline VCs: the ring has cyclic channel dependencies and can deadlock
# near saturation.


class Ring(SimpleTopology):
    description = "Ring"

    def __init__(self, controllers):
        self.nodes = controllers

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        num_routers = options.num_cpus
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

        int_links = []
        for i in range(num_routers):
            nxt = (i + 1) % num_routers
            for src, dst, out_dir, in_dir in [
                (i, nxt, "CW", "CCW"),
                (nxt, i, "CCW", "CW"),
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
