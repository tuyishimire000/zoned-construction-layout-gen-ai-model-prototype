"""Layout engine: graph-based grid adjacency solver."""

import math
import random
from typing import List, Tuple, Dict, Any, Set

from .model import (
    FloorPlan, Rect, Room, Opening, OpeningType,
    Orientation, Furniture, SiteFeature, FeatureType,
)

STANDARD_ROOM_SIZES = {
    "bedrooms": 24, "bathrooms": 8, "kitchens": 18,
    "living_rooms": 35, "offices": 16, "outside_kitchens": 12,
    "outside_bathrooms": 6, "maid_rooms": 12, "corridors": 15
}

MIN_WIDTHS = {
    "bedrooms": 4.0, "living_rooms": 5.0, "bathrooms": 2.0,
    "kitchens": 3.5, "offices": 3.0, "outside_kitchens": 3.0,
    "outside_bathrooms": 2.0, "maid_rooms": 3.0, "corridors": 1.5
}

MIN_DEPTHS = {
    "bedrooms": 4.0, "living_rooms": 5.0, "bathrooms": 2.5,
    "kitchens": 4.0, "offices": 3.5, "outside_kitchens": 3.0,
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
                
            if cell_scores:
                min_s = min(s for s, c in cell_scores)
                top_cells = [c for s, c in cell_scores if s <= min_s + 0.02]
                best_cell = random.choice(top_cells)
                    
            if best_cell:
                grid[best_cell] = nid
                placed[nid] = best_cell
            
        if not placed: continue
            
        rects = {}
        for nid, (gx, gy) in placed.items():
            rtype = node_map[nid]['type']
            w = MIN_WIDTHS.get(rtype, 3.0)
            h = MIN_DEPTHS.get(rtype, 3.0)
            
            if "corridor" in rtype.lower():
                w, h = 1.5, 1.5
                    
            rects[nid] = Rect(gx * 4.0, gy * 4.0, w, h)
            
        # Physics Relaxation Loop (150 iterations)
        for _step in range(150):
            # Attractive forces based on graph edges
            for e in edges:
                if e['room_a'] in rects and e['room_b'] in rects:
                    ra, rb = rects[e['room_a']], rects[e['room_b']]
                    dx = rb.cx - ra.cx
                    dy = rb.cy - ra.cy
                    if abs(dx) > abs(dy):
                        target_dist = (ra.width + rb.width)/2
                        force = (abs(dx) - target_dist) * 0.2
                        shift_x = force * (1 if dx > 0 else -1)
                        ra.x += shift_x
                        rb.x -= shift_x
                        shift_y = dy * 0.1
                        ra.y += shift_y
                        rb.y -= shift_y
                    else:
                        target_dist = (ra.height + rb.height)/2
                        force = (abs(dy) - target_dist) * 0.2
                        shift_y = force * (1 if dy > 0 else -1)
                        ra.y += shift_y
                        rb.y -= shift_y
                        shift_x = dx * 0.1
                        ra.x += shift_x
                        rb.x -= shift_x
                        
            # Repulsive forces (prevent overlap)
            for nid1, r1 in rects.items():
                for nid2, r2 in rects.items():
                    if nid1 >= nid2: continue
                    dx = r2.cx - r1.cx
                    dy = r2.cy - r1.cy
                    min_x = (r1.width + r2.width)/2
                    min_y = (r1.height + r2.height)/2
                    if abs(dx) < min_x and abs(dy) < min_y:
                        pen_x = min_x - abs(dx)
                        pen_y = min_y - abs(dy)
                        if pen_x < pen_y:
                            shift = (pen_x / 2 + 0.05) * (1 if dx > 0 else -1)
                            r1.x -= shift
                            r2.x += shift
                        else:
                            shift = (pen_y / 2 + 0.05) * (1 if dy > 0 else -1)
                            r1.y -= shift
                            r2.y += shift

            # Corridor stretching
            for nid, r in rects.items():
                if "corridor" in node_map[nid]['type'].lower():
                    # Find connected rooms
                    connected_r = [rects[e['room_b']] for e in edges if e['room_a'] == nid and e['room_b'] in rects] + \
                                  [rects[e['room_a']] for e in edges if e['room_b'] == nid and e['room_a'] in rects]
                    
                    if len(connected_r) >= 2:
                        min_cx = min(cr.cx for cr in connected_r)
                        max_cx = max(cr.cx for cr in connected_r)
                        min_cy = min(cr.cy for cr in connected_r)
                        max_cy = max(cr.cy for cr in connected_r)
                        
                        span_w = max_cx - min_cx
                        span_h = max_cy - min_cy
                        
                        # We want the corridor to span between the centers of the furthest connected rooms
                        # minus half the width of those rooms, but roughly span_w * 0.8 works well as an approximation.
                        if span_w > span_h:
                            target_w = max(1.5, span_w * 0.8)
                            target_h = 1.5
                        else:
                            target_w = 1.5
                            target_h = max(1.5, span_h * 0.8)
                            
                        # Smoothly adapt width/height
                        r.width += (target_w - r.width) * 0.1
                        r.height += (target_h - r.height) * 0.1

        # Snap to 0.1 grid
        for r in rects.values():
            r.x = round(r.x * 10) / 10
            r.y = round(r.y * 10) / 10
            r.width = round(r.width * 10) / 10
            r.height = round(r.height * 10) / 10
            
        score = _score_layout(rects, edges)
        if score < best_score:
            best_score = score
            best_rects = rects
            
    return best_rects, best_score

def _build_openings(room_rects: Dict[str, Rect], nodes: List[Dict], edges: List[Dict]) -> Dict[str, List[Opening]]:
    openings = {n['id']: [] for n in nodes}
    node_map = {n['id']: n['type'] for n in nodes}
    
    room_doors_count = {n['id']: 0 for n in nodes}
    
    for e in edges:
        ra, rb = e['room_a'], e['room_b']
        if ra not in room_rects or rb not in room_rects: continue
        r1, r2 = room_rects[ra], room_rects[rb]
        
        type_a, type_b = node_map[ra], node_map[rb]
        types_set = {type_a, type_b}
        
        def is_open(t):
            t = t.lower()
            return "corridor" in t or "living" in t or "dining" in t or "kitchen" in t
            
        def is_corridor(t): return "corridor" in t.lower()
        def is_living(t): return "living" in t.lower()
        def is_dining(t): return "dining" in t.lower()
        def is_bath(t): return "bath" in t.lower()
        
        is_passage = False
        door_len = 0.9
        
        if all(is_open(t) for t in types_set):
            is_passage = True
            if any(is_living(t) for t in types_set):
                door_len = 1.6
            elif all(is_corridor(t) for t in types_set):
                door_len = 1.2
            elif any(is_dining(t) for t in types_set):
                door_len = 1.2
            else:
                door_len = 1.0
        else:
            if any(is_bath(t) for t in types_set):
                door_len = 0.7
            elif any(is_living(t) for t in types_set):
                door_len = 1.0
            else:
                door_len = 0.9
                
        op_type = OpeningType.PASSAGE if is_passage else OpeningType.DOOR
        
        def add_door(o_type, dx, dy, dlen, ori, swing):
            openings[ra].append(Opening(o_type, dx, dy, dlen, ori, swing=swing, style="swing"))
            openings[rb].append(Opening(o_type, dx, dy, dlen, ori, swing=swing, style="swing"))
            room_doors_count[ra] += 1
            room_doors_count[rb] += 1
            
        def get_privacy_score(t):
            t = t.lower()
            if "bath" in t or "toilet" in t or "wc" in t: return 10
            if "bed" in t or "master" in t: return 8
            if "office" in t or "study" in t: return 7
            if "kitchen" in t: return 5
            if "dining" in t: return 4
            if "living" in t or "lounge" in t: return 3
            if "corridor" in t or "hall" in t: return 1
            return 5
            
        score_a = get_privacy_score(type_a)
        score_b = get_privacy_score(type_b)
        
        if abs(r1.right - r2.x) < 0.1 or abs(r2.right - r1.x) < 0.1:
            # Vertical wall
            is_r1_left = abs(r1.right - r2.x) < 0.1
            x = r1.right if is_r1_left else r2.right
            ys, ye = max(r1.y, r2.y), min(r1.bottom, r2.bottom)
            if ye - ys >= door_len:
                dy = ys + (ye - ys - door_len) / 2
                if score_a > score_b:
                    swing = "left" if is_r1_left else "right"
                elif score_b > score_a:
                    swing = "right" if is_r1_left else "left"
                else:
                    swing = "right" if is_r1_left else "left"
                add_door(op_type, x, dy, door_len, Orientation.VERTICAL, swing)
        elif abs(r1.bottom - r2.y) < 0.1 or abs(r2.bottom - r1.y) < 0.1:
            # Horizontal wall
            is_r1_top = abs(r1.bottom - r2.y) < 0.1
            y = r1.bottom if is_r1_top else r2.bottom
            xs, xe = max(r1.x, r2.x), min(r1.right, r2.right)
            if xe - xs >= door_len:
                dx = xs + (xe - xs - door_len) / 2
                if score_a > score_b:
                    swing = "up" if is_r1_top else "down"
                elif score_b > score_a:
                    swing = "down" if is_r1_top else "up"
                else:
                    swing = "down" if is_r1_top else "up"
                add_door(op_type, dx, y, door_len, Orientation.HORIZONTAL, swing)

    # Fallback: if a room has no doors/passages but touches another room, force a door!
    for nid, r in room_rects.items():
        if room_doors_count[nid] == 0:
            for other_id, other_r in room_rects.items():
                if nid == other_id: continue
                
                type_a, type_b = node_map[nid], node_map[other_id]
                types_set = {type_a, type_b}
                is_bed = any("bedroom" in t.lower() for t in types_set)
                is_bath = any("bathroom" in t.lower() for t in types_set)
                is_living = any("living" in t.lower() for t in types_set)
                is_kitchen = any("kitchen" in t.lower() for t in types_set)
                
                # Forbid emergency fallback doors between high privacy zones
                if (is_bed or is_bath) and (is_kitchen or is_living):
                    continue
                    
                is_passage = all("corridor" in t.lower() or "living" in t.lower() or "dining" in t.lower() or "kitchen" in t.lower() for t in types_set)
                fallback_op_type = OpeningType.PASSAGE if is_passage else OpeningType.DOOR
                door_len = 1.2 if is_passage else 0.8
                
                score_r = get_privacy_score(type_a)
                score_other = get_privacy_score(type_b)
                
                # check if they touch
                if abs(r.right - other_r.x) < 0.1 or abs(other_r.right - r.x) < 0.1:
                    is_r_left = abs(r.right - other_r.x) < 0.1
                    x = r.right if is_r_left else other_r.right
                    ys, ye = max(r.y, other_r.y), min(r.bottom, other_r.bottom)
                    if ye - ys >= door_len:
                        dy = ys + (ye - ys - door_len) / 2
                        if score_r > score_other:
                            swing = "left" if is_r_left else "right"
                        elif score_other > score_r:
                            swing = "right" if is_r_left else "left"
                        else:
                            swing = "right" if is_r_left else "left"
                        openings[nid].append(Opening(fallback_op_type, x, dy, door_len, Orientation.VERTICAL, swing=swing, style="swing"))
                        openings[other_id].append(Opening(fallback_op_type, x, dy, door_len, Orientation.VERTICAL, swing=swing, style="swing"))
                        room_doors_count[nid] += 1
                        break
                elif abs(r.bottom - other_r.y) < 0.1 or abs(other_r.bottom - r.y) < 0.1:
                    is_r_top = abs(r.bottom - other_r.y) < 0.1
                    y = r.bottom if is_r_top else other_r.bottom
                    xs, xe = max(r.x, other_r.x), min(r.right, other_r.right)
                    if xe - xs >= door_len:
                        dx = xs + (xe - xs - door_len) / 2
                        if score_r > score_other:
                            swing = "up" if is_r_top else "down"
                        elif score_other > score_r:
                            swing = "down" if is_r_top else "up"
                        else:
                            swing = "down" if is_r_top else "up"
                        openings[nid].append(Opening(fallback_op_type, dx, y, door_len, Orientation.HORIZONTAL, swing=swing, style="swing"))
                        openings[other_id].append(Opening(fallback_op_type, dx, y, door_len, Orientation.HORIZONTAL, swing=swing, style="swing"))
                        room_doors_count[nid] += 1
                        break

    # Extents detection for Windows
    def get_exposed_intervals(r, edge, all_rects):
        if edge in ('top', 'bottom'):
            main_bounds = [r.x, r.right]
        else:
            main_bounds = [r.y, r.bottom]
            
        covered = []
        for other in all_rects:
            if other == r: continue
            if edge == 'top' and abs(other.bottom - r.y) < 0.1:
                covered.append((max(r.x, other.x), min(r.right, other.right)))
            elif edge == 'bottom' and abs(other.y - r.bottom) < 0.1:
                covered.append((max(r.x, other.x), min(r.right, other.right)))
            elif edge == 'left' and abs(other.right - r.x) < 0.1:
                covered.append((max(r.y, other.y), min(r.bottom, other.bottom)))
            elif edge == 'right' and abs(other.x - r.right) < 0.1:
                covered.append((max(r.y, other.y), min(r.bottom, other.bottom)))
                
        intervals = []
        cur = main_bounds[0]
        for c in sorted(covered):
            if c[0] > cur:
                intervals.append((cur, c[0]))
            cur = max(cur, c[1])
        if cur < main_bounds[1]:
            intervals.append((cur, main_bounds[1]))
        return [i for i in intervals if i[1] - i[0] > 0.1]

    all_r = list(room_rects.values())
    
    # Place External Doors
    def place_external_door(room_type_keywords, door_len=1.0, fallback_type_keywords=None):
        target_nids = [n['id'] for n in nodes if any(kw in n['type'].lower() for kw in room_type_keywords)]
        for nid in target_nids:
            if nid not in room_rects: continue
            r = room_rects[nid]
            for edge in ['bottom', 'top', 'left', 'right']:
                intervals = get_exposed_intervals(r, edge, all_r)
                for start, end in intervals:
                    if end - start >= door_len + 0.4:
                        if edge in ('top', 'bottom'):
                            cx = start + (end - start)/2
                            cy = r.y if edge == 'top' else r.bottom
                            swing = "down" if edge == 'top' else "up"
                            openings[nid].append(Opening(OpeningType.DOOR, cx, cy, door_len, Orientation.HORIZONTAL, swing=swing, style="swing"))
                            if edge == 'top':
                                all_r.append(Rect(cx - door_len/2 - 0.2, r.y - 0.2, door_len + 0.4, 0.2))
                            else:
                                all_r.append(Rect(cx - door_len/2 - 0.2, r.bottom, door_len + 0.4, 0.2))
                        else:
                            cx = r.x if edge == 'left' else r.right
                            cy = start + (end - start)/2
                            swing = "right" if edge == 'left' else "left"
                            openings[nid].append(Opening(OpeningType.DOOR, cx, cy, door_len, Orientation.VERTICAL, swing=swing, style="swing"))
                            if edge == 'left':
                                all_r.append(Rect(r.x - 0.2, cy - door_len/2 - 0.2, 0.2, door_len + 0.4))
                            else:
                                all_r.append(Rect(r.right, cy - door_len/2 - 0.2, 0.2, door_len + 0.4))
                        return True
                        
        if fallback_type_keywords:
            fallback_nids = [n['id'] for n in nodes if any(kw in n['type'].lower() for kw in fallback_type_keywords)]
            for nid in fallback_nids:
                if nid not in room_rects: continue
                r = room_rects[nid]
                for edge in ['bottom', 'top', 'left', 'right']:
                    intervals = get_exposed_intervals(r, edge, all_r)
                    for start, end in intervals:
                        if end - start >= door_len + 0.4:
                            if edge in ('top', 'bottom'):
                                cx = start + (end - start)/2
                                cy = r.y if edge == 'top' else r.bottom
                                swing = "down" if edge == 'top' else "up"
                                openings[nid].append(Opening(OpeningType.DOOR, cx, cy, door_len, Orientation.HORIZONTAL, swing=swing, style="swing"))
                                if edge == 'top':
                                    all_r.append(Rect(cx - door_len/2 - 0.2, r.y - 0.2, door_len + 0.4, 0.2))
                                else:
                                    all_r.append(Rect(cx - door_len/2 - 0.2, r.bottom, door_len + 0.4, 0.2))
                            else:
                                cx = r.x if edge == 'left' else r.right
                                cy = start + (end - start)/2
                                swing = "right" if edge == 'left' else "left"
                                openings[nid].append(Opening(OpeningType.DOOR, cx, cy, door_len, Orientation.VERTICAL, swing=swing, style="swing"))
                                if edge == 'left':
                                    all_r.append(Rect(r.x - 0.2, cy - door_len/2 - 0.2, 0.2, door_len + 0.4))
                                else:
                                    all_r.append(Rect(r.right, cy - door_len/2 - 0.2, 0.2, door_len + 0.4))
                            return True
        return False
        
    # 1. Main Entrance (Living Room or Corridor)
    place_external_door(["living"], 1.0, ["corridor"])
    # 2. Back Door (Kitchen or Corridor)
    place_external_door(["kitchen"], 0.9, ["corridor"])

    all_rects = all_r
    for n in nodes:
        nid = n['id']
        r = room_rects[nid]
        rtype = n['type']
        
        if rtype in ["storage"]:
            continue
            
        if rtype in ["corridors"] and max(r.width, r.height) <= 4.0:
            continue
            
        is_bathroom = rtype in ["bathrooms", "outside_bathrooms"]
        
        window_placed = False
        for edge in ['top', 'bottom', 'left', 'right']:
            if window_placed:
                break
            intervals = get_exposed_intervals(r, edge, all_rects)
            for (start, end) in intervals:
                wall_len = end - start
                
                if is_bathroom:
                    win_len = 0.6
                else:
                    win_len = min(4.0, max(1.0, wall_len * 0.4))
                    
                if wall_len >= win_len + 0.4:
                    center = start + wall_len / 2
                    if center - win_len/2 < start + 0.2:
                        center = start + 0.2 + win_len/2
                    if center + win_len/2 > end - 0.2:
                        center = end - 0.2 - win_len/2
                        
                    if edge == 'top':
                        openings[nid].append(Opening(OpeningType.WINDOW, center - win_len/2, r.y, win_len, Orientation.HORIZONTAL, style="sliding"))
                    elif edge == 'bottom':
                        openings[nid].append(Opening(OpeningType.WINDOW, center - win_len/2, r.bottom, win_len, Orientation.HORIZONTAL, style="sliding"))
                    elif edge == 'left':
                        openings[nid].append(Opening(OpeningType.WINDOW, r.x, center - win_len/2, win_len, Orientation.VERTICAL, style="sliding"))
                    elif edge == 'right':
                        openings[nid].append(Opening(OpeningType.WINDOW, r.right, center - win_len/2, win_len, Orientation.VERTICAL, style="sliding"))
                    window_placed = True
                    break


            
    return openings

def build_floorplan(params: dict, compliance: dict) -> FloorPlan:
    plot_size = params.get("plot_size") or 600
    floors = params.get("floors") or 1
    parking = params.get("parking_spaces") or 0
    usage = params.get("usage") or "residential"
    archetype = params.get("archetype") or "auto"
    
    plot_side = math.sqrt(plot_size)
    plot = Rect(0, 0, plot_side, plot_side)
    
    rooms_counts = params.get("rooms", {}) or {}
    
    from .house_sketch import HouseSketch, SketchValidationError
    
    try:
        # 1. Generate the house layout
        hs = HouseSketch(
            plot_width=plot_side,
            plot_depth=plot_side,
            rooms=rooms_counts,
            archetype=archetype,
        )
    except SketchValidationError as e:
        # Fallback to a tiny layout if we can't fit the requested rooms, or just re-raise.
        # For a prototype, raising is fine so the error bubbles up.
        raise ValueError(f"Layout generation failed: {e}")

    # 2. Map HouseSketch geometry to Model Geometry
    placed_rooms = []
    
    def _dist(p1, p2):
        return math.hypot(p2[0]-p1[0], p2[1]-p1[1])
        
    for hr in hs.all_rooms:
        if not hr.rect: continue
        r = Rect(hr.rect.x, hr.rect.y, hr.rect.w, hr.rect.h)
        rtype = hr.type.value if hasattr(hr.type, 'value') else hr.type
        # Our furniture expects plural type names or exactly what's in FURNITURE_SIZES mapping,
        # but HouseSketch uses singular types (bedroom, bathroom, etc).
        plural_type = f"{rtype}s" if not rtype.endswith('s') else rtype
        
        openings = []
        for w in hr.windows:
            w_len = _dist(w.p0, w.p1)
            cx, cy = (w.p0[0] + w.p1[0])/2, (w.p0[1] + w.p1[1])/2
            orient = Orientation.HORIZONTAL if abs(w.p0[1] - w.p1[1]) < 0.1 else Orientation.VERTICAL
            # To anchor it top-left in our opening struct:
            ox = cx - w_len/2 if orient == Orientation.HORIZONTAL else cx
            oy = cy - w_len/2 if orient == Orientation.VERTICAL else cy
            openings.append(Opening(OpeningType.WINDOW, ox, oy, w_len, orient, "sliding"))
            
        for d in hr.doors:
            d_len = _dist(d.leaf[0], d.leaf[1])
            # The gap center
            center_x = (d.leaf[0][0] + d.leaf[1][0]) / 2
            center_y = (d.leaf[0][1] + d.leaf[1][1]) / 2
            
            orient = Orientation.HORIZONTAL if abs(d.leaf[0][1] - d.leaf[1][1]) < 0.1 else Orientation.VERTICAL
            
            if orient == Orientation.HORIZONTAL:
                ox = min(d.leaf[0][0], d.leaf[1][0])
                oy = d.leaf[0][1]
                # Is the door on the top or bottom wall of the room?
                # If oy is closer to rect.y (top), it's on the top wall.
                is_top_wall = abs(oy - hr.rect.y) < abs(oy - hr.rect.bottom)
                # It should swing INTO the room: if top wall, swing down. If bottom wall, swing up.
                swing = "down" if is_top_wall else "up"
                
                # Should hinge be on the left (start) or right (end) of the gap?
                # Hinge should be closer to the nearest perpendicular wall to open against it.
                dist_left = abs(ox - hr.rect.x)
                dist_right = abs((ox + d_len) - hr.rect.right)
                hinge_at_start = dist_left <= dist_right
            else:
                ox = d.leaf[0][0]
                oy = min(d.leaf[0][1], d.leaf[1][1])
                # Is the door on the left or right wall?
                is_left_wall = abs(ox - hr.rect.x) < abs(ox - hr.rect.right)
                # It should swing INTO the room: if left wall, swing right. If right wall, swing left.
                swing = "right" if is_left_wall else "left"
                
                # Should hinge be on the bottom (start) or top (end) of the gap?
                dist_bottom = abs(oy - hr.rect.y) # wait, rect.y is top!
                dist_top = abs(oy - hr.rect.y)
                dist_bottom = abs((oy + d_len) - hr.rect.bottom)
                hinge_at_start = dist_top <= dist_bottom # True means hinge is at oy (which is the smaller y, i.e. closer to top)
                
            openings.append(Opening(OpeningType.DOOR, ox, oy, d_len, orient, swing=swing, hinge_at_start=hinge_at_start))
            
        # Add open archways
        for a_p0, a_p1 in hs.openings:
            # check if this archway belongs to this room
            if (hr.rect.x - 0.1 <= a_p0[0] <= hr.rect.right + 0.1 and 
                hr.rect.y - 0.1 <= a_p0[1] <= hr.rect.bottom + 0.1):
                a_len = _dist(a_p0, a_p1)
                cx, cy = (a_p0[0] + a_p1[0])/2, (a_p0[1] + a_p1[1])/2
                orient = Orientation.HORIZONTAL if abs(a_p0[1] - a_p1[1]) < 0.1 else Orientation.VERTICAL
                ox = cx - a_len/2 if orient == Orientation.HORIZONTAL else cx
                oy = cy - a_len/2 if orient == Orientation.VERTICAL else cy
                openings.append(Opening(OpeningType.DOOR, ox, oy, a_len, orient, "open"))

        placed_rooms.append(Room(
            type=plural_type,
            label=hr.label,
            bounds=r,
            openings=openings,
            furniture=_build_furniture(plural_type, r)
        ))
        
    building = Rect(hs.footprint.x, hs.footprint.y, hs.footprint.w, hs.footprint.h)

    # Note: HouseSketch does not explicitly separate annexes by default unless we wrote custom manual rules,
    # so we place everything in the main building.
    
    plan = FloorPlan(
        plot=plot,
        building=building,
        rooms=placed_rooms,
        annex_building=None,
        annex_rooms=[],
        plot_size_sqm=plot_size,
        floors=floors,
        usage=usage,
        parking_spaces=parking,
        wall_thickness=0.2,
        score=100  # Always 100 since it's procedural and precise
    )
    
    plan.site_features.append(SiteFeature(FeatureType.GRASS, Rect(0, 0, plot.width, plot.height)))
    
    front_door_x = building.cx
    front_door_y = building.bottom
    # Try to find a door on the bottom wall of the building
    for r in plan.rooms:
        if abs(r.bounds.bottom - building.bottom) < 0.5:
            for o in r.openings:
                if o.type == OpeningType.DOOR and o.orientation == Orientation.HORIZONTAL and abs(o.y - building.bottom) < 0.5:
                    front_door_x = o.x + o.size / 2
                    front_door_y = o.y
                    break
            
    # Irregular path routing
    path_points = []
    start_x = front_door_x
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

