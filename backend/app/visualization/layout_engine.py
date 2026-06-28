"""Layout engine: graph-based grid adjacency solver."""

import math
import random
from typing import List, Tuple, Dict, Any, Set

from .model import (
    FloorPlan, Rect, Room, Opening, OpeningType,
    Orientation, Furniture, SiteFeature, FeatureType,
)

STANDARD_ROOM_SIZES = {
    "bedrooms": 15, "bathrooms": 5, "kitchens": 10,
    "living_rooms": 20, "offices": 12, "outside_kitchens": 8,
    "outside_bathrooms": 4, "maid_rooms": 9, "corridors": 10
}

MIN_WIDTHS = {
    "bedrooms": 3.0, "living_rooms": 4.0, "bathrooms": 1.5,
    "kitchens": 3.0, "offices": 2.5, "outside_kitchens": 2.0,
    "outside_bathrooms": 1.5, "maid_rooms": 2.5, "corridors": 1.5
}

MIN_DEPTHS = {
    "bedrooms": 3.0, "living_rooms": 4.0, "bathrooms": 2.0,
    "kitchens": 3.0, "offices": 3.0, "outside_kitchens": 2.5,
    "outside_bathrooms": 2.0, "maid_rooms": 3.0, "corridors": 2.0
}

FURNITURE_SIZES = {
    "bed": (1.8, 2.0),
    "wardrobe": (2.0, 0.6),
    "bathtub": (0.8, 1.6),
    "toilet": (0.5, 0.7),
    "sink": (0.6, 0.5),
    "sofa": (2.2, 0.9),
    "tv_stand": (1.5, 0.4),
    "desk": (1.2, 0.6),
    "kitchen_island": (1.8, 0.9),
}

def _singular_label(rtype: str) -> str:
    base = rtype[:-1] if rtype.endswith("s") else rtype
    return base.replace("_", " ").capitalize()

def _build_furniture(rtype: str, room: Rect) -> List[Furniture]:
    f = []
    
    def add(type_name, x, y):
        w, h = FURNITURE_SIZES[type_name]
        f.append(Furniture(type_name, Rect(x, y, w, h)))

    if rtype in ("bedrooms", "maid_rooms"):
        add("bed", room.x + 0.5, room.y + 0.2)
        add("wardrobe", room.right - FURNITURE_SIZES["wardrobe"][0] - 0.2, room.bottom - FURNITURE_SIZES["wardrobe"][1] - 0.2)
    elif rtype in ("bathrooms", "outside_bathrooms"):
        add("bathtub", room.x + 0.1, room.y + 0.1)
        add("toilet", room.right - FURNITURE_SIZES["toilet"][0] - 0.1, room.y + 0.1)
        add("sink", room.right - FURNITURE_SIZES["sink"][0] - 0.1, room.bottom - FURNITURE_SIZES["sink"][1] - 0.1)
    elif rtype in ("kitchens", "outside_kitchens"):
        cw, ch = max(room.width - 0.4, 0.4), 0.6
        f.append(Furniture("kitchen_counter", Rect(room.cx - cw/2, room.y + 0.1, cw, ch)))
        if room.width >= 3.5 and room.height >= 3.5:
            add("kitchen_island", room.cx - FURNITURE_SIZES["kitchen_island"][0]/2, room.cy - FURNITURE_SIZES["kitchen_island"][1]/2)
    elif rtype == "living_rooms":
        add("sofa", room.cx - FURNITURE_SIZES["sofa"][0]/2, room.y + 0.5)
        add("tv_stand", room.cx - FURNITURE_SIZES["tv_stand"][0]/2, room.bottom - FURNITURE_SIZES["tv_stand"][1] - 0.2)
    elif rtype == "offices":
        add("desk", room.x + 0.5, room.y + 0.5)
        
    return f


def _score_layout(rects: Dict[str, Rect], edges: List[Dict]) -> float:
    # Lower is better. Calculate total area, perimeter, and walking distance.
    if not rects: return 0.0
    min_x = min(r.x for r in rects.values())
    max_x = max(r.right for r in rects.values())
    min_y = min(r.y for r in rects.values())
    max_y = max(r.bottom for r in rects.values())
    
    width = max_x - min_x
    height = max_y - min_y
    compactness = width * height # Bounding box area penalty
    
    # Connection distance penalty
    dist = 0
    for e in edges:
        if e['room_a'] in rects and e['room_b'] in rects:
            ra, rb = rects[e['room_a']], rects[e['room_b']]
            weight = e.get('weight', 1)
            dist += weight * (abs(ra.cx - rb.cx) + abs(ra.cy - rb.cy))
            
    return compactness * 0.1 + dist

def _solve_grid(nodes: List[Dict], edges: List[Dict], iterations: int = 20) -> Tuple[Dict[str, Rect], float]:
    if not nodes: return {}, 0.0
    adj = {n['id']: [] for n in nodes}
    for e in edges:
        if e['room_a'] in adj and e['room_b'] in adj:
            adj[e['room_a']].append(e['room_b'])
            adj[e['room_b']].append(e['room_a'])
            
    best_rects = {}
    best_score = float('inf')
    node_map = {n['id']: n for n in nodes}
    
    for _ in range(iterations):
        # Add slight randomness to sort order
        sorted_nodes = sorted(nodes, key=lambda n: len(adj[n['id']]) + random.random(), reverse=True)
        grid = {}
        placed = {}
        
        def get_adj_cells(x, y):
            return [(x+1,y), (x-1,y), (x,y+1), (x,y-1)]
            
        for node in sorted_nodes:
            nid = node['id']
            if not placed:
                grid[(0,0)] = nid
                placed[nid] = (0,0)
                continue
                
            connected_placed = [p for p in adj[nid] if p in placed]
            candidates = set()
            if connected_placed:
                for cp in connected_placed:
                    if placed[cp] is None: continue
                    cx, cy = placed[cp]
                    for ac in get_adj_cells(cx, cy):
                        if ac not in grid: candidates.add(ac)
            
            if not candidates:
                for p in placed.values():
                    if p is None: continue
                    for ac in get_adj_cells(p[0], p[1]):
                        if ac not in grid: candidates.add(ac)
                        
            best_cell = None
            cell_scores = []
            for cx, cy in candidates:
                score = 0
                if connected_placed:
                    for cp in connected_placed:
                        px, py = placed[cp]
                        score += abs(cx - px) + abs(cy - py)
                else:
                    score = abs(cx) + abs(cy)
                score += 0.01 * (abs(cx) + abs(cy))
                cell_scores.append((score, (cx, cy)))
                
            # Randomly pick among the top tied scores to explore different topologies
            if cell_scores:
                min_s = min(s for s, c in cell_scores)
                top_cells = [c for s, c in cell_scores if s <= min_s + 0.02]
                best_cell = random.choice(top_cells)
                    
            if best_cell:
                grid[best_cell] = nid
                placed[nid] = best_cell
            
        if not placed: continue
            
        min_x = min(x for x,y in placed.values() if x is not None)
        max_x = max(x for x,y in placed.values() if x is not None)
        min_y = min(y for x,y in placed.values() if y is not None)
        max_y = max(y for x,y in placed.values() if y is not None)
        
        col_widths = {}
        row_heights = {}
        
        for x in range(min_x, max_x + 1):
            ws = [MIN_WIDTHS.get(node_map[grid[(x,y)]]['type'], 2.0) for y in range(min_y, max_y + 1) if (x,y) in grid]
            col_widths[x] = max(ws) if ws else 0
        for y in range(min_y, max_y + 1):
            hs = [MIN_DEPTHS.get(node_map[grid[(x,y)]]['type'], 3.0) for x in range(min_x, max_x + 1) if (x,y) in grid]
            row_heights[y] = max(hs) if hs else 0
            
        rects = {}
        cur_y = 0
        for y in range(min_y, max_y + 1):
            cur_x = 0
            for x in range(min_x, max_x + 1):
                if (x,y) in grid:
                    rects[grid[(x,y)]] = Rect(cur_x, cur_y, col_widths[x], row_heights[y])
                cur_x += col_widths[x]
            cur_y += row_heights[y]
            
        # Score this candidate
        score = _score_layout(rects, edges)
        if score < best_score:
            best_score = score
            best_rects = rects
            
    return best_rects, best_score

def _build_openings(room_rects: Dict[str, Rect], nodes: List[Dict], edges: List[Dict]) -> Dict[str, List[Opening]]:
    openings = {n['id']: [] for n in nodes}
    node_map = {n['id']: n['type'] for n in nodes}
    
    for e in edges:
        ra, rb = e['room_a'], e['room_b']
        if ra not in room_rects or rb not in room_rects: continue
        r1, r2 = room_rects[ra], room_rects[rb]
        
        type_a, type_b = node_map[ra], node_map[rb]
        types_set = {type_a, type_b}
        
        is_passage = False
        door_len = 0.8
        
        if "living_rooms" in types_set:
            is_passage = True
            door_len = 1.6
        elif "dining_rooms" in types_set:
            is_passage = True
            door_len = 1.0
        elif "kitchens" in types_set or "outside_kitchens" in types_set:
            is_passage = True
            door_len = 0.9
            
        if not is_passage:
            if "bathrooms" in types_set or "outside_bathrooms" in types_set:
                door_len = 0.7
            else:
                door_len = 0.8
                
        op_type = OpeningType.PASSAGE if is_passage else OpeningType.DOOR
        
        if abs(r1.right - r2.x) < 0.1 or abs(r2.right - r1.x) < 0.1:
            # Vertical wall
            is_r1_left = abs(r1.right - r2.x) < 0.1
            x = r1.right if is_r1_left else r2.right
            ys, ye = max(r1.y, r2.y), min(r1.bottom, r2.bottom)
            if ye - ys >= door_len:
                dy = ys + (ye - ys - door_len) / 2
                swing = "right" if is_r1_left else "left"
                openings[ra].append(Opening(op_type, x, dy, door_len, Orientation.VERTICAL, swing=swing, style="swing"))
                openings[rb].append(Opening(op_type, x, dy, door_len, Orientation.VERTICAL, swing=swing, style="swing"))
        elif abs(r1.bottom - r2.y) < 0.1 or abs(r2.bottom - r1.y) < 0.1:
            # Horizontal wall
            is_r1_top = abs(r1.bottom - r2.y) < 0.1
            y = r1.bottom if is_r1_top else r2.bottom
            xs, xe = max(r1.x, r2.x), min(r1.right, r2.right)
            if xe - xs >= door_len:
                dx = xs + (xe - xs - door_len) / 2
                swing = "down" if is_r1_top else "up"
                openings[ra].append(Opening(op_type, dx, y, door_len, Orientation.HORIZONTAL, swing=swing, style="swing"))
                openings[rb].append(Opening(op_type, dx, y, door_len, Orientation.HORIZONTAL, swing=swing, style="swing"))

    # Building bounding box to detect exterior walls
    min_x = min(r.x for r in room_rects.values()) if room_rects else 0
    max_x = max(r.right for r in room_rects.values()) if room_rects else 0
    min_y = min(r.y for r in room_rects.values()) if room_rects else 0
    max_y = max(r.bottom for r in room_rects.values()) if room_rects else 0

    for n in nodes:
        nid = n['id']
        r = room_rects[nid]
        rtype = n['type']
        if rtype not in ["corridors"]:
            if rtype in ["bathrooms", "outside_bathrooms"]:
                win_len = 0.6
                style = "sliding"
            else:
                win_len = 1.6
                style = "sliding"
                
            if r.width >= win_len or r.height >= win_len:
                if abs(r.y - min_y) < 0.1:
                    openings[nid].append(Opening(OpeningType.WINDOW, r.cx - win_len/2, r.y, win_len, Orientation.HORIZONTAL, style=style))
                elif abs(r.bottom - max_y) < 0.1:
                    openings[nid].append(Opening(OpeningType.WINDOW, r.cx - win_len/2, r.bottom, win_len, Orientation.HORIZONTAL, style=style))
                elif abs(r.x - min_x) < 0.1:
                    openings[nid].append(Opening(OpeningType.WINDOW, r.x, r.cy - win_len/2, win_len, Orientation.VERTICAL, style=style))
                elif abs(r.right - max_x) < 0.1:
                    openings[nid].append(Opening(OpeningType.WINDOW, r.right, r.cy - win_len/2, win_len, Orientation.VERTICAL, style=style))
                
    # Front door
    for n in nodes:
        if n['type'] == 'living_rooms':
            r = room_rects[n['id']]
            openings[n['id']].append(Opening(OpeningType.DOOR, r.cx - 0.5, r.bottom, 1.0, Orientation.HORIZONTAL, swing="up", style="pivot"))
            break
            
    return openings

def build_floorplan(params: dict, compliance: dict) -> FloorPlan:
    plot_size = params.get("plot_size") or 600
    floors = params.get("floors") or 1
    parking = params.get("parking_spaces") or 0
    usage = params.get("usage") or "residential"
    
    plot_side = math.sqrt(plot_size)
    plot = Rect(0, 0, plot_side, plot_side)
    
    graph = params.get("graph")
    nodes = []
    edges = []
    if graph and graph.get("rooms"):
        for r in graph["rooms"]:
            nodes.append({"id": r["id"], "type": r["room_type"]})
        for e in graph.get("connections", []):
            edges.append(e)
    else:
        rooms_counts = params.get("rooms", {}) or {}
        prev_id = None
        for rtype, count in rooms_counts.items():
            for i in range(int(count)):
                nid = f"{rtype}_{i}"
                nodes.append({"id": nid, "type": rtype})
                if prev_id: edges.append({"room_a": prev_id, "room_b": nid})
                prev_id = nid
                
    annex_types = {"outside_kitchens", "outside_bathrooms", "maid_rooms"}
    main_nodes = [n for n in nodes if n["type"] not in annex_types]
    annex_nodes = [n for n in nodes if n["type"] in annex_types]
    
    main_edges = [e for e in edges if any(n['id'] == e['room_a'] for n in main_nodes) and any(n['id'] == e['room_b'] for n in main_nodes)]
    annex_edges = [e for e in edges if any(n['id'] == e['room_a'] for n in annex_nodes) and any(n['id'] == e['room_b'] for n in annex_nodes)]
    
    main_rects, main_score = _solve_grid(main_nodes, main_edges)
    annex_rects, annex_score = _solve_grid(annex_nodes, annex_edges)
    
    left_setback, back_setback, front_setback = 2.0, 2.0, 3.0
    
    main_w = max([r.right for r in main_rects.values()] + [0])
    main_h = max([r.bottom for r in main_rects.values()] + [0])
    annex_h = max([r.bottom for r in annex_rects.values()] + [0]) if annex_rects else 0.0
    
    shift_x = left_setback
    shift_y = back_setback + annex_h + (2.0 if annex_h > 0 else 0)
    
    placed_rooms = []
    
    if main_rects:
        openings_map = _build_openings(main_rects, main_nodes, main_edges)
        for nid, r in main_rects.items():
            ntype = next(n['type'] for n in main_nodes if n['id'] == nid)
            r.x += shift_x; r.y += shift_y
            for o in openings_map[nid]:
                o.x += shift_x; o.y += shift_y
            placed_rooms.append(Room(
                type=ntype,
                label=_singular_label(ntype) if ntype != "corridors" else "Corridor",
                bounds=r,
                openings=openings_map[nid],
                furniture=_build_furniture(ntype, r)
            ))
            
    placed_annex = []
    if annex_rects:
        annex_openings = _build_openings(annex_rects, annex_nodes, annex_edges)
        for nid, r in annex_rects.items():
            ntype = next(n['type'] for n in annex_nodes if n['id'] == nid)
            r.x += shift_x; r.y += back_setback
            for o in annex_openings[nid]:
                o.x += shift_x; o.y += back_setback
            placed_annex.append(Room(
                type=ntype,
                label=_singular_label(ntype),
                bounds=r,
                openings=annex_openings[nid],
                furniture=_build_furniture(ntype, r)
            ))
            
    building = Rect(shift_x, shift_y, main_w, main_h)
    annex_building = Rect(shift_x, back_setback, max([r.right for r in annex_rects.values()] + [0]), annex_h) if placed_annex else None

    # normalize score to a 0-100 scale (just a simple heuristic)
    total_score = max(0, min(100, 100 - (main_score + annex_score) * 2))

    plan = FloorPlan(
        plot=plot,
        building=building,
        rooms=placed_rooms,
        annex_building=annex_building,
        annex_rooms=placed_annex,
        plot_size_sqm=plot_size,
        floors=floors,
        usage=usage,
        parking_spaces=parking,
        wall_thickness=0.2,
        score=total_score
    )
    
    plan.site_features.append(SiteFeature(FeatureType.GRASS, Rect(0, 0, plot.width, plot.height)))
    
    front_door_x = shift_x + main_w / 2 - 0.75
    front_door_y = shift_y + main_h
    for r in plan.rooms:
        if r.type == "living_rooms":
            front_door_x = r.bounds.cx - 0.75
            front_door_y = r.bounds.bottom
            break
            
    # Irregular path routing
    path_points = []
    start_x = front_door_x + 0.75
    
    drop_y = max(front_door_y + 1.5, plan.building.bottom + 1.0)
    center_road_x = plot.width / 2
    
    path_points.append((start_x, front_door_y))
    path_points.append((start_x, drop_y))
    
    if abs(start_x - center_road_x) > 1.5:
        path_points.append((center_road_x, drop_y))
        path_points.append((center_road_x, plot.height))
    else:
        path_points.append((start_x, plot.height))
        
    plan.site_features.append(SiteFeature(
        type=FeatureType.PATH,
        bounds=Rect(min(start_x, center_road_x)-0.75, front_door_y, abs(start_x - center_road_x)+1.5, plot.height - front_door_y),
        points=path_points
    ))
    
    if parking > 0:
        stall_w, stall_h = 2.5, 3.0
        start_x, start_y = 2.0, plot.height - stall_h
        for i in range(min(parking, 5)):
            plan.site_features.append(SiteFeature(FeatureType.PARKING, Rect(start_x + i * 3.0, start_y, stall_w, stall_h), "P"))

    return plan
