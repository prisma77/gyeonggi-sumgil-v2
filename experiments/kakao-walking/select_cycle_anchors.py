"""Select at most five original cycle nodes by source-network shortcut loss."""
import heapq
import math
import time

from probe import meters
from source_route_evidence import safe_network


def select_cycle_anchors(source, nodes, maximum=5, time_limit=5, work_limit=1_000_000):
    if maximum not in (5,11) or len(nodes) < maximum+2 or nodes[0] != nodes[-1] or len(set(nodes[:-1])) != len(nodes)-1:
        raise ValueError('A simple original cycle and explicit five or two-request anchor budget required')
    coords, edges, ways = safe_network(source)
    if any(edge not in edges for edge in zip(nodes, nodes[1:])):
        raise ValueError('Eligible original directed cycle edges required')
    bridge = {n for w in ways.values() if w.get('tags',{}).get('bridge','no') != 'no' for n in w['nodes']}
    ground = [i for i,n in enumerate(nodes[:-1]) if n not in bridge]
    if len(ground) < maximum+1 or nodes[0] in bridge:
        raise ValueError('Six distinct original ground inputs required')
    # Bound the original-node pool; never interpolate request coordinates.
    pool = sorted(set([0]+[ground[i*len(ground)//min(64,len(ground))] for i in range(min(64,len(ground)))]+[len(nodes)-1]))
    cumulative = [0.0]
    for a,b in zip(nodes,nodes[1:]):
        cumulative.append(cumulative[-1]+meters(coords[a],coords[b]))
    adjacency = {}
    for a,b in edges:
        adjacency.setdefault(a,[]).append((b,meters(coords[a],coords[b])))
    deadline, work = time.monotonic()+time_limit, 0
    losses = {}
    for i,first in enumerate(pool[:-1]):
        wanted = {nodes[j] for j in pool[i+1:]}
        distances, queue = {nodes[first]:0.0}, [(0.0,nodes[first])]
        settled = {}
        while queue and wanted:
            work += 1
            if work > work_limit or time.monotonic() >= deadline:
                raise TimeoutError('Source anchor analysis limit reached')
            length,node = heapq.heappop(queue)
            if length != distances[node]:
                continue
            if node in wanted:
                settled[node] = length; wanted.remove(node)
            for nxt,edge_length in adjacency.get(node,[]):
                proposed = length+edge_length
                if proposed < distances.get(nxt,math.inf):
                    distances[nxt] = proposed; heapq.heappush(queue,(proposed,nxt))
        for j in range(i+1,len(pool)):
            if nodes[pool[j]] in settled:
                losses[i,j] = max(0,cumulative[pool[j]]-cumulative[first]-settled[nodes[pool[j]]])
    # Fixed return: minimize total lost source length, then worst leg.
    costs, previous = {(0,0):(0.0,0.0,0.0)}, {}
    for used in range(1,maximum+2):
        for end in range(used,len(pool)):
            if end == len(pool)-1 and used != maximum+1:
                continue
            for start in range(used-1,end):
                if (used-1,start) not in costs or (start,end) not in losses:
                    continue
                old = costs[used-1,start];loss = losses[start,end]
                cost = (old[0]+loss,max(old[1],loss),max(old[2],cumulative[pool[end]]-cumulative[pool[start]]))
                if cost < costs.get((used,end),(math.inf,math.inf,math.inf)):
                    costs[used,end],previous[used,end] = cost,start
    end,chosen = len(pool)-1,[]
    if (maximum+1,end) not in costs:
        raise ValueError('No bounded directed source anchor sequence')
    score = costs[maximum+1,end]
    for used in range(maximum+1,0,-1):
        chosen.append(pool[end]);end=previous[used,end]
    chosen = list(reversed(chosen))[:-1]
    return dict(indices=chosen,policy='MINIMUM_SOURCE_NETWORK_SHORTCUT_LOSS',maximum=maximum,
                source_shortcut_loss_m=round(score[0],1),max_leg_shortcut_loss_m=round(score[1],1),
                input_pool_size=len(pool)-1,work_count=work,
                scope='SOURCE_GRAPH_ONLY; ACTUAL_API_DISTANCE_AND_GEOMETRY_REQUIRE_CHECK')
