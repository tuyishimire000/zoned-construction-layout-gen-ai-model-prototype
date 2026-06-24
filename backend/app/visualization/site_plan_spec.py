"""Static, hand-authored site plan, defined entirely in named variables (meters).

This is the "static first" phase: a realistic single-family layout written out by
hand so we can tune how the drawing *feels* without any NLP/parsing in the way.
It produces the same `FloorPlan` model the dynamic engine produces, so once this
looks right, going dynamic is just swapping `build_site_plan()` for
`build_floorplan(params, compliance)` — same model, same renderers (PNG + DXF).

Coordinate system (matches the model): origin top-left, Y increases downward, so
the street/front of the lot is at the BOTTOM (large Y) and the rear is at the TOP.
"""

from .model import (
    FloorPlan,
    Rect,
    Room,
    Opening,
    OpeningType,
    Orientation,
    SiteFeature,
    FeatureType,
)
from .layout_engine import _build_furniture

# --- Plot & setbacks ------------------------------------------------------ #
PLOT_W = 22.0          # property width  (m)
PLOT_D = 26.0          # property depth  (m)

SETBACK_FRONT = 6.0    # street (bottom) → building
SETBACK_SIDE = 4.0     # side boundary → building
SETBACK_REAR = 9.0     # rear (top) → building

# --- Building footprint --------------------------------------------------- #
BUILDING_W = 14.0
BUILDING_D = 11.0
BX = SETBACK_SIDE                      # 4.0  → centered: (22-14)/2
BY = SETBACK_REAR                      # 9.0
BUILDING = Rect(BX, BY, BUILDING_W, BUILDING_D)   # x[4,18], y[9,20]

WALL_THICKNESS = 0.2

# --- Driveway ------------------------------------------------------------- #
DRIVEWAY = Rect(5.0, BUILDING.bottom, 3.5, PLOT_D - BUILDING.bottom)  # front yard

# --- Rooms ---------------------------------------------------------------- #
# (category key, label, x, y, w, h). The category key drives color + furniture.
ROOM_DEFS = [
    ("living_rooms", "Living Room",  4.0, 14.0,  7.0, 6.0),   # front-left
    ("kitchens",     "Kitchen",     11.0, 14.0,  7.0, 6.0),   # front-right
    ("bedrooms",     "Bedroom 1",    4.0,  9.0,  5.5, 5.0),   # rear-left
    ("bathrooms",    "Bathroom",     9.5,  9.0,  3.0, 5.0),   # rear-middle
    ("bedrooms",     "Bedroom 2",   12.5,  9.0,  5.5, 5.0),   # rear-right
]

# Openings keyed by room label. Doors carry a swing; windows do not.
# Horizontal wall → swing "up"/"down"; vertical wall → swing "left"/"right".
W = OpeningType.WINDOW
D = OpeningType.DOOR
H = Orientation.HORIZONTAL
V = Orientation.VERTICAL

OPENINGS = {
    "Living Room": [
        Opening(W, 7.5, 20.0, 1.5, H),                       # front window
        Opening(W, 4.0, 16.0, 1.5, V),                       # left window
        Opening(D, 5.5, 20.0, 0.9, H, swing="up"),           # front entry
        Opening(D, 11.0, 15.0, 0.9, V, swing="right"),       # → kitchen
    ],
    "Kitchen": [
        Opening(W, 13.5, 20.0, 1.5, H),                      # front window
        Opening(W, 18.0, 16.0, 1.5, V),                      # right window
    ],
    "Bedroom 1": [
        Opening(W, 5.5, 9.0, 1.5, H),                        # rear window
        Opening(W, 4.0, 10.5, 1.2, V),                       # left window
        Opening(D, 5.0, 14.0, 0.9, H, swing="up"),           # door from living
    ],
    "Bathroom": [
        Opening(W, 10.5, 9.0, 0.8, H),                       # rear window
        Opening(D, 10.6, 14.0, 0.8, H, swing="up"),          # door from living
    ],
    "Bedroom 2": [
        Opening(W, 14.0, 9.0, 1.5, H),                       # rear window
        Opening(W, 18.0, 10.5, 1.2, V),                      # right window
        Opening(D, 16.0, 14.0, 0.9, H, swing="up"),          # door from kitchen
    ],
}

# --- Landscaping ---------------------------------------------------------- #
TREES = [Rect(1.5, 1.5, 1.4, 1.4), Rect(PLOT_W - 2.9, 1.5, 1.4, 1.4)]


def build_site_plan() -> FloorPlan:
    """Assemble the hand-authored variables above into a FloorPlan model."""
    rooms = []
    for rtype, label, x, y, w, h in ROOM_DEFS:
        bounds = Rect(x, y, w, h)
        rooms.append(
            Room(
                type=rtype,
                label=label,
                bounds=bounds,
                openings=OPENINGS.get(label, []),
                furniture=_build_furniture(rtype, bounds),
            )
        )

    plot = Rect(0, 0, PLOT_W, PLOT_D)
    features = [SiteFeature(FeatureType.GRASS, plot)]
    features += [SiteFeature(FeatureType.TREE, t) for t in TREES]
    features.append(SiteFeature(FeatureType.DRIVEWAY, DRIVEWAY, "DRIVEWAY"))

    return FloorPlan(
        plot=plot,
        building=BUILDING,
        rooms=rooms,
        site_features=features,
        wall_thickness=WALL_THICKNESS,
        plot_size_sqm=PLOT_W * PLOT_D,
        floors=1,
        usage="residential",
        parking_spaces=0,
    )
