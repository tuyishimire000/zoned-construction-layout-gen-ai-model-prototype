"""Geometry model for a generated site plan.

This is the single source of truth for a layout. Everything here is expressed in
**real-world meters**, with the origin (0, 0) at the top-left of the plot and the
Y axis pointing *down* (screen convention). Renderers are responsible for mapping
these meters onto their own output space (pixels for PNG, drawing units for DXF).

Keeping the geometry decoupled from any particular output format is what lets the
same model feed the current PNG renderer today and a DXF/JSON exporter later.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


@dataclass
class Rect:
    """An axis-aligned rectangle in meters (top-left origin, Y-down)."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2

    @property
    def area(self) -> float:
        return self.width * self.height


class Orientation(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class OpeningType(str, Enum):
    DOOR = "door"
    WINDOW = "window"


@dataclass
class Opening:
    """A door or window, modelled as a segment lying on a wall.

    For doors, `swing` and `hinge_at_start` describe how the leaf opens so the
    renderer can draw a leaf line + swing arc. `swing` is the direction the leaf
    rotates toward, relative to the wall:
      - horizontal wall: "up" or "down"
      - vertical wall:   "left" or "right"
    `hinge_at_start` puts the hinge at (x, y); otherwise at the far end of the
    segment. Windows leave both as their defaults.
    """

    type: OpeningType
    x: float
    y: float
    length: float
    orientation: Orientation = Orientation.HORIZONTAL
    swing: Optional[str] = None
    hinge_at_start: bool = True


@dataclass
class Furniture:
    """A piece of furniture, anchored at its top-left corner in meters.

    `type` is a stable key (e.g. "bed", "sofa") that renderers map to a glyph.
    """

    type: str
    bounds: Rect


@dataclass
class Room:
    """A single room/space within the building footprint."""

    type: str  # category key, e.g. "bedrooms" (matches the extractor/validator)
    label: str  # human-readable, e.g. "Bedroom"
    bounds: Rect
    openings: List[Opening] = field(default_factory=list)
    furniture: List[Furniture] = field(default_factory=list)


class FeatureType(str, Enum):
    GRASS = "grass"
    TREE = "tree"
    CORRIDOR = "corridor"
    PARKING = "parking"
    PATH = "path"
    DRIVEWAY = "driveway"


@dataclass
class SiteFeature:
    """A non-room element of the site (landscaping, circulation, parking)."""

    type: FeatureType
    bounds: Rect
    label: Optional[str] = None


@dataclass
class FloorPlan:
    """Complete geometric description of a generated layout, in meters."""

    plot: Rect
    building: Rect
    rooms: List[Room] = field(default_factory=list)
    site_features: List[SiteFeature] = field(default_factory=list)

    # Wall thickness in meters, used by renderers to draw double-line walls.
    wall_thickness: float = 0.2

    # Project metadata, carried through for labels/title block.
    plot_size_sqm: float = 0.0
    floors: int = 1
    usage: str = "residential"
    parking_spaces: int = 0
