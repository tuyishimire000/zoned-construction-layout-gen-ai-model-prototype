"""HouseSketch: turn typed house parameters into a real PNG + SVG floor sketch.

Design goals (deliberately small and self-contained):
  * Input is plain typed data: plot dimensions + how many of each room.
  * Inputs are validated against the plot (setbacks, buildable area, min sizes)
    and raise a clear error if the house cannot reasonably fit.
  * Geometry is computed ONCE in meters, then drawn through a tiny `_Surface`
    abstraction so the PNG (Pillow) and SVG (hand-written) outputs are identical.
  * No external services. Only Pillow is required (for PNG); SVG is pure strings.

Layout archetype (typical rectangular African house): a central corridor runs
front-to-back with private rooms (bedrooms / bathrooms / kitchen) on either side,
and a full-width public band (living + dining) across the front.

Coordinate system: origin top-left, X right, Y down (screen convention), meters.
The front of the house (street side) is the BOTTOM (large Y).

Run it directly to produce sample files:
    python -m app.sketch.house_sketch
"""

from __future__ import annotations

import io
import math
import html
import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union

from PIL import Image, ImageDraw, ImageFont


# --------------------------------------------------------------------------- #
# Room catalogue
# --------------------------------------------------------------------------- #


class RoomType(str, Enum):
    BEDROOM = "bedroom"
    BATHROOM = "bathroom"
    KITCHEN = "kitchen"
    LIVING_ROOM = "living_room"
    DINING = "dining"
    OFFICE = "office"
    CORRIDOR = "corridor"


# Rooms that form the full-width public band at the front.
PUBLIC_TYPES = {RoomType.LIVING_ROOM, RoomType.DINING}

# Desired floor area (m²) and minimum side lengths (m) per room type.
ROOM_AREA = {
    RoomType.BEDROOM: 14.0,
    RoomType.BATHROOM: 5.0,
    RoomType.KITCHEN: 11.0,
    RoomType.LIVING_ROOM: 22.0,
    RoomType.DINING: 12.0,
    RoomType.OFFICE: 10.0,
    RoomType.CORRIDOR: 6.0,
}
ROOM_MIN_SIDE = {
    RoomType.BEDROOM: 2.6,
    RoomType.BATHROOM: 1.5,
    RoomType.KITCHEN: 2.2,
    RoomType.LIVING_ROOM: 3.0,
    RoomType.DINING: 2.4,
    RoomType.OFFICE: 2.0,
    RoomType.CORRIDOR: 1.0,
}
# Professional look: rooms are white; circulation is a faint grey.
ROOM_COLOR = {rt: "#FFFFFF" for rt in RoomType}
ROOM_COLOR[RoomType.CORRIDOR] = "#F2F3F5"

# Drawing convention / legend. Single source of truth for the colour language.
#   wall states : added (red), removed (blue), remaining (black)
#   unit fills  : first unit (mint), second unit (light yellow)
#   openings    : windows are orange with black jamb caps
LEGEND = {
    "added_wall": "#E53935",  # red
    "removed_wall": "#1E88E5",  # blue
    "remaining_wall": "#111111",  # black
    "unit_1": "#B9F6CA",  # mint green
    "unit_2": "#FFF59D",  # light yellow
    "window": "#EF7C00",  # orange
}

# Accept loose synonyms so callers can pass "bed", "bathrooms", "lounge", etc.
_ALIASES = {
    "bed": RoomType.BEDROOM,
    "bedroom": RoomType.BEDROOM,
    "bedrooms": RoomType.BEDROOM,
    "bath": RoomType.BATHROOM,
    "bathroom": RoomType.BATHROOM,
    "bathrooms": RoomType.BATHROOM,
    "wc": RoomType.BATHROOM,
    "toilet": RoomType.BATHROOM,
    "kitchen": RoomType.KITCHEN,
    "kitchens": RoomType.KITCHEN,
    "living": RoomType.LIVING_ROOM,
    "living_room": RoomType.LIVING_ROOM,
    "living_rooms": RoomType.LIVING_ROOM,
    "lounge": RoomType.LIVING_ROOM,
    "sitting": RoomType.LIVING_ROOM,
    "dining": RoomType.DINING,
    "dining_room": RoomType.DINING,
    "office": RoomType.OFFICE,
    "offices": RoomType.OFFICE,
    "study": RoomType.OFFICE,
    "corridor": RoomType.CORRIDOR,
    "hall": RoomType.CORRIDOR,
    "hallway": RoomType.CORRIDOR,
    "passage": RoomType.CORRIDOR,
}


def _normalize(rtype: Union[str, RoomType]) -> RoomType:
    if isinstance(rtype, RoomType):
        return rtype
    key = str(rtype).strip().lower().replace(" ", "_")
    if key not in _ALIASES:
        raise SketchValidationError(
            f"Unknown room type {rtype!r}. Known: {sorted(set(_ALIASES))}"
        )
    return _ALIASES[key]


# --------------------------------------------------------------------------- #
# Geometry primitives
# --------------------------------------------------------------------------- #


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass
class Door:
    leaf: Tuple[Tuple[float, float], Tuple[float, float]]  # hinge -> leaf tip
    arc: List[Tuple[float, float]]  # swing polyline


@dataclass
class Window:
    p0: Tuple[float, float]
    p1: Tuple[float, float]


@dataclass
class Room:
    """A room after layout: its computed geometry plus a link to its spec."""

    type: RoomType
    label: str
    rect: Optional[Rect] = None
    doors: List[Door] = field(default_factory=list)
    windows: List[Window] = field(default_factory=list)
    door_walls: Set[str] = field(default_factory=set)
    id: str = ""
    spec: Optional["RoomSpec"] = None


class SketchValidationError(ValueError):
    """Raised when the requested rooms cannot reasonably fit the plot."""


@dataclass
class RoomSpec:
    """Declarative description of one room the caller wants.

    Only ``type`` is required; every other field is optional and falls back to
    per-type defaults or the layout engine's own decisions when omitted. This is
    the INPUT model — the computed geometry ends up on the matching `Room`.

    Sizing:      ``area`` wins; else ``width * depth`` if both given; else the
                 per-type default. ``min_width`` / ``min_depth`` override the
                 per-type minimums used for validation and column stacking.
    Placement:   ``zone`` forces "public" (front band) or "private" (rear); if
                 None it is inferred from the room type. ``adjacent_to`` lists
                 the ids/names this room should border (drives doors). Position
                 is given ONE of these ways:
                   * ``position`` = explicit (x, y) meters from the building corner
                   * one of ``east_of`` / ``west_of`` / ``north_of`` / ``south_of``
                     = an anchor room id; this room is placed flush against that
                     side of the anchor, sharing a wall (no coordinates needed).
                 ``align`` ("start"/"center"/"end") and ``offset`` (m) slide the
                 room along the shared wall; ``gap`` (m) leaves a gap instead of
                 sharing. When a relatively-placed room omits the cross dimension
                 (depth for east/west, width for north/south) it defaults to the
                 anchor's, giving a full shared wall.
    Openings:    ``entrances`` lists exterior walls to cut an entry door into
                 ("left"/"right"/"top"/"bottom"). ``windows`` = False suppresses
                 the automatic exterior windows for this room.
    """

    type: Union[str, "RoomType"]
    name: Optional[str] = None
    id: Optional[str] = None

    width: Optional[float] = None
    depth: Optional[float] = None
    area: Optional[float] = None
    min_width: Optional[float] = None
    min_depth: Optional[float] = None

    zone: Optional[str] = None
    adjacent_to: List[str] = field(default_factory=list)
    position: Optional[Tuple[float, float]] = None

    # Relative placement (alternative to `position`): one anchor room id.
    east_of: Optional[str] = None
    west_of: Optional[str] = None
    north_of: Optional[str] = None
    south_of: Optional[str] = None
    align: str = "start"       # start | center | end, along the shared wall
    offset: float = 0.0        # slide along the shared wall (meters)
    gap: float = 0.0           # gap from the anchor instead of a shared wall

    entrances: List[str] = field(default_factory=list)
    windows: Optional[bool] = None

    priority: int = 0
    notes: str = ""

    _WALLS = ("left", "right", "top", "bottom")
    _RELATIONS = ("east_of", "west_of", "north_of", "south_of")

    def __post_init__(self):
        self.type = _normalize(self.type)
        if self.zone not in (None, "public", "private"):
            raise SketchValidationError(
                f"zone must be 'public', 'private' or None, got {self.zone!r}"
            )
        for w in self.entrances:
            if w not in self._WALLS:
                raise SketchValidationError(
                    f"entrance wall must be one of {self._WALLS}, got {w!r}"
                )
        if self.align not in ("start", "center", "end"):
            raise SketchValidationError(
                f"align must be 'start', 'center' or 'end', got {self.align!r}"
            )
        set_rel = [r for r in self._RELATIONS if getattr(self, r)]
        if len(set_rel) > 1:
            raise SketchValidationError(
                f"a room can use only one of {self._RELATIONS}, got {set_rel}"
            )
        if set_rel and self.position is not None:
            raise SketchValidationError(
                "use either `position` or a relative direction, not both."
            )

    def anchor(self) -> Tuple[Optional[str], Optional[str]]:
        """(anchor_id, relation) if placed relatively, else (None, None)."""
        for rel in self._RELATIONS:
            v = getattr(self, rel)
            if v:
                return v, rel
        return None, None

    def target_area(self) -> float:
        if self.area is not None:
            return self.area
        if self.width is not None and self.depth is not None:
            return self.width * self.depth
        return ROOM_AREA[self.type]


# --------------------------------------------------------------------------- #
# The class
# --------------------------------------------------------------------------- #


class HouseSketch:
    """Build and render a single-storey house sketch from typed parameters.

    Example
    -------
    >>> sketch = HouseSketch(
    ...     plot_width=16, plot_depth=18,
    ...     rooms={"bedroom": 3, "bathroom": 1, "kitchen": 1,
    ...            "living_room": 1, "dining": 1},
    ...     setback=3.0,
    ... )
    >>> png_bytes = sketch.to_png("house.png")
    >>> svg_text  = sketch.to_svg("house.svg")
    """

    def __init__(
        self,
        plot_width: float,
        plot_depth: float,
        rooms: Union[
            Dict[Union[str, RoomType], int],
            List[Union[str, RoomType, "RoomSpec", dict]],
        ],
        *,
        setback: float = 3.0,
        circulation: float = 1.12,
        wall_thickness: float = 0.3,
        title: str = "PROPOSED HOUSE SKETCH",
    ):
        if plot_width <= 0 or plot_depth <= 0:
            raise SketchValidationError("Plot dimensions must be positive.")
        if setback < 0 or setback * 2 >= min(plot_width, plot_depth):
            raise SketchValidationError(
                f"Setback {setback} m leaves no buildable area on a "
                f"{plot_width}x{plot_depth} m plot."
            )

        self.plot = Rect(0, 0, float(plot_width), float(plot_depth))
        self.setback = float(setback)
        self.circulation = float(circulation)
        self.wall = float(wall_thickness)
        self.title = title

        self.footprint = Rect(
            setback, setback, plot_width - 2 * setback, plot_depth - 2 * setback
        )
        self.specs: List[RoomSpec] = self._coerce_specs(rooms)
        self.rooms: List[Room] = self._build_rooms(self.specs)
        if not self.rooms:
            raise SketchValidationError("At least one room is required.")

        # Manual placement kicks in when any room carries an explicit position
        # or a relative direction (east_of/west_of/north_of/south_of).
        self.manual = any(
            s.position is not None or s.anchor()[0] for s in self.specs
        )

        self.corridor: Optional[Room] = None
        # Wall segments left open as passages (corridor mouth, open-plan, etc.).
        self.openings: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        # Spatial model: room id -> [{neighbor, wall, segment}], computed from
        # the placed geometry so the class understands where every element sits.
        self.adjacency: Dict[str, List[dict]] = {}

        self.validate()  # raises on hard failures
        self._layout()  # fills room.rect + corridor + doors + windows

    # -- input handling ----------------------------------------------------- #

    @classmethod
    def from_area(cls, plot_size: float, rooms, *, ratio: float = 1.2, **kw):
        """Convenience: build from a plot AREA (m²) and a depth:width `ratio`."""
        if plot_size <= 0:
            raise SketchValidationError("plot_size must be positive.")
        width = math.sqrt(plot_size / ratio)
        depth = width * ratio
        return cls(width, depth, rooms, **kw)

    @staticmethod
    def _coerce_specs(rooms) -> List["RoomSpec"]:
        """Normalize any accepted `rooms` form into a list of RoomSpec."""
        specs: List[RoomSpec] = []
        if isinstance(rooms, dict):
            for rtype, n in rooms.items():
                for _ in range(int(n)):
                    specs.append(RoomSpec(type=rtype))
        else:
            for item in rooms:
                if isinstance(item, RoomSpec):
                    specs.append(item)
                elif isinstance(item, dict):
                    specs.append(RoomSpec(**item))
                else:  # bare "bedroom" / RoomType.BEDROOM
                    specs.append(RoomSpec(type=item))
        return specs

    @staticmethod
    def _slug(text: str) -> str:
        return "-".join(text.lower().split())

    def _build_rooms(self, specs: List["RoomSpec"]) -> List[Room]:
        """Turn specs into Rooms, assigning default labels + unique ids."""
        totals: Dict[RoomType, int] = {}
        for s in specs:
            totals[s.type] = totals.get(s.type, 0) + 1

        seen: Dict[RoomType, int] = {}
        used_ids: Set[str] = set()
        rooms: List[Room] = []
        for s in specs:
            seen[s.type] = seen.get(s.type, 0) + 1
            if s.name:
                label = s.name
            else:
                base = s.type.value.replace("_", " ").title()
                label = f"{base} {seen[s.type]}" if totals[s.type] > 1 else base

            rid = s.id or self._slug(label)
            base_id, k = rid, 2
            while rid in used_ids:
                rid, k = f"{base_id}-{k}", k + 1
            used_ids.add(rid)
            s.id = rid  # backfill so adjacency can reference auto-generated ids

            rooms.append(Room(type=s.type, label=label, id=rid, spec=s))
        return rooms

    # -- per-room effective values (spec overrides, else per-type defaults) -- #

    def _area(self, room: Room) -> float:
        return room.spec.target_area() if room.spec else ROOM_AREA[room.type]

    def _min_w(self, room: Room) -> float:
        if room.spec and room.spec.min_width is not None:
            return room.spec.min_width
        return ROOM_MIN_SIDE[room.type]

    def _min_d(self, room: Room) -> float:
        if room.spec and room.spec.min_depth is not None:
            return room.spec.min_depth
        return ROOM_MIN_SIDE[room.type]

    def _is_public(self, room: Room) -> bool:
        z = room.spec.zone if room.spec else None
        if z == "public":
            return True
        if z == "private":
            return False
        return room.type in PUBLIC_TYPES

    @property
    def all_rooms(self) -> List[Room]:
        return self.rooms + ([self.corridor] if self.corridor else [])

    # -- validation --------------------------------------------------------- #

    def required_area(self) -> float:
        """Desired total floor area incl. a circulation allowance."""
        return sum(self._area(r) for r in self.rooms) * self.circulation

    def validate(self) -> None:
        """Raise SketchValidationError if the rooms cannot fit the plot."""
        # Auto layout packs rooms with a circulation allowance; manual layout
        # is validated exactly (inside footprint, no overlaps) during placement.
        if not self.manual:
            buildable = self.footprint.area
            needed = self.required_area()
            if needed > buildable + 1e-6:
                raise SketchValidationError(
                    f"Rooms need about {needed:.0f} m² (incl. circulation) but the "
                    f"buildable footprint is only {buildable:.0f} m² "
                    f"({self.plot.area:.0f} m² plot minus {self.setback} m setbacks). "
                    f"Reduce rooms, shrink setbacks, or enlarge the plot."
                )

        # Adjacency references must resolve to a known room id or label.
        ids = {r.id for r in self.rooms}
        names = {r.label for r in self.rooms}
        for r in self.rooms:
            for ref in r.spec.adjacent_to if r.spec else []:
                if ref not in ids and ref not in names:
                    raise SketchValidationError(
                        f"{r.label!r} lists an unknown adjacent room {ref!r}."
                    )

    # -- layout dispatch ---------------------------------------------------- #

    def _layout(self) -> None:
        """Place rooms, then compute the adjacency graph from the geometry.

        If any room carries an explicit `position`, use manual placement; else
        fall back to the automatic central-corridor archetype.
        """
        if self.manual:
            self._layout_manual()
        else:
            self._layout_auto()
        self.adjacency = self._compute_adjacency()
        # Windows are placed last: they sit on exterior (non-shared) wall edges,
        # which we only know once every room is placed and adjacency is computed.
        self._place_windows()

    def _resolve(self, ref: str) -> Optional[Room]:
        for r in self.rooms:
            if r.id == ref or r.label == ref:
                return r
        return None

    def neighbors_of(self, room_id: str) -> List[str]:
        """Ids of the rooms that share a wall with the given room."""
        return [e["neighbor"] for e in self.adjacency.get(room_id, [])]

    def _compute_adjacency(self) -> Dict[str, List[dict]]:
        """Work out which rooms share a wall, and the shared segment (meters)."""
        rooms = [r for r in self.all_rooms if r.rect]
        adj: Dict[str, List[dict]] = {r.id: [] for r in rooms}
        eps = max(self.wall, 0.05) * 1.5   # collinearity tolerance
        min_overlap = 0.4                  # ignore mere corner touches

        for i, a in enumerate(rooms):
            for b in rooms[i + 1 :]:
                ra, rb = a.rect, b.rect
                seg = wall_a = wall_b = None
                if abs(ra.right - rb.x) < eps:          # a is left of b
                    lo, hi = max(ra.y, rb.y), min(ra.bottom, rb.bottom)
                    if hi - lo > min_overlap:
                        seg = ((ra.right, lo), (ra.right, hi))
                        wall_a, wall_b = "right", "left"
                elif abs(rb.right - ra.x) < eps:        # a is right of b
                    lo, hi = max(ra.y, rb.y), min(ra.bottom, rb.bottom)
                    if hi - lo > min_overlap:
                        seg = ((ra.x, lo), (ra.x, hi))
                        wall_a, wall_b = "left", "right"
                elif abs(ra.bottom - rb.y) < eps:       # a is above b
                    lo, hi = max(ra.x, rb.x), min(ra.right, rb.right)
                    if hi - lo > min_overlap:
                        seg = ((lo, ra.bottom), (hi, ra.bottom))
                        wall_a, wall_b = "bottom", "top"
                elif abs(rb.bottom - ra.y) < eps:       # a is below b
                    lo, hi = max(ra.x, rb.x), min(ra.right, rb.right)
                    if hi - lo > min_overlap:
                        seg = ((lo, ra.y), (hi, ra.y))
                        wall_a, wall_b = "top", "bottom"
                if seg:
                    adj[a.id].append({"neighbor": b.id, "wall": wall_a, "segment": seg})
                    adj[b.id].append({"neighbor": a.id, "wall": wall_b, "segment": seg})
        return adj

    # -- manual placement (explicit positions or relative directions) ------- #

    @staticmethod
    def _aligned(anchor_start, anchor_len, room_len, align, offset):
        if align == "center":
            base = anchor_start + (anchor_len - room_len) / 2
        elif align == "end":
            base = anchor_start + anchor_len - room_len
        else:  # start
            base = anchor_start
        return base + offset

    def _place_relative(self, room: Room, anchor: Room, relation: str) -> Rect:
        """Rect for a room placed against one side of an already-placed anchor.

        The cross dimension defaults to the anchor's (full shared wall) when the
        spec leaves it out; the along dimension comes from the spec or its area.
        """
        s, a = room.spec, anchor.rect
        if relation in ("east_of", "west_of"):
            h = s.depth if s.depth is not None else a.h
            w = s.width if s.width is not None else self._area(room) / h
            y = self._aligned(a.y, a.h, h, s.align, s.offset)
            x = a.right + s.gap if relation == "east_of" else a.x - w - s.gap
            return Rect(x, y, w, h)
        else:  # north_of / south_of
            w = s.width if s.width is not None else a.w
            h = s.depth if s.depth is not None else self._area(room) / w
            x = self._aligned(a.x, a.w, w, s.align, s.offset)
            y = a.bottom + s.gap if relation == "south_of" else a.y - h - s.gap
            return Rect(x, y, w, h)

    def _resolve_positions(self) -> None:
        """Turn explicit positions + relative directions into absolute rects.

        Absolute-position rooms are placed first; relative rooms resolve once
        their anchor is placed (dependency order). Cycles / dangling anchors and
        rooms with no position at all are reported.
        """
        fb = self.footprint
        pending = list(self.rooms)
        progressed = True
        while pending and progressed:
            progressed = False
            for r in pending[:]:
                s = r.spec
                anchor_id, relation = s.anchor()
                if s.position is not None:
                    w = s.width if s.width is not None else self._area(r) ** 0.5
                    h = s.depth if s.depth is not None else self._area(r) / w
                    r.rect = Rect(fb.x + s.position[0], fb.y + s.position[1], w, h)
                    pending.remove(r)
                    progressed = True
                elif anchor_id is None:
                    raise SketchValidationError(
                        f"{r.label!r}: needs a position or a relative direction "
                        f"(east_of / west_of / north_of / south_of)."
                    )
                else:
                    anchor = self._resolve(anchor_id)
                    if anchor is None:
                        raise SketchValidationError(
                            f"{r.label!r} is placed {relation} unknown room "
                            f"{anchor_id!r}."
                        )
                    if anchor.rect is None:
                        continue  # anchor not placed yet — try next pass
                    r.rect = self._place_relative(r, anchor, relation)
                    pending.remove(r)
                    progressed = True

        if pending:
            names = ", ".join(repr(r.label) for r in pending)
            raise SketchValidationError(
                f"Relative placement could not resolve {names} — check for a "
                f"cycle or an anchor that is itself unplaced."
            )

    def _layout_manual(self) -> None:
        """Place rooms (by explicit position OR relative direction), then openings.

        Positions are meters from the building's top-left interior corner. Rooms
        may not overlap or spill outside the footprint (gaps/courtyards are ok).
        """
        fb = self.footprint
        self._resolve_positions()

        # Inside the footprint?
        for r in self.rooms:
            rc = r.rect
            if (
                rc.x < fb.x - 1e-6
                or rc.y < fb.y - 1e-6
                or rc.right > fb.right + 1e-6
                or rc.bottom > fb.bottom + 1e-6
            ):
                raise SketchValidationError(
                    f"{r.label!r} at {r.spec.position} ({rc.w}x{rc.h} m) extends "
                    f"outside the {fb.w:.1f}x{fb.h:.1f} m building footprint."
                )

        # Overlapping?
        for i, a in enumerate(self.rooms):
            for b in self.rooms[i + 1 :]:
                ox = min(a.rect.right, b.rect.right) - max(a.rect.x, b.rect.x)
                oy = min(a.rect.bottom, b.rect.bottom) - max(a.rect.y, b.rect.y)
                if ox > 1e-6 and oy > 1e-6:
                    raise SketchValidationError(
                        f"{a.label!r} and {b.label!r} overlap."
                    )

        adj = self._compute_adjacency()

        # Doors between rooms declared adjacent (must actually share a wall).
        inward = {"left": (1, 0), "right": (-1, 0), "top": (0, 1), "bottom": (0, -1)}
        done: Set[frozenset] = set()
        for r in self.rooms:
            for ref in r.spec.adjacent_to if r.spec else []:
                other = self._resolve(ref)
                if other is None or frozenset((r.id, other.id)) in done:
                    continue
                link = next(
                    (e for e in adj[r.id] if e["neighbor"] == other.id), None
                )
                if link is None:
                    raise SketchValidationError(
                        f"{r.label!r} is declared adjacent to {other.label!r} but "
                        f"they don't share a wall as positioned."
                    )
                done.add(frozenset((r.id, other.id)))
                self._door_on_segment(r, link["wall"], link["segment"])

        # Exterior entry doors (windows are placed later, in the dispatcher).
        for r in self.rooms:
            for w in r.spec.entrances if r.spec else []:
                self._side_door(r, w, into=inward[w])

    def _door_on_segment(self, room: Room, wall: str, segment) -> None:
        """Place a door centred on a shared wall segment, opening into `room`."""
        (sx, sy), (ex, ey) = segment
        cx, cy = (sx + ex) / 2, (sy + ey) / 2
        seg_len = math.hypot(ex - sx, ey - sy)
        dw = min(0.9, seg_len * 0.7)
        into = {"left": (1, 0), "right": (-1, 0), "top": (0, 1), "bottom": (0, -1)}[wall]
        if wall in ("left", "right"):  # vertical wall
            hinge, wdir = (cx, cy - dw / 2), (0, 1)
        else:  # horizontal wall
            hinge, wdir = (cx - dw / 2, cy), (1, 0)
        room.doors.append(self._make_door(hinge, wdir, into, dw))
        room.door_walls.add(wall)

    # -- adjacency-driven grouping (used by the auto solver) ---------------- #

    def _adjacency_columns(self, private: List[Room]):
        """Split private rooms into two corridor-flanking columns.

        Rooms declared adjacent to each other are kept in the SAME column and
        ordered contiguously so they end up sharing a wall. With no adjacency
        declared this degrades to plain area-balancing (each room its own group),
        i.e. the previous behaviour.
        """
        ids = {r.id for r in private}
        byid = {r.id: r for r in private}
        graph: Dict[str, Set[str]] = {r.id: set() for r in private}
        for r in private:
            for ref in r.spec.adjacent_to if r.spec else []:
                o = self._resolve(ref)
                if o and o.id in ids:
                    graph[r.id].add(o.id)
                    graph[o.id].add(r.id)

        # Connected components: rooms that must travel together.
        seen: Set[str] = set()
        components: List[List[str]] = []
        for r in private:
            if r.id in seen:
                continue
            comp: Set[str] = set()
            stack = [r.id]
            while stack:
                n = stack.pop()
                if n in comp:
                    continue
                comp.add(n)
                seen.add(n)
                stack.extend(graph[n] - comp)
            components.append(self._order_component(comp, graph))

        # Assign whole components to the lighter column to balance area.
        components.sort(key=lambda c: sum(self._area(byid[i]) for i in c), reverse=True)
        left, right, la, ra = [], [], 0.0, 0.0
        for comp in components:
            a = sum(self._area(byid[i]) for i in comp)
            if la <= ra:
                left.extend(byid[i] for i in comp)
                la += a
            else:
                right.extend(byid[i] for i in comp)
                ra += a
        return left, right

    @staticmethod
    def _order_component(comp: Set[str], graph: Dict[str, Set[str]]) -> List[str]:
        """DFS from a chain endpoint so neighbours stay next to each other."""
        start = min(comp, key=lambda n: (len(graph[n] & comp), n))
        order, visited, stack = [], set(), [start]
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            order.append(n)
            for m in sorted(graph[n] & comp, reverse=True):
                if m not in visited:
                    stack.append(m)
        return order

    def adjacency_report(self) -> List[dict]:
        """For each declared adjacency, whether the final geometry realises it."""
        out, done = [], set()
        for r in self.rooms:
            for ref in r.spec.adjacent_to if r.spec else []:
                o = self._resolve(ref)
                if not o or frozenset((r.id, o.id)) in done:
                    continue
                done.add(frozenset((r.id, o.id)))
                ok = any(e["neighbor"] == o.id for e in self.adjacency.get(r.id, []))
                out.append({"a": r.id, "b": o.id, "satisfied": ok})
        return out

    # -- layout: central corridor + full-width public band ------------------ #

    def _layout_auto(self) -> None:
        bx, by, W, D = (
            self.footprint.x,
            self.footprint.y,
            self.footprint.w,
            self.footprint.h,
        )

        public = [r for r in self.rooms if self._is_public(r)]
        private = [r for r in self.rooms if not self._is_public(r)]
        any_custom_entrance = any(r.spec and r.spec.entrances for r in self.rooms)

        # Front public band depth (full width). If a public room pins a depth,
        # the band takes it; else target ~4 m, kept within bounds.
        if public and private:
            pub_depths = [r.spec.depth for r in public if r.spec and r.spec.depth]
            if pub_depths:
                front_depth = min(max(pub_depths), 0.6 * D)
            else:
                pub_area = sum(self._area(r) for r in public)
                front_depth = min(max(pub_area / W, 4.0), 0.45 * D)
        elif public:
            front_depth = D
        else:
            front_depth = 0.0
        rear_depth = D - front_depth

        too_small: List[str] = []

        # --- Rear private zone: two columns flanking a central corridor. ---- #
        if private and rear_depth > 0:
            if len(private) == 1:
                private[0].rect = Rect(bx, by, W, rear_depth)
                self._side_door(private[0], "bottom", into=(0, -1))
            else:
                cw = min(1.3, W * 0.12)
                col_w = (W - cw) / 2
                # Adjacency decides column grouping + order (declared-adjacent
                # rooms end up contiguous); no adjacency => area-balancing.
                left, right = self._adjacency_columns(private)

                self._stack(left, bx, by, col_w, rear_depth, door="right")
                self._stack(right, bx + col_w + cw, by, col_w, rear_depth, door="left")

                self.corridor = Room(
                    RoomType.CORRIDOR,
                    "Hall",
                    Rect(bx + col_w, by, cw, rear_depth),
                    id="hall",
                )
                # Open archway where the corridor meets the public band.
                if public:
                    self.openings.append(
                        (
                            (bx + col_w, by + rear_depth),
                            (bx + col_w + cw, by + rear_depth),
                        )
                    )
                else:
                    self._side_door(self.corridor, "bottom", into=(0, -1))

        # --- Front public band: living + dining split across full width. ---- #
        if public and front_depth > 0:
            # Living first (left), then dining, so the entry lands on the living.
            ordered = sorted(
                public,
                key=lambda r: (r.type != RoomType.LIVING_ROOM, -self._area(r)),
            )
            # Pinned widths honored exactly; the rest flow to fill the width.
            widths = self._flow_sizes(
                W,
                [r.spec.width if r.spec else None for r in ordered],
                [0.0 for _ in ordered],
                [self._area(r) for r in ordered],
            )
            x = bx
            for r, w in zip(ordered, widths):
                r.rect = Rect(x, by + rear_depth, w, front_depth)
                x += w
            living = next((r for r in ordered if r.type == RoomType.LIVING_ROOM), None)
            dining = next((r for r in ordered if r.type == RoomType.DINING), None)

            # Default entrances on the two long (12 m) sides: into the living room
            # on the left and the dining room on the right (only one public room
            # spans full width and takes both). Skipped if any spec declares its
            # own entrances, which then take over.
            if not any_custom_entrance:
                left_room = living or dining
                right_room = dining or living
                if left_room:
                    self._side_door(left_room, "left", into=(1, 0))
                if right_room:
                    self._side_door(right_room, "right", into=(-1, 0))

            # Open-plan: leave a wide opening in the wall between living & dining
            # (keep short wall stubs at the ends), instead of a solid partition.
            if living and dining and living.rect and dining.rect:
                bound = (
                    living.rect.right
                    if abs(living.rect.right - dining.rect.x) < 1e-6
                    else dining.rect.right
                )
                y0 = by + rear_depth
                y1 = y0 + front_depth
                stub = 0.5
                if y1 - y0 > 2 * stub:
                    self.openings.append(((bound, y0 + stub), (bound, y1 - stub)))

        # Custom entrances declared on specs (exterior entry doors on named walls).
        inward = {"left": (1, 0), "right": (-1, 0), "top": (0, 1), "bottom": (0, -1)}
        for r in self.rooms:
            if r.rect and r.spec:
                for w in r.spec.entrances:
                    self._side_door(r, w, into=inward[w])

        # Min-size sanity check (spec overrides, else per-type minimums).
        for r in self.all_rooms:
            if r.rect and (
                r.rect.w < self._min_w(r) - 1e-6 or r.rect.h < self._min_d(r) - 1e-6
            ):
                too_small.append(
                    f"{r.label} would be {r.rect.w:.1f}x{r.rect.h:.1f} m "
                    f"(min {self._min_w(r):.1f}x{self._min_d(r):.1f} m)"
                )
        if too_small:
            raise SketchValidationError(
                "Some rooms come out too small for this plot: "
                + "; ".join(too_small)
                + ". Use a larger plot or fewer rooms."
            )

    def _stack(self, rooms, x, y, w, total_h, door) -> None:
        """Stack rooms vertically in a column; door faces the corridor.

        Each room is guaranteed at least its minimum depth; any remaining depth
        is shared out by area, so a small room (e.g. a bathroom) is never starved
        into an unusably thin slice.
        """
        if not rooms:
            return
        heights = self._flow_sizes(
            total_h,
            [r.spec.depth if r.spec else None for r in rooms],
            [self._min_d(r) for r in rooms],
            [self._area(r) for r in rooms],
        )
        cy = y
        for r, h in zip(rooms, heights):
            r.rect = Rect(x, cy, w, h)
            cy += h
            self._side_door(r, door, into=((1, 0) if door == "left" else (-1, 0)))

    @staticmethod
    def _flow_sizes(total, fixed, mins, areas) -> List[float]:
        """Distribute `total` length across items along one axis.

        `fixed[i]` pins an exact size; the remaining (None) items each get at
        least `mins[i]`, then share what's left in proportion to `areas[i]`.
        This is what lets a room keep a specified width/depth exactly while its
        neighbours flex to fill the rest.
        """
        pinned = sum(f for f in fixed if f is not None)
        if pinned > total + 1e-6:
            raise SketchValidationError(
                f"Pinned room sizes ({pinned:.1f} m) exceed the available "
                f"{total:.1f} m along that axis. Enlarge the plot or shrink them."
            )
        flex = [i for i, f in enumerate(fixed) if f is None]
        if not flex:
            # Everything pinned: scale to fill exactly, preserving the ratios.
            scale = total / pinned if pinned else 1.0
            return [f * scale for f in fixed]

        sizes = list(fixed)
        rem = total - pinned
        fmins = [mins[i] for i in flex]
        fareas = [areas[i] for i in flex]
        extra = rem - sum(fmins)
        ta = sum(fareas) or 1.0
        for k, i in enumerate(flex):
            if extra >= 0:
                sizes[i] = fmins[k] + extra * fareas[k] / ta
            else:  # not enough room even for minimums; validation flags it
                sizes[i] = fareas[k] / ta * rem
        return sizes

    # -- openings ----------------------------------------------------------- #

    def _side_door(self, room: Room, wall: str, into: Tuple[float, float]) -> None:
        rect = room.rect
        dw = min(
            0.9,
            max(rect.w, rect.h) * 0.5,
            (rect.w if wall in ("top", "bottom") else rect.h) * 0.7,
        )
        if wall == "bottom":
            hinge, wdir = (rect.cx - dw / 2, rect.bottom), (1, 0)
        elif wall == "top":
            hinge, wdir = (rect.cx - dw / 2, rect.y), (1, 0)
        elif wall == "right":
            hinge, wdir = (rect.right, rect.cy - dw / 2), (0, 1)
        else:  # left
            hinge, wdir = (rect.x, rect.cy - dw / 2), (0, 1)
        room.doors.append(self._make_door(hinge, wdir, into, dw))
        room.door_walls.add(wall)

    @staticmethod
    def _subtract_intervals(a: float, b: float, covered) -> List[Tuple[float, float]]:
        """Sub-ranges of [a, b] not covered by any interval in `covered`."""
        clipped = sorted(
            (max(a, lo), min(b, hi)) for lo, hi in covered if min(b, hi) > max(a, lo)
        )
        out, cur = [], a
        for lo, hi in clipped:
            if lo > cur:
                out.append((cur, lo))
            cur = max(cur, hi)
        if cur < b:
            out.append((cur, b))
        return out

    def _exterior_segments(self, room: Room):
        """(side, segment) for each part of a room's edges NOT shared with a
        neighbour — i.e. the outer walls. This is what lets the building outline
        follow the rooms into any shape instead of a fixed rectangle."""
        r = room.rect
        if r is None:
            return []
        shared = {"top": [], "bottom": [], "left": [], "right": []}
        for e in self.adjacency.get(room.id, []):
            (sx, sy), (ex, ey) = e["segment"]
            if e["wall"] in ("top", "bottom"):
                shared[e["wall"]].append((min(sx, ex), max(sx, ex)))
            else:
                shared[e["wall"]].append((min(sy, ey), max(sy, ey)))

        edges = {  # side: (interval_start, interval_end, fixed_coord, horizontal?)
            "top": (r.x, r.right, r.y, True),
            "bottom": (r.x, r.right, r.bottom, True),
            "left": (r.y, r.bottom, r.x, False),
            "right": (r.y, r.bottom, r.right, False),
        }
        out = []
        for side, (a, b, fixed, horizontal) in edges.items():
            for lo, hi in self._subtract_intervals(a, b, shared[side]):
                if hi - lo < 0.05:
                    continue
                if horizontal:
                    out.append((side, ((lo, fixed), (hi, fixed))))
                else:
                    out.append((side, ((fixed, lo), (fixed, hi))))
        return out

    def _place_windows(self) -> None:
        """Centre a window on each exterior wall segment long enough to hold one,
        skipping sides that carry a door and rooms with windows suppressed."""
        for room in self.all_rooms:
            if room.spec and room.spec.windows is False:
                continue
            for side, seg in self._exterior_segments(room):
                if side in room.door_walls:
                    continue
                (x0, y0), (x1, y1) = seg
                length = math.hypot(x1 - x0, y1 - y0)
                if length <= 1.4:
                    continue
                win = min(1.6, length * 0.5)
                if abs(x0 - x1) < 1e-9:  # vertical wall
                    c = (y0 + y1) / 2
                    room.windows.append(Window((x0, c - win / 2), (x0, c + win / 2)))
                else:  # horizontal wall
                    c = (x0 + x1) / 2
                    room.windows.append(Window((c - win / 2, y0), (c + win / 2, y0)))

    def _rooms_bbox(self) -> Rect:
        """Bounding box of all placed rooms (the building's actual extent)."""
        rects = [r.rect for r in self.all_rooms if r.rect]
        if not rects:
            return self.footprint
        x0 = min(r.x for r in rects)
        y0 = min(r.y for r in rects)
        x1 = max(r.right for r in rects)
        y1 = max(r.bottom for r in rects)
        return Rect(x0, y0, x1 - x0, y1 - y0)

    @staticmethod
    def _make_door(hinge, wall, swing, w) -> Door:
        a0 = math.atan2(wall[1], wall[0])
        a1 = math.atan2(swing[1], swing[0])
        d = a1 - a0
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        arc = [
            (
                hinge[0] + w * math.cos(a0 + d * i / 10),
                hinge[1] + w * math.sin(a0 + d * i / 10),
            )
            for i in range(11)
        ]
        tip = (hinge[0] + w * swing[0], hinge[1] + w * swing[1])
        return Door(leaf=(hinge, tip), arc=arc)

    # -- rendering ---------------------------------------------------------- #

    # Palette (driven by the LEGEND convention).
    C_SHEET = "#FFFFFF"
    C_LOT = "#FCFBF7"
    C_LOT_LINE = "#9AA3AD"
    C_WALL = LEGEND["remaining_wall"]  # black
    C_PARTITION = LEGEND["remaining_wall"]  # black
    C_WINDOW = LEGEND["window"]  # orange
    C_DOOR = LEGEND["remaining_wall"]  # black
    C_LABEL = "#2B333B"
    C_DIM = "#9AA3AD"

    def _draw(self, surf: "_Surface", t: "_Transform") -> None:
        plot = self.plot
        # Solid wall bands: exterior heavier than interior partitions.
        wall_px = max(6, int(self.wall * t.scale))
        part_px = max(4, int(self.wall * t.scale * 0.7))

        # Property boundary (lot) — light fill, thin line, generous yard around.
        surf.rect(*t.box(plot), fill=self.C_LOT, stroke=self.C_LOT_LINE, width=2)

        # Room fills. Their union is the building — so the shape follows the rooms
        # (rectangular, L-shaped, courtyard, central room, ...); gaps show the lot.
        for r in self.all_rooms:
            surf.rect(*t.box(r.rect), fill=ROOM_COLOR[r.type], stroke=None)

        # Interior partitions: solid bands on every room boundary.
        for r in self.all_rooms:
            surf.rect(*t.box(r.rect), fill=None, stroke=self.C_PARTITION, width=part_px)

        # Exterior wall: a heavier band along every non-shared (outer) edge, so the
        # outline traces the actual building shape rather than a bounding rectangle.
        for r in self.all_rooms:
            for _side, seg in self._exterior_segments(r):
                surf.line(*t.pt(seg[0]), *t.pt(seg[1]), stroke=self.C_WALL, width=wall_px)

        # Open passages (corridor mouth, living/dining open-plan).
        for seg in self.openings:
            self._erase(surf, t, seg[0], seg[1], part_px)

        # Windows: orange segment INLINE with the wall band (no separator caps).
        for r in self.all_rooms:
            for w in r.windows:
                self._draw_window(surf, t, w, wall_px)

        # Doors: gap in the wall + bold door leaf (panel) + thin swing arc.
        for r in self.all_rooms:
            for d in r.doors:
                self._erase(surf, t, d.leaf[0], d.arc[-1], wall_px)
                surf.line(
                    *t.pt(d.leaf[0]), *t.pt(d.leaf[1]), stroke=self.C_DOOR, width=4
                )
                surf.polyline([t.pt(p) for p in d.arc], stroke=self.C_DOOR, width=1)

        # Labels.
        for r in self.all_rooms:
            cx, cy = t.pt((r.rect.cx, r.rect.cy))
            if r.type == RoomType.CORRIDOR:
                surf.text(cx, cy, r.label, fill=self.C_DIM, size=11, anchor="middle")
                continue
            surf.text(cx, cy - 8, r.label, fill=self.C_LABEL, size=14, anchor="middle")
            surf.text(
                cx,
                cy + 10,
                f"{r.rect.w:.1f}x{r.rect.h:.1f} m",
                fill=self.C_DIM,
                size=11,
                anchor="middle",
            )

        # Overall building dimensions (from the rooms' actual extent), north
        # arrow, title, scale bar.
        bb = self._rooms_bbox()
        self._dim(surf, t, (bb.x, bb.y), (bb.right, bb.y), -24, f"{bb.w:.1f} m")
        self._dim(
            surf,
            t,
            (bb.right, bb.y),
            (bb.right, bb.bottom),
            24,
            f"{bb.h:.1f} m",
            vertical=True,
        )
        self._north(surf, t)
        self._title_and_scale(surf, t)

    def _draw_window(self, surf, t, w, wall_px) -> None:
        """Window drawn INLINE with the wall: an orange band the same thickness
        as the wall, with a thin black glazing line down its centre. The black
        wall continues at each end as the jamb."""
        p0, p1 = t.pt(w.p0), t.pt(w.p1)
        surf.line(p0[0], p0[1], p1[0], p1[1], stroke=self.C_WINDOW, width=wall_px)
        surf.line(p0[0], p0[1], p1[0], p1[1], stroke=self.C_WALL, width=max(1, wall_px // 4))

    def _erase(self, surf, t, a, b, wall_px) -> None:
        half = wall_px * 0.7 + 1
        ax, ay = t.pt(a)
        bx, by = t.pt(b)
        if abs(ay - by) < abs(ax - bx):  # horizontal
            surf.rect(min(ax, bx), ay - half, max(ax, bx), ay + half, fill="#FFFFFF")
        else:  # vertical
            surf.rect(ax - half, min(ay, by), ax + half, max(ay, by), fill="#FFFFFF")

    def _dim(self, surf, t, p1, p2, offset, text, vertical=False) -> None:
        col = self.C_DIM
        if not vertical:
            yb = t.pt(p1)[1]
            yl = yb + offset
            x1 = t.pt(p1)[0]
            x2 = t.pt(p2)[0]
            surf.line(x1, yb, x1, yl, stroke=col, width=1)
            surf.line(x2, yb, x2, yl, stroke=col, width=1)
            surf.line(x1, yl, x2, yl, stroke=col, width=1)
            surf.text(
                (x1 + x2) / 2,
                yl - 9 if offset < 0 else yl + 9,
                text,
                fill=col,
                size=12,
                anchor="middle",
            )
        else:
            xb = t.pt(p1)[0]
            xl = xb + offset
            y1 = t.pt(p1)[1]
            y2 = t.pt(p2)[1]
            surf.line(xb, y1, xl, y1, stroke=col, width=1)
            surf.line(xb, y2, xl, y2, stroke=col, width=1)
            surf.line(xl, y1, xl, y2, stroke=col, width=1)
            surf.text(xl + 22, (y1 + y2) / 2, text, fill=col, size=12, anchor="middle")

    def _north(self, surf, t) -> None:
        nx, ny = 40, t.oy + 4
        surf.ellipse(
            nx - 14,
            ny - 14,
            nx + 14,
            ny + 14,
            fill="#FFFFFF",
            stroke=self.C_WALL,
            width=1,
        )
        surf.line(nx, ny + 10, nx, ny - 10, stroke=self.C_WALL, width=2)
        surf.polygon(
            [(nx, ny - 15), (nx - 5, ny - 6), (nx + 5, ny - 6)], fill=self.C_WALL
        )
        surf.text(nx, ny - 24, "N", fill=self.C_WALL, size=12, anchor="middle")

    def _title_and_scale(self, surf, t) -> None:
        bx0 = surf.width - 250
        surf.rect(
            bx0, 22, surf.width - 22, 88, fill="#FFFFFF", stroke=self.C_WALL, width=1
        )
        surf.text(bx0 + 12, 40, self.title, fill=self.C_WALL, size=14, anchor="start")
        surf.text(
            bx0 + 12,
            62,
            f"Plot: {self.plot.w:.0f} x {self.plot.h:.0f} m ({self.plot.area:.0f} m2)",
            fill=self.C_DIM,
            size=11,
            anchor="start",
        )
        surf.text(
            bx0 + 12,
            80,
            f"Rooms: {len(self.rooms)}   Setback: {self.setback:.0f} m",
            fill=self.C_DIM,
            size=11,
            anchor="start",
        )

        bar = 5 * t.scale
        x1 = surf.width - 30
        x0 = x1 - bar
        y = surf.height - 28
        surf.line(x0, y, x1, y, stroke=self.C_WALL, width=2)
        surf.line(x0, y - 5, x0, y + 5, stroke=self.C_WALL, width=1)
        surf.line(x1, y - 5, x1, y + 5, stroke=self.C_WALL, width=1)
        surf.text(x0, y + 13, "0", fill=self.C_WALL, size=11, anchor="middle")
        surf.text(x1, y + 13, "5 m", fill=self.C_WALL, size=11, anchor="middle")

    def _transform(self) -> "_Transform":
        margin = (95, 95, 270, 95)  # left, top, right, bottom — zoomed out
        draw_target = 620
        scale = min(draw_target / self.plot.w, draw_target / self.plot.h)
        width = int(self.plot.w * scale + margin[0] + margin[2])
        height = int(self.plot.h * scale + margin[1] + margin[3])
        return _Transform(scale, margin[0], margin[1], width, height)

    def to_png(self, path: Optional[str] = None) -> bytes:
        t = self._transform()
        surf = _PILSurface(t.width, t.height, self.C_SHEET)
        self._draw(surf, t)
        data = surf.to_bytes()
        if path:
            with open(path, "wb") as f:
                f.write(data)
        return data

    def to_png_data_uri(self) -> str:
        return "data:image/png;base64," + base64.b64encode(self.to_png()).decode()

    def to_svg(self, path: Optional[str] = None) -> str:
        t = self._transform()
        surf = _SVGSurface(t.width, t.height, self.C_SHEET)
        self._draw(surf, t)
        svg = surf.to_svg()
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg)
        return svg

    def to_dict(self) -> dict:
        """Structured description of the computed plan (handy for JSON/DXF/debug)."""

        def room_d(r: Room) -> dict:
            s = r.spec
            return {
                "id": r.id,
                "type": r.type.value,
                "label": r.label,
                "zone": "public" if self._is_public(r) else "private",
                "rect": None
                if not r.rect
                else {
                    "x": round(r.rect.x, 3),
                    "y": round(r.rect.y, 3),
                    "w": round(r.rect.w, 3),
                    "h": round(r.rect.h, 3),
                },
                "adjacent_to": list(s.adjacent_to) if s else [],  # declared
                "neighbors": self.neighbors_of(r.id),              # computed
                "doors": len(r.doors),
                "windows": len(r.windows),
            }

        return {
            "plot": {"w": self.plot.w, "h": self.plot.h, "area": self.plot.area},
            "setback": self.setback,
            "footprint": {
                "x": self.footprint.x,
                "y": self.footprint.y,
                "w": self.footprint.w,
                "h": self.footprint.h,
            },
            "rooms": [room_d(r) for r in self.all_rooms],
        }


# --------------------------------------------------------------------------- #
# Transform + drawing surfaces (meters already converted to pixels by callers)
# --------------------------------------------------------------------------- #


@dataclass
class _Transform:
    scale: float
    ox: float
    oy: float
    width: int
    height: int

    def pt(self, p: Tuple[float, float]) -> Tuple[float, float]:
        return (self.ox + p[0] * self.scale, self.oy + p[1] * self.scale)

    def box(self, r: Rect) -> Tuple[float, float, float, float]:
        x0, y0 = self.pt((r.x, r.y))
        x1, y1 = self.pt((r.right, r.bottom))
        return (x0, y0, x1, y1)


def _load_font(size: int):
    for p in (
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


class _Surface:
    """Drawing interface in PIXEL coordinates. PNG and SVG both implement it."""

    width: int
    height: int

    def rect(self, x0, y0, x1, y1, fill=None, stroke=None, width=1): ...
    def line(self, x0, y0, x1, y1, stroke, width=1): ...
    def polyline(self, pts, stroke, width=1): ...
    def polygon(self, pts, fill=None, stroke=None, width=1): ...
    def ellipse(self, x0, y0, x1, y1, fill=None, stroke=None, width=1): ...
    def text(self, x, y, s, fill, size, anchor="start"): ...


class _PILSurface(_Surface):
    def __init__(self, width, height, bg):
        self.width, self.height = width, height
        self.img = Image.new("RGB", (width, height), bg)
        self.d = ImageDraw.Draw(self.img)

    def rect(self, x0, y0, x1, y1, fill=None, stroke=None, width=1):
        self.d.rectangle([x0, y0, x1, y1], fill=fill, outline=stroke, width=width)

    def line(self, x0, y0, x1, y1, stroke, width=1):
        self.d.line([x0, y0, x1, y1], fill=stroke, width=width)

    def polyline(self, pts, stroke, width=1):
        self.d.line([tuple(p) for p in pts], fill=stroke, width=width, joint="curve")

    def polygon(self, pts, fill=None, stroke=None, width=1):
        self.d.polygon([tuple(p) for p in pts], fill=fill, outline=stroke)

    def ellipse(self, x0, y0, x1, y1, fill=None, stroke=None, width=1):
        self.d.ellipse([x0, y0, x1, y1], fill=fill, outline=stroke, width=width)

    def text(self, x, y, s, fill, size, anchor="start"):
        a = "mm" if anchor == "middle" else "lm"
        self.d.text((x, y), s, fill=fill, font=_load_font(size), anchor=a)

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.img.save(buf, format="PNG")
        return buf.getvalue()


class _SVGSurface(_Surface):
    def __init__(self, width, height, bg):
        self.width, self.height = width, height
        self.bg = bg
        self.parts: List[str] = []

    @staticmethod
    def _n(v) -> str:
        return f"{v:.2f}"

    def rect(self, x0, y0, x1, y1, fill=None, stroke=None, width=1):
        x, y = min(x0, x1), min(y0, y1)
        self.parts.append(
            f'<rect x="{self._n(x)}" y="{self._n(y)}" width="{self._n(abs(x1 - x0))}" '
            f'height="{self._n(abs(y1 - y0))}" fill="{fill or "none"}" '
            f'stroke="{stroke or "none"}" stroke-width="{width}"/>'
        )

    def line(self, x0, y0, x1, y1, stroke, width=1):
        self.parts.append(
            f'<line x1="{self._n(x0)}" y1="{self._n(y0)}" x2="{self._n(x1)}" '
            f'y2="{self._n(y1)}" stroke="{stroke}" stroke-width="{width}"/>'
        )

    def polyline(self, pts, stroke, width=1):
        pstr = " ".join(f"{self._n(p[0])},{self._n(p[1])}" for p in pts)
        self.parts.append(
            f'<polyline points="{pstr}" fill="none" stroke="{stroke}" stroke-width="{width}"/>'
        )

    def polygon(self, pts, fill=None, stroke=None, width=1):
        pstr = " ".join(f"{self._n(p[0])},{self._n(p[1])}" for p in pts)
        self.parts.append(
            f'<polygon points="{pstr}" fill="{fill or "none"}" '
            f'stroke="{stroke or "none"}" stroke-width="{width}"/>'
        )

    def ellipse(self, x0, y0, x1, y1, fill=None, stroke=None, width=1):
        self.parts.append(
            f'<ellipse cx="{self._n((x0 + x1) / 2)}" cy="{self._n((y0 + y1) / 2)}" '
            f'rx="{self._n(abs(x1 - x0) / 2)}" ry="{self._n(abs(y1 - y0) / 2)}" '
            f'fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{width}"/>'
        )

    def text(self, x, y, s, fill, size, anchor="start"):
        ta = "middle" if anchor == "middle" else "start"
        self.parts.append(
            f'<text x="{self._n(x)}" y="{self._n(y)}" fill="{fill}" '
            f'font-family="DejaVu Sans, Arial, sans-serif" font-size="{size}" '
            f'text-anchor="{ta}" dominant-baseline="central">{html.escape(s)}</text>'
        )

    def to_svg(self) -> str:
        body = "\n  ".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}">\n'
            f'  <rect width="100%" height="100%" fill="{self.bg}"/>\n  {body}\n</svg>\n'
        )


# --------------------------------------------------------------------------- #
# Runnable demo — a typical rectangular African house (~10 x 12 m building)
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # The simple dict form still works (each entry becomes a default RoomSpec)...
    # ...but rooms can now carry rich, per-room data:
    sketch = HouseSketch(
        plot_width=16,
        plot_depth=18,
        rooms=[
            RoomSpec("living_room", width=6.5, depth=4.0, entrances=["left"]),
            RoomSpec("dining", entrances=["right"], adjacent_to=["living-room"]),
            RoomSpec("bedroom", name="Master Bedroom", area=16.0),
            RoomSpec("bedroom"),
            RoomSpec("bedroom"),
            RoomSpec("bathroom", windows=False),
            RoomSpec("kitchen"),
        ],
        setback=3.0,
    )
    sketch.to_png("house.png")
    sketch.to_svg("house.svg")
    print("Wrote house.png and house.svg")
    print(f"Buildable footprint: {sketch.footprint.w:.1f} x {sketch.footprint.h:.1f} m")
    print(f"Required area (incl. circulation): {sketch.required_area():.0f} m2")
