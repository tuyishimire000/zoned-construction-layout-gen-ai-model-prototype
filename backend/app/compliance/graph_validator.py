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
        
        is_privacy_violation = ("bedrooms" in types_set) and ("kitchens" in types_set or "living_rooms" in types_set)
        is_sanitation_violation = ("bathrooms" in types_set) and ("kitchens" in types_set or "living_rooms" in types_set)
        
        if is_privacy_violation or is_sanitation_violation:
            # We must break this connection and insert a corridor
            connections_to_remove.append(idx)
            
            corridor_id = f"inserted_corridor_{corridors_added + 1}"
            
            # Add new corridor room
            rooms.append({"id": corridor_id, "room_type": "corridors"})
            room_types[corridor_id] = "corridors"
            room_counts["corridors"] = room_counts.get("corridors", 0) + 1
            corridors_added += 1
            
            # Create two new connections routing through the corridor
            new_connections.append({
                "room_a": ra_id,
                "room_b": corridor_id,
                "weight": conn.get("weight", 5)
            })
            new_connections.append({
                "room_a": corridor_id,
                "room_b": rb_id,
                "weight": conn.get("weight", 5)
            })
            
            # Log the fix
            if is_privacy_violation:
                issues_fixed.append(f"AI Privacy Fix: A bedroom was directly connected to a living area. Inserted a hallway ({corridor_id}) to act as a privacy buffer.")
            elif is_sanitation_violation:
                issues_fixed.append(f"AI Sanitation Fix: A bathroom was directly connected to a living area/kitchen. Inserted a hallway ({corridor_id}) to act as a buffer.")

    if connections_to_remove:
        # Rebuild connections list without the removed ones, and add the new ones
        final_connections = [c for i, c in enumerate(connections) if i not in connections_to_remove]
        final_connections.extend(new_connections)
        graph["connections"] = final_connections
        
        # Update the params
        graph["rooms"] = rooms
        params["graph"] = graph
        params["rooms"] = room_counts
        
    return params, issues_fixed
