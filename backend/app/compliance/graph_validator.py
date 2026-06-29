from typing import Dict, Any, List, Tuple

def validate_and_repair_graph(params: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Analyzes the extracted Adjacency Graph for architectural violations (privacy, sanitation).
    Repairs the graph by injecting corridors where necessary.
    Returns the mutated params dictionary and a list of repair notes for the user.
    """
    if "graph" not in params or not params["graph"]:
        return params, []

    graph = params["graph"]
    rooms = graph.get("rooms", [])
    connections = graph.get("connections", [])
    room_counts = params.get("rooms", {})

    issues_fixed = []
    
    # Map of room ID to room type for quick lookup
    room_types = {r["id"]: r["room_type"] for r in rooms}
    
    new_connections = []
    connections_to_remove = []
    corridors_added = 0
    
    # Identify violations
    for idx, conn in enumerate(connections):
        ra_id = conn["room_a"]
        rb_id = conn["room_b"]
        
        type_a = room_types.get(ra_id)
        type_b = room_types.get(rb_id)
        
        if not type_a or not type_b:
            continue
            
        types_set = {type_a, type_b}
        is_bed = any("bedroom" in t.lower() for t in types_set)
        is_bath = any("bathroom" in t.lower() for t in types_set)
        is_living = any("living" in t.lower() for t in types_set)
        is_kitchen = any("kitchen" in t.lower() for t in types_set)
        
        is_privacy_violation = is_bed and (is_kitchen or is_living)
        is_sanitation_violation = is_bath and (is_kitchen or is_living)
        
        if is_privacy_violation or is_sanitation_violation:
            # We must break this connection and route through a central corridor
            connections_to_remove.append(idx)
            
            # Find an existing corridor
            existing_corridor_id = None
            for r in rooms:
                if "corridor" in r.get("room_type", "").lower():
                    existing_corridor_id = r["id"]
                    break
                    
            if existing_corridor_id:
                corridor_id = existing_corridor_id
            else:
                corridor_id = "inserted_central_corridor"
                if corridors_added == 0:
                    # Add central corridor room only once
                    rooms.append({"id": corridor_id, "room_type": "corridors"})
                    room_types[corridor_id] = "corridors"
                    room_counts["corridors"] = room_counts.get("corridors", 0) + 1
                    corridors_added += 1
            
            # Ensure the two rooms are connected to the central corridor
            # Check if connection already exists to prevent duplicates
            has_ra_conn = any(c['room_a'] == ra_id and c['room_b'] == corridor_id or c['room_a'] == corridor_id and c['room_b'] == ra_id for c in new_connections)
            has_rb_conn = any(c['room_a'] == rb_id and c['room_b'] == corridor_id or c['room_a'] == corridor_id and c['room_b'] == rb_id for c in new_connections)
            
            if not has_ra_conn:
                new_connections.append({
                    "room_a": ra_id,
                    "room_b": corridor_id,
                    "weight": conn.get("weight", 5)
                })
            if not has_rb_conn:
                new_connections.append({
                    "room_a": corridor_id,
                    "room_b": rb_id,
                    "weight": conn.get("weight", 5)
                })
            
            # Log the fix
            if is_privacy_violation:
                issues_fixed.append(f"AI Privacy Fix: A bedroom was directly connected to a living area. Routed through central hallway ({corridor_id}) to act as a privacy buffer.")
            elif is_sanitation_violation:
                issues_fixed.append(f"AI Sanitation Fix: A bathroom was directly connected to a living area/kitchen. Routed through central hallway ({corridor_id}) to act as a buffer.")

    if connections_to_remove:
        # Rebuild connections list without the removed ones, and add the new ones
        final_connections = [c for i, c in enumerate(connections) if i not in connections_to_remove]
        final_connections.extend(new_connections)
        graph["connections"] = final_connections
    else:
        final_connections = connections

    # Prune unnecessary corridors (degree < 2)
    changed = True
    while changed:
        changed = False
        degree_map = {}
        for conn in final_connections:
            ra, rb = conn["room_a"], conn["room_b"]
            degree_map[ra] = degree_map.get(ra, 0) + 1
            degree_map[rb] = degree_map.get(rb, 0) + 1
            
        useless_corridors = [r["id"] for r in rooms if "corridor" in r.get("room_type", "").lower() and degree_map.get(r["id"], 0) < 2]
        
        if useless_corridors:
            changed = True
            rooms = [r for r in rooms if r["id"] not in useless_corridors]
            final_connections = [c for c in final_connections if c["room_a"] not in useless_corridors and c["room_b"] not in useless_corridors]
            for c in useless_corridors:
                room_counts["corridors"] = max(0, room_counts.get("corridors", 0) - 1)
                issues_fixed.append(f"AI Connectivity Fix: Pruned unnecessary dead-end corridor ({c}).")

    # Ensure graph is fully connected
    adj = {r["id"]: [] for r in rooms}
    for conn in final_connections:
        adj[conn["room_a"]].append(conn["room_b"])
        adj[conn["room_b"]].append(conn["room_a"])
        
    visited = set()
    def dfs(node):
        visited.add(node)
        for neighbor in adj[node]:
            if neighbor not in visited:
                dfs(neighbor)
                
    components = []
    unvisited = set(adj.keys())
    while unvisited:
        start = unvisited.pop()
        visited.clear()
        dfs(start)
        components.append(list(visited))
        unvisited -= visited
        
    if len(components) > 1:
        # Sort components by size descending
        components.sort(key=len, reverse=True)
        main_comp = components[0]
        corridor_id = "inserted_central_corridor"
        if not any(corridor_id in comp for comp in components):
            rooms.append({"id": corridor_id, "room_type": "corridors"})
            room_types[corridor_id] = "corridors"
            room_counts["corridors"] = room_counts.get("corridors", 0) + 1
            main_comp.append(corridor_id)
            
        # Connect 1 room from each disconnected component to the corridor
        target_id = corridor_id if corridor_id in adj else main_comp[0]
        for comp in components[1:]:
            source_id = comp[0]
            final_connections.append({
                "room_a": source_id,
                "room_b": target_id,
                "weight": 5
            })
            issues_fixed.append(f"AI Connectivity Fix: Connected isolated room cluster starting with {source_id} to {target_id} to prevent floating rooms.")

    # Update the params
    graph["connections"] = final_connections
    graph["rooms"] = rooms
    params["graph"] = graph
    params["rooms"] = room_counts
        
    return params, issues_fixed
