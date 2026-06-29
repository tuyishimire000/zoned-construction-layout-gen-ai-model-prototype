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
from typing import List, Optional, Tuple


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
    PASSAGE = "passage"


@dataclass
class Opening:
    type: OpeningType
    x: float
    y: float
    length: float
    orientation: Orientation = Orientation.HORIZONTAL
    swing: Optional[str] = None
    hinge_at_start: bool = True
    style: str = "swing"


@dataclass
class Furniture:
    type: str
    bounds: Rect


@dataclass
class Room:
    """A single room/space within the building footprint."""

    type: str
    label: str
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
    """A non-room element of the site."""

    type: FeatureType
    bounds: Rect
    label: Optional[str] = None
    points: Optional[List[Tuple[float, float]]] = None


@dataclass
class FloorPlan:
    """Complete geometric description of a generated layout, in meters."""

    plot: Rect
    building: Rect
    rooms: List[Room] = field(default_factory=list)
    annex_building: Optional[Rect] = None
    annex_rooms: List[Room] = field(default_factory=list)
    site_features: List[SiteFeature] = field(default_factory=list)

    wall_thickness: float = 0.2
    score: float = 0.0

    plot_size_sqm: float = 0.0
    floors: int = 1
    usage: str = "residential"
    parking_spaces: int = 0
