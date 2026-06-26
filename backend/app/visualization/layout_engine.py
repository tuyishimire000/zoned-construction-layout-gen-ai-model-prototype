"""Layout engine: turns extracted params + compliance into a FloorPlan model."""

import math
from typing import List, Tuple

from .model import (
    FloorPlan,
    Rect,
    Room,
    Opening,
    OpeningType,
    Orientation,
    Furniture,
    SiteFeature,
    FeatureType,
)

STANDARD_ROOM_SIZES = {
    "bedrooms": 15,
    "bathrooms": 5,
    "kitchens": 10,
    "living_rooms": 20,
    "offices": 12,
}

# New physical constraints
MIN_WIDTHS = {
    "bedrooms": 2.5,
    "living_rooms": 3.0,
    "bathrooms": 1.5,
    "kitchens": 2.5,
    "offices": 2.5,
}

MIN_DEPTHS = {
    "bedrooms": 3.0,
    "living_rooms": 4.0,
    "bathrooms": 2.0,
    "kitchens": 3.0,
    "offices": 3.0,
}

FURNITURE_SIZES = {
    "bed": (1.5, 2.0),
    "bathtub": (0.8, 1.6),
    "sofa": (2.0, 0.8),
    "desk": (1.2, 0.6),
}

ROOM_PADDING = 0.4
CORRIDOR_HEIGHT = 1.2


def _singular_label(rtype: str) -> str:
    base = rtype[:-1] if rtype.endswith("s") else rtype
    return base.replace("_", " ").capitalize()


def _split_into_wings(
    room_items: List[Tuple[str, float]]
) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
    top, bottom = [], []
    
    # Group by type
    from collections import defaultdict
    groups = defaultdict(list)
    for r in room_items:
        groups[r[0]].append(r)
        
    top_weight = bottom_weight = 0.0
    
    # Distribute each type evenly
    for rtype, items in groups.items():
        for i, item in enumerate(items):
            # Try to balance weight overall, but also distribute the type
            # Alternate based on index to ensure even spread of instances
            if i % 2 == 0:
                if top_weight <= bottom_weight:
                    top.append(item)
                    top_weight += item[1]
                else:
                    bottom.append(item)
                    bottom_weight += item[1]
            else:
                if top_weight > bottom_weight:
                    top.append(item)
                    top_weight += item[1]
                else:
                    bottom.append(item)
                    bottom_weight += item[1]

    return top, bottom


def _build_furniture(rtype: str, room: Rect) -> List[Furniture]:
    fx = room.x + ROOM_PADDING
    fy = room.y + ROOM_PADDING

    if rtype == "bedrooms":
        w, h = FURNITURE_SIZES["bed"]
        return [Furniture("bed", Rect(fx, fy, w, h))]
    if rtype == "bathrooms":
        w, h = FURNITURE_SIZES["bathtub"]
        return [Furniture("bathtub", Rect(fx, fy, w, h))]
    if rtype == "kitchens":
        return [
            Furniture(
                "kitchen_counter",
                Rect(room.x + 0.2, room.y + 0.2, max(room.width - 0.4, 0.4), 0.6),
            )
        ]
    if rtype == "living_rooms":
        w, h = FURNITURE_SIZES["sofa"]
        return [Furniture("sofa", Rect(fx, fy, min(w, room.width - 0.4), h))]
    if rtype == "offices":
        w, h = FURNITURE_SIZES["desk"]
        return [Furniture("desk", Rect(fx, fy, w, h))]
    return []


def _build_openings(room: Rect, rtype: str, is_top_wing: bool) -> List[Opening]:
    openings: List[Opening] = []

    exterior_y = room.y if is_top_wing else room.bottom
    corridor_y = room.bottom if is_top_wing else room.y

    # Internal door to the corridor
    door_len = min(1.0, max(0.5, room.width - 0.4))
    door_x = room.cx - door_len / 2
    openings.append(
        Opening(OpeningType.DOOR, door_x, corridor_y, door_len, Orientation.HORIZONTAL)
    )

    if rtype == "living_rooms":
        # Living Room has a front entrance double door (2x1m) AND a window on its exterior wall
        # Divide the width: Door in left half, Window in right half
        door_total = min(2.0, room.width * 0.45)
        single_door = door_total / 2.0
        
        # Center the double door in the left half of the room (so it's not glued to the corner)
        left_center = room.x + room.width * 0.25
        front_door1_x = left_center - single_door
        front_door2_x = left_center
        
        # Center the window in the right half of the room
        win_len = min(2.0, room.width * 0.45)
        right_center = room.x + room.width * 0.75
        win_x = right_center - win_len / 2.0
        
        # Left door of the double door (hinges on its left, start)
        openings.append(
            Opening(OpeningType.DOOR, front_door1_x, exterior_y, single_door, Orientation.HORIZONTAL, hinge_at_start=True)
        )
        # Right door of the double door (hinges on its right, end)
        openings.append(
            Opening(OpeningType.DOOR, front_door2_x, exterior_y, single_door, Orientation.HORIZONTAL, hinge_at_start=False)
        )
        # Window
        openings.append(
            Opening(OpeningType.WINDOW, win_x, exterior_y, win_len, Orientation.HORIZONTAL)
        )
    else:
        # Other rooms just have a window on exterior
        win_len = 1.5
        win_len = min(win_len, max(0.5, room.width - 0.4))
        win_x = room.cx - win_len / 2
        openings.append(
            Opening(OpeningType.WINDOW, win_x, exterior_y, win_len, Orientation.HORIZONTAL)
        )

    return openings


def _sort_wing_rooms(rooms: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    public_order = ["living_rooms", "kitchens", "offices"]
    public = []
    beds = []
    baths = []
    others = []
    
    for r in rooms:
        rtype = r[0]
        if rtype in public_order:
            public.append(r)
        elif rtype == "bedrooms":
            beds.append(r)
        elif rtype == "bathrooms":
            baths.append(r)
        else:
            others.append(r)
            
    public.sort(key=lambda x: public_order.index(x[0]))
    
    # Interleave beds and baths
    # If there are more baths than beds, start with baths to keep them separated
    interleaved = []
    if len(baths) > len(beds):
        while beds or baths:
            if baths: interleaved.append(baths.pop(0))
            if beds: interleaved.append(beds.pop(0))
    else:
        while beds or baths:
            if beds: interleaved.append(beds.pop(0))
            if baths: interleaved.append(baths.pop(0))
            
    return public + others + interleaved


def _layout_wing(
    wing: Rect, rooms: List[Tuple[str, float]], is_top_wing: bool
) -> List[Room]:
    if not rooms:
        return []

    rooms = _sort_wing_rooms(rooms)

    # First, allocate minimum widths
    min_widths = [MIN_WIDTHS.get(rtype, 2.0) for rtype, _ in rooms]
    total_min = sum(min_widths)
    
    # Distribute the remaining width proportionally by weight
    remaining = max(0.0, wing.width - total_min)
    total_weight = sum(w for _, w in rooms) or 1.0

    placed: List[Room] = []
    cursor_x = wing.x

    for i, (rtype, weight) in enumerate(rooms):
        room_width = min_widths[i] + remaining * (weight / total_weight)
        bounds = Rect(cursor_x, wing.y, room_width, wing.height)
        placed.append(
            Room(
                type=rtype,
                label=_singular_label(rtype),
                bounds=bounds,
                openings=_build_openings(bounds, rtype, is_top_wing),
                furniture=_build_furniture(rtype, bounds),
            )
        )
        cursor_x += room_width

    return placed


def _build_landscaping(plot: Rect) -> List[SiteFeature]:
    features = [SiteFeature(FeatureType.GRASS, Rect(0, 0, plot.width, plot.height))]
    tree_d = max(plot.width * 0.05, 1.0)
    inset = tree_d
    corners = [
        (inset, inset),
        (plot.width - inset - tree_d, inset),
        (plot.width - inset - tree_d, plot.height - inset - tree_d),
    ]
    for tx, ty in corners:
        features.append(SiteFeature(FeatureType.TREE, Rect(tx, ty, tree_d, tree_d)))
    return features


def _build_parking(plot: Rect, count: int) -> List[SiteFeature]:
    if count <= 0:
        return []

    # User says 3m is enough in Kigali
    stall_w, stall_h = 2.5, 3.0
    gap = 0.5
    shown = min(count, 5)

    features: List[SiteFeature] = []
    # Place parking in the front setback (bottom of plot)
    start_x = 2.0
    start_y = plot.height - stall_h

    for i in range(shown):
        px = start_x + i * (stall_w + gap)
        features.append(
            SiteFeature(FeatureType.PARKING, Rect(px, start_y, stall_w, stall_h), "P")
        )

    return features


def build_floorplan(params: dict, compliance: dict) -> FloorPlan:
    plot_size = params.get("plot_size") or 600
    floors = params.get("floors") or 1
    parking = params.get("parking_spaces") or 0
    usage = params.get("usage") or "residential"
    rooms = params.get("rooms", {}) or {}

    plot_side = math.sqrt(plot_size)
    plot = Rect(0, 0, plot_side, plot_side)

    # Physical setbacks
    # Left = 2.0, Right = 2.0, Back (top) = 2.0, Front (bottom) = 3.0
    left_setback, right_setback = 2.0, 2.0
    back_setback, front_setback = 2.0, 3.0

    building_w = plot_side - left_setback - right_setback
    building_h = plot_side - back_setback - front_setback

    if building_w < 3.0 or building_h < 3.0:
        raise ValueError(f"Plot size ({plot_size} sqm) is too small to accommodate the required {left_setback}m side, {back_setback}m back, and {front_setback}m front setbacks.")

    building = Rect(left_setback, back_setback, building_w, building_h)

    room_items: List[Tuple[str, float]] = []
    for rtype, count in rooms.items():
        for _ in range(int(count)):
            room_items.append((rtype, STANDARD_ROOM_SIZES.get(rtype, 10)))

    top_rooms, bottom_rooms = _split_into_wings(room_items)

    # Validate room constraints
    def req_width(r_items):
        return sum(MIN_WIDTHS.get(rt, 2.0) for rt, _ in r_items)
    def req_depth(r_items):
        return max([MIN_DEPTHS.get(rt, 3.0) for rt, _ in r_items] + [0])

    top_w_req = req_width(top_rooms)
    bottom_w_req = req_width(bottom_rooms)
    top_d_req = req_depth(top_rooms) if top_rooms else 0
    bottom_d_req = req_depth(bottom_rooms) if bottom_rooms else 0

    corridor_h = CORRIDOR_HEIGHT if room_items else 0
    total_w_req = max(top_w_req, bottom_w_req)
    total_h_req = top_d_req + corridor_h + bottom_d_req

    if building_w < total_w_req or building_h < total_h_req:
        raise ValueError(f"The required rooms need a building of at least {total_w_req:.1f}x{total_h_req:.1f}m. After setbacks, plot only allows {building_w:.1f}x{building_h:.1f}m. Please reduce rooms or increase plot size.")

    placed_rooms: List[Room] = []
    corridor: SiteFeature | None = None

    if room_items:
        # Distribute remaining height
        rem_h = max(0.0, building_h - corridor_h)
        # Give top and bottom proportional to their required depth
        if top_d_req + bottom_d_req > 0:
            top_wing_h = rem_h * (top_d_req / (top_d_req + bottom_d_req))
            bottom_wing_h = rem_h - top_wing_h
        else:
            top_wing_h = bottom_wing_h = rem_h / 2

        top_wing = Rect(building.x, building.y, building.width, top_wing_h)
        corridor_rect = Rect(building.x, top_wing.bottom, building.width, corridor_h)
        bottom_wing = Rect(building.x, corridor_rect.bottom, building.width, bottom_wing_h)

        placed_rooms += _layout_wing(top_wing, top_rooms, is_top_wing=True)
        placed_rooms += _layout_wing(bottom_wing, bottom_rooms, is_top_wing=False)

        corridor = SiteFeature(FeatureType.CORRIDOR, corridor_rect, "Central Hallway")

    plan = FloorPlan(
        plot=plot,
        building=building,
        rooms=placed_rooms,
        plot_size_sqm=plot_size,
        floors=floors,
        usage=usage,
        parking_spaces=parking,
        wall_thickness=0.2
    )

    # Add Back Door to the Corridor
    if corridor:
        # Add a 1m single door at the right end of the corridor (Back door)
        back_door_len = min(1.0, corridor_rect.height)
        back_door_y = corridor_rect.y + (corridor_rect.height - back_door_len) / 2
        
        plan.rooms.append(Room(
            type="corridor_entrance",
            label="Exit",
            bounds=corridor_rect,
            openings=[
                Opening(OpeningType.DOOR, corridor_rect.right, back_door_y, back_door_len, Orientation.VERTICAL)
            ],
            furniture=[]
        ))

    plan.site_features += _build_landscaping(plot)
    if corridor is not None:
        plan.site_features.append(corridor)
    plan.site_features += _build_parking(plot, parking)

    # Path from entrance to parking
    if parking > 0 and corridor:
        plan.site_features.append(SiteFeature(FeatureType.PATH, Rect(building.x, corridor_rect.bottom, 1.5, plot.height - corridor_rect.bottom)))

    return plan
