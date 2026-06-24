"""Layout engine: turns extracted params + compliance into a FloorPlan model.

All computation here happens in real-world meters. The engine owns every
*geometric decision* (footprint sizing, the two-wing room split, where doors,
windows and furniture sit) but knows nothing about pixels, colors or PNGs.
"""

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

# Nominal floor area per room type, in square meters. Used both to size a room's
# share of a wing and (indirectly) to keep parity with the compliance validator.
STANDARD_ROOM_SIZES = {
    "bedrooms": 15,
    "bathrooms": 5,
    "kitchens": 10,
    "living_rooms": 20,
    "offices": 12,
}

# Standard furniture footprints in meters (width x height).
FURNITURE_SIZES = {
    "bed": (1.5, 2.0),
    "bathtub": (0.8, 1.6),
    "sofa": (2.0, 0.8),
    "desk": (1.2, 0.6),
}

# How much of the plot the building footprint occupies, as a fraction of the
# coverage limit. Mirrors the original 0.8 fudge factor that kept a setback.
FOOTPRINT_COVERAGE_FRACTION = 0.8

# Central corridor height as a fraction of the building depth.
CORRIDOR_DEPTH_FRACTION = 0.12

# Inset of furniture/openings from room walls, in meters.
ROOM_PADDING = 0.4


def _singular_label(rtype: str) -> str:
    """"bedrooms" -> "Bedroom"."""
    base = rtype[:-1] if rtype.endswith("s") else rtype
    return base.replace("_", " ").capitalize()


def _split_into_wings(
    room_items: List[Tuple[str, float]]
) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
    """Greedily balance rooms across the top and bottom wings by area weight."""
    top, bottom = [], []
    top_weight = bottom_weight = 0.0

    for rtype, weight in sorted(room_items, key=lambda x: x[1], reverse=True):
        if top_weight <= bottom_weight:
            top.append((rtype, weight))
            top_weight += weight
        else:
            bottom.append((rtype, weight))
            bottom_weight += weight

    return top, bottom


def _build_furniture(rtype: str, room: Rect) -> List[Furniture]:
    """Place the primary furniture item(s) for a room, in meters."""
    fx = room.x + ROOM_PADDING
    fy = room.y + ROOM_PADDING

    if rtype == "bedrooms":
        w, h = FURNITURE_SIZES["bed"]
        return [Furniture("bed", Rect(fx, fy, w, h))]
    if rtype == "bathrooms":
        w, h = FURNITURE_SIZES["bathtub"]
        return [Furniture("bathtub", Rect(fx, fy, w, h))]
    if rtype == "kitchens":
        # Counter spans the room width along the top wall.
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


def _build_openings(room: Rect, is_top_wing: bool) -> List[Opening]:
    """A window on the exterior wall and a door on the corridor-facing wall."""
    openings: List[Opening] = []

    win_len = min(1.2, room.width * 0.5)
    win_x = room.cx - win_len / 2
    door_len = min(0.9, room.width * 0.6)
    door_x = room.cx - door_len / 2

    # Exterior wall is the top edge for the top wing, bottom edge otherwise.
    exterior_y = room.y if is_top_wing else room.bottom
    corridor_y = room.bottom if is_top_wing else room.y

    openings.append(
        Opening(OpeningType.WINDOW, win_x, exterior_y, win_len, Orientation.HORIZONTAL)
    )
    openings.append(
        Opening(OpeningType.DOOR, door_x, corridor_y, door_len, Orientation.HORIZONTAL)
    )
    return openings


def _layout_wing(
    wing: Rect, rooms: List[Tuple[str, float]], is_top_wing: bool
) -> List[Room]:
    """Place rooms left-to-right within a wing, widths proportional to area."""
    total_weight = sum(w for _, w in rooms)
    if total_weight == 0:
        return []

    placed: List[Room] = []
    cursor_x = wing.x

    for rtype, weight in rooms:
        room_width = wing.width * (weight / total_weight)
        bounds = Rect(cursor_x, wing.y, room_width, wing.height)
        placed.append(
            Room(
                type=rtype,
                label=_singular_label(rtype),
                bounds=bounds,
                openings=_build_openings(bounds, is_top_wing),
                furniture=_build_furniture(rtype, bounds),
            )
        )
        cursor_x += room_width

    return placed


def _build_landscaping(plot: Rect) -> List[SiteFeature]:
    """Base grass and a few corner trees."""
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


def _build_parking(
    plot: Rect, building: Rect, corridor: Rect, count: int
) -> List[SiteFeature]:
    """Up to five parking stalls along the bottom-left, plus an entrance path."""
    if count <= 0:
        return []

    stall_w, stall_h = 2.5, 5.0
    gap = 0.5
    shown = min(count, 5)

    features: List[SiteFeature] = []
    start_x = max(plot.width * 0.02, 0.5)
    start_y = plot.height - stall_h - max(plot.height * 0.02, 0.5)

    for i in range(shown):
        px = start_x + i * (stall_w + gap)
        features.append(
            SiteFeature(FeatureType.PARKING, Rect(px, start_y, stall_w, stall_h), "P")
        )

    # Path from the parking lane to the building corridor.
    path_x0 = start_x + shown * (stall_w + gap)
    if corridor is not None and building.x > path_x0:
        features.append(
            SiteFeature(
                FeatureType.PATH,
                Rect(
                    path_x0,
                    corridor.y + corridor.height * 0.15,
                    building.x - path_x0,
                    corridor.height * 0.7,
                ),
            )
        )

    return features


def build_floorplan(params: dict, compliance: dict) -> FloorPlan:
    """Compute the full FloorPlan geometry from extracted params + compliance."""
    plot_size = params.get("plot_size") or 500
    floors = params.get("floors") or 1
    parking = params.get("parking_spaces") or 0
    usage = params.get("usage") or "residential"
    rooms = params.get("rooms", {}) or {}

    coverage_limit = compliance.get("metrics", {}).get("site_coverage_limit", 0.6)

    # Plot is modelled as a square with the requested area.
    plot_side = math.sqrt(plot_size)
    plot = Rect(0, 0, plot_side, plot_side)

    # Centered building footprint.
    footprint_side = plot_side * math.sqrt(coverage_limit) * FOOTPRINT_COVERAGE_FRACTION
    building = Rect(
        (plot_side - footprint_side) / 2,
        (plot_side - footprint_side) / 2,
        footprint_side,
        footprint_side,
    )

    # Flatten the room counts into individual room instances.
    room_items: List[Tuple[str, float]] = []
    for rtype, count in rooms.items():
        for _ in range(int(count)):
            room_items.append((rtype, STANDARD_ROOM_SIZES.get(rtype, 10)))

    placed_rooms: List[Room] = []
    corridor: SiteFeature | None = None

    if room_items:
        corridor_h = building.height * CORRIDOR_DEPTH_FRACTION
        wing_h = (building.height - corridor_h) / 2

        top_wing = Rect(building.x, building.y, building.width, wing_h)
        corridor_rect = Rect(
            building.x, building.y + wing_h, building.width, corridor_h
        )
        bottom_wing = Rect(
            building.x, corridor_rect.bottom, building.width, wing_h
        )

        top_rooms, bottom_rooms = _split_into_wings(room_items)
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
    )

    # Site features: landscaping, then corridor (under rooms in z-order is fine
    # since the renderer draws the building base first), then parking.
    plan.site_features += _build_landscaping(plot)
    if corridor is not None:
        plan.site_features.append(corridor)
    plan.site_features += _build_parking(
        plot, building, corridor.bounds if corridor else None, parking
    )

    return plan
