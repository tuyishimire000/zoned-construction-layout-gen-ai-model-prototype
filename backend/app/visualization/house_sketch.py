"""HouseSketch: turn typed house parameters into a real PNG + SVG floor sketch.
"""

from __future__ import annotations

import io
import math
import html
import base64
import random
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Union

from PIL import Image, ImageDraw, ImageFont


class RoomType(str, Enum):
    BEDROOM = "bedroom"
    BATHROOM = "bathroom"
    KITCHEN = "kitchen"
    LIVING_ROOM = "living_room"
    DINING = "dining"
    OFFICE = "office"
    CORRIDOR = "corridor"
    GARAGE = "garage"
    STORE = "store"
    LAUNDRY = "laundry"
    PANTRY = "pantry"
    BALCONY = "balcony"
    OTHER = "other"  # catch-all for any room name not otherwise recognized


PUBLIC_TYPES = {RoomType.LIVING_ROOM, RoomType.DINING}

ROOM_AREA = {
    RoomType.BEDROOM: 14.0,
    RoomType.BATHROOM: 5.0,
    RoomType.KITCHEN: 11.0,
    RoomType.LIVING_ROOM: 22.0,
    RoomType.DINING: 12.0,
    RoomType.OFFICE: 10.0,
    RoomType.CORRIDOR: 6.0,
    RoomType.GARAGE: 18.0,
    RoomType.STORE: 4.0,
    RoomType.LAUNDRY: 5.0,
    RoomType.PANTRY: 3.5,
    RoomType.BALCONY: 6.0,
    RoomType.OTHER: 10.0,  # generic fallback for an unrecognized room name
}
ROOM_MIN_SIDE = {
    RoomType.BEDROOM: 2.6,
    RoomType.BATHROOM: 1.5,
    RoomType.KITCHEN: 2.2,
    RoomType.LIVING_ROOM: 3.0,
    RoomType.DINING: 2.4,
    RoomType.OFFICE: 2.0,
    RoomType.CORRIDOR: 1.0,
    RoomType.GARAGE: 2.8,
    RoomType.STORE: 1.4,
    RoomType.LAUNDRY: 1.6,
    RoomType.PANTRY: 1.3,
    RoomType.BALCONY: 1.4,
    RoomType.OTHER: 2.0,
}
ROOM_COLOR = {rt: "#FFFFFF" for rt in RoomType}
ROOM_COLOR[RoomType.CORRIDOR] = "#F2F3F5"

LEGEND = {
    "added_wall": "#E53935",
    "removed_wall": "#1E88E5",
    "remaining_wall": "#111111",
    "unit_1": "#B9F6CA",
    "unit_2": "#FFF59D",
    "window": "#EF7C00",
}

_ALIASES = {
    "bed": RoomType.BEDROOM,
    "bedroom": RoomType.BEDROOM,
    "bedrooms": RoomType.BEDROOM,
    "bath": RoomType.BATHROOM,
    "bathroom": RoomType.BATHROOM,
    "bathrooms": RoomType.BATHROOM,
    "wc": RoomType.BATHROOM,
    "toilet": RoomType.BATHROOM,
    "ensuite": RoomType.BATHROOM,
    "kitchen": RoomType.KITCHEN,
    "kitchens": RoomType.KITCHEN,
    "living": RoomType.LIVING_ROOM,
    "living_room": RoomType.LIVING_ROOM,
    "living_rooms": RoomType.LIVING_ROOM,
    "lounge": RoomType.LIVING_ROOM,
    "sitting": RoomType.LIVING_ROOM,
    "family_room": RoomType.LIVING_ROOM,
    "dining": RoomType.DINING,
    "dining_room": RoomType.DINING,
    "office": RoomType.OFFICE,
    "offices": RoomType.OFFICE,
    "study": RoomType.OFFICE,
    "home_office": RoomType.OFFICE,
    "corridor": RoomType.CORRIDOR,
    "hall": RoomType.CORRIDOR,
    "hallway": RoomType.CORRIDOR,
    "passage": RoomType.CORRIDOR,
    "garage": RoomType.GARAGE,
    "carport": RoomType.GARAGE,
    "store": RoomType.STORE,
    "storage": RoomType.STORE,
    "store_room": RoomType.STORE,
    "storeroom": RoomType.STORE,
    "closet": RoomType.STORE,
    "walk_in_closet": RoomType.STORE,
    "laundry": RoomType.LAUNDRY,
    "utility": RoomType.LAUNDRY,
    "utility_room": RoomType.LAUNDRY,
    "pantry": RoomType.PANTRY,
    "balcony": RoomType.BALCONY,
    "terrace": RoomType.BALCONY,
    "veranda": RoomType.BALCONY,
    "verandah": RoomType.BALCONY,
    "porch": RoomType.BALCONY,
}


def _normalize(rtype: Union[str, RoomType]) -> RoomType:
    """Map a room-type string onto a `RoomType`. Anything not recognized
    becomes RoomType.OTHER (with generic default sizing) rather than raising —
    an extractor reading free-form text (e.g. "prayer room", "cinema room")
    will surface names this module was never told about, and a hard failure
    there would make the whole pipeline as brittle as its room-name list.
    Give a room explicit `area`/`min_width`/`min_depth` in its RoomSpec for
    accurate sizing when using an unrecognized type.
    """
    if isinstance(rtype, RoomType):
        return rtype
    key = str(rtype).strip().lower().replace(" ", "_").replace("-", "_")
    return _ALIASES.get(key, RoomType.OTHER)


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
    leaf: Tuple[Tuple[float, float], Tuple[float, float]]
    arc: List[Tuple[float, float]]


@dataclass
class Window:
    p0: Tuple[float, float]
    p1: Tuple[float, float]


@dataclass
class Room:
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

    east_of: Optional[str] = None
    west_of: Optional[str] = None
    north_of: Optional[str] = None
    south_of: Optional[str] = None
    align: str = "start"
    offset: float = 0.0
    gap: float = 0.0

    entrances: List[str] = field(default_factory=list)
    windows: Optional[bool] = None

    priority: int = 0
    notes: str = ""

    _WALLS = ("left", "right", "top", "bottom")
    _RELATIONS = ("east_of", "west_of", "north_of", "south_of")

    def __post_init__(self):
        raw_type = self.type
        self.type = _normalize(self.type)
        if (
            self.type is RoomType.OTHER
            and not self.name
            and isinstance(raw_type, str)
        ):
            # Fall back to the caller's own wording ("Prayer Room", "Cinema
            # Room", ...) instead of the generic "Other" label.
            self.name = raw_type.strip().replace("_", " ").title()
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
        for rel in self._RELATIONS:
            v = getattr(self, rel)
            if v:
                return v, rel
        return None, None

    def target_area(self) -> float:
        """Desired floor area used for sizing/flex calculations.

        NOTE: if only ONE of `width`/`depth` is set (not both, and no explicit
        `area`), this falls back to the per-type default area rather than
        deriving anything from the single pinned dimension — the other side is
        then computed elsewhere as `area / pinned_side`, which may not match
        what you'd expect. Set both `width` and `depth`, or `area`, to fully
        control a room's size.
        """
        if self.area is not None:
            return self.area
        if self.width is not None and self.depth is not None:
            return self.width * self.depth
        return ROOM_AREA[self.type]


@dataclass
class LayoutTuning:
    """Every numeric knob the non-manual archetypes use, factored out of the
    layout code so a caller (e.g. a pipeline mapping extracted parameters onto
    a house) can override them without touching code. Defaults reproduce the
    original hand-tuned behavior exactly — pass a modified instance (or a
    dict of overrides) via `HouseSketch(..., tuning=...)` to change them.

    None of these are "correct" in any universal sense; they're reasonable
    defaults for a modest single-storey house. A different market/typology
    (tiny apartments, large villas) may want different numbers entirely.
    """

    # Front (public) band depth, as a fraction/floor of the footprint depth D.
    front_depth_min: float = 4.0
    front_depth_max_frac: float = 0.45      # cap when depth is derived from area
    front_depth_pinned_max_frac: float = 0.6  # cap when a room pins its own depth

    # Corridor / hall strip width.
    corridor_width_max: float = 1.3
    corridor_width_frac_two_col: float = 0.12   # fraction of the private zone's width
    corridor_width_frac_single_col: float = 0.18

    # Courtyard ring (back row + two side columns around an open void).
    courtyard_back_depth_min: float = 3.0
    courtyard_back_depth_max_frac: float = 0.4   # fraction of the rear rect's depth
    courtyard_col_width_min: float = 2.6
    courtyard_col_width_max_frac: float = 0.35   # fraction of the rear rect's width

    # L-shape wings (private wing width, public wing depth).
    l_wing_min: float = 3.0
    l_wing_max_frac: float = 0.6            # fraction of the footprint's matching side

    # Archway stub length: how much solid wall stays at each end of an
    # open-plan opening so it doesn't erase into an adjacent corner.
    archway_stub: float = 0.5

    # "auto" archetype choice, based on the footprint's aspect ratio (W / D).
    auto_narrow_aspect: float = 0.55        # below this -> single_loaded
    auto_wide_aspect: float = 1.8           # above this -> single_loaded
    auto_courtyard_aspect_lo: float = 0.8
    auto_courtyard_aspect_hi: float = 1.25
    auto_courtyard_min_private: int = 5     # min private-room count to try a ring

    @classmethod
    def coerce(cls, value: Union["LayoutTuning", dict, None]) -> "LayoutTuning":
        if value is None:
            return cls()
        if isinstance(value, LayoutTuning):
            return value
        if isinstance(value, dict):
            return replace(cls(), **value)
        raise SketchValidationError(
            "tuning must be a LayoutTuning, a dict of overrides, or None."
        )


class HouseSketch:
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
        archetype: str = "auto",
        tuning: Union["LayoutTuning", dict, None] = None,
        mirror: Optional[bool] = None,
        seed: Optional[int] = None,
    ):
        """`archetype` picks the spatial idea used when no manual placement is
        given (position/east_of/etc. on any room still takes over completely):

          * "central_corridor" — public band at the front, private rooms in two
            columns flanking a central hall behind it (the original layout).
          * "single_loaded"    — public band at the front, private rooms in ONE
            column with the corridor as a strip beside it. Suits narrow plots.
          * "courtyard"        — public band at the front, private rooms form a
            U (back row + two side columns) around an open central courtyard
            instead of an indoor corridor.
          * "l_shape"          — a private wing and a public wing meet at a
            right angle, leaving an open notch (yard) — an L-shaped footprint.
          * "auto" (default)   — picks one of the above from the footprint's
            aspect ratio and room count; see `_choose_archetype`.

        `tuning` overrides the numeric assumptions the archetypes use (corridor
        widths, band depths, etc.) — see `LayoutTuning`. Pass a `LayoutTuning`
        instance or a dict of just the fields you want to change.

        `mirror` flips the finished (non-manual) layout left-right. Leave as
        None to let `seed` decide randomly each time — a free source of visual
        variety between two otherwise-similar requests. Pass True/False to pin
        it.

        `seed` controls the randomness used for `mirror` (when None) and for
        breaking ties when grouping rooms into columns/rows — e.g. which of two
        equal-area bedrooms lands on the left vs right. Leave unset for a fresh
        (non-reproducible) variation each call; set it for a reproducible one
        (e.g. hashing the user's request id) or to regenerate the same result.
        """
        if plot_width <= 0 or plot_depth <= 0:
            raise SketchValidationError("Plot dimensions must be positive.")
        valid_archetypes = {
            "auto", "central_corridor", "single_loaded", "courtyard", "l_shape",
        }
        if archetype not in valid_archetypes:
            raise SketchValidationError(
                f"archetype must be one of {sorted(valid_archetypes)}, got {archetype!r}"
            )
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
        self._requested_archetype = archetype
        self.archetype = archetype  # resolved to a concrete name in _layout()
        self.tuning = LayoutTuning.coerce(tuning)
        self._mirror_requested = mirror
        self._rng = random.Random(seed)
        self.mirrored = False

        self.footprint = Rect(
            setback, setback, plot_width - 2 * setback, plot_depth - 2 * setback
        )
        self.specs: List[RoomSpec] = self._coerce_specs(rooms)
        self.rooms: List[Room] = self._build_rooms(self.specs)
        if not self.rooms:
            raise SketchValidationError("At least one room is required.")

        self.manual = any(
            s.position is not None or s.anchor()[0] for s in self.specs
        )

        self.corridor: Optional[Room] = None
        self.openings: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        self.adjacency: Dict[str, List[dict]] = {}

        self.validate()
        self._layout()

    @classmethod
    def from_area(cls, plot_size: float, rooms, *, ratio: float = 1.2, **kw):
        if plot_size <= 0:
            raise SketchValidationError("plot_size must be positive.")
        width = math.sqrt(plot_size / ratio)
        depth = width * ratio
        return cls(width, depth, rooms, **kw)

    @staticmethod
    def _coerce_specs(rooms) -> List["RoomSpec"]:
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
                else:
                    specs.append(RoomSpec(type=item))
        return specs

    @staticmethod
    def _slug(text: str) -> str:
        return "-".join(text.lower().split())

    def _build_rooms(self, specs: List["RoomSpec"]) -> List[Room]:
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
            s.id = rid

            rooms.append(Room(type=s.type, label=label, id=rid, spec=s))
        # Kept so later auto-generated ids (e.g. the corridor) can't collide
        # with a user-supplied room id/label.
        self._used_ids: Set[str] = used_ids
        return rooms

    def _unique_id(self, base: str) -> str:
        """An id guaranteed not to collide with any room id already in use."""
        rid, k = base, 2
        while rid in self._used_ids:
            rid, k = f"{base}-{k}", k + 1
        self._used_ids.add(rid)
        return rid

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

    def required_area(self) -> float:
        return sum(self._area(r) for r in self.rooms) * self.circulation

    def validate(self) -> None:
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

        ids = {r.id for r in self.rooms}
        names = {r.label for r in self.rooms}
        for r in self.rooms:
            for ref in r.spec.adjacent_to if r.spec else []:
                if ref not in ids and ref not in names:
                    raise SketchValidationError(
                        f"{r.label!r} lists an unknown adjacent room {ref!r}."
                    )

    def _choose_archetype(self) -> str:
        """Pick a concrete archetype for archetype="auto".

        Heuristic, not a design judgement call the caller can't override:
        narrow/deep footprints favour a single loaded corridor (two columns +
        a hall would leave rooms too thin); squarish footprints with enough
        rooms to fill a ring favour a courtyard; everything else defaults to
        the central corridor. Pass an explicit `archetype=` to skip this.
        """
        fb = self.footprint
        t = self.tuning
        aspect = fb.w / fb.h if fb.h else 1.0
        private_n = len([r for r in self.rooms if not self._is_public(r)])
        if aspect < t.auto_narrow_aspect or aspect > t.auto_wide_aspect:
            return "single_loaded"
        if (
            t.auto_courtyard_aspect_lo <= aspect <= t.auto_courtyard_aspect_hi
            and private_n >= t.auto_courtyard_min_private
        ):
            return "courtyard"
        return "central_corridor"

    def _layout(self) -> None:
        if self.manual:
            self._layout_manual()
        else:
            if self.archetype == "auto":
                self.archetype = self._choose_archetype()
            {
                "central_corridor": self._layout_central_corridor,
                "single_loaded": self._layout_single_loaded,
                "courtyard": self._layout_courtyard,
                "l_shape": self._layout_l_shape,
            }[self.archetype]()
            self._check_min_sizes()
        self.adjacency = self._compute_adjacency()
        self._place_windows()

        if not self.manual:
            do_mirror = self._mirror_requested
            if do_mirror is None:
                do_mirror = self._rng.random() < 0.5
            if do_mirror:
                self._apply_mirror()
            self.mirrored = bool(do_mirror)

    def _mirror_point(self, p: Tuple[float, float]) -> Tuple[float, float]:
        return (2 * self.footprint.cx - p[0], p[1])

    def _mirror_rect(self, r: Rect) -> Rect:
        return Rect(2 * self.footprint.cx - r.x - r.w, r.y, r.w, r.h)

    def _apply_mirror(self) -> None:
        """Flip the finished layout left-right about the footprint's vertical
        centerline: a free, always-valid source of visual variety (every
        distance/area is preserved, only left/right is swapped). Runs after
        all geometry, doors, and windows are computed, so it's a pure
        coordinate transform of an already-valid plan."""
        for room in self.all_rooms:
            if room.rect:
                room.rect = self._mirror_rect(room.rect)
            room.doors = [
                Door(
                    leaf=(self._mirror_point(d.leaf[0]), self._mirror_point(d.leaf[1])),
                    arc=[self._mirror_point(p) for p in d.arc],
                )
                for d in room.doors
            ]
            room.windows = [
                Window(self._mirror_point(w.p0), self._mirror_point(w.p1))
                for w in room.windows
            ]
        self.openings = [
            (self._mirror_point(a), self._mirror_point(b)) for a, b in self.openings
        ]
        # Every room moved, so cached wall-segment data is stale — cheap to
        # just recompute rather than transform it in place.
        self.adjacency = self._compute_adjacency()

    def _resolve(self, ref: str) -> Optional[Room]:
        for r in self.rooms:
            if r.id == ref or r.label == ref:
                return r
        return None

    def neighbors_of(self, room_id: str) -> List[str]:
        return [e["neighbor"] for e in self.adjacency.get(room_id, [])]

    def _compute_adjacency(self) -> Dict[str, List[dict]]:
        rooms = [r for r in self.all_rooms if r.rect]
        adj: Dict[str, List[dict]] = {r.id: [] for r in rooms}
        eps = max(self.wall, 0.05) * 1.5
        min_overlap = 0.4

        for i, a in enumerate(rooms):
            for b in rooms[i + 1 :]:
                ra, rb = a.rect, b.rect
                seg = wall_a = wall_b = None
                if abs(ra.right - rb.x) < eps:
                    lo, hi = max(ra.y, rb.y), min(ra.bottom, rb.bottom)
                    if hi - lo > min_overlap:
                        seg = ((ra.right, lo), (ra.right, hi))
                        wall_a, wall_b = "right", "left"
                elif abs(rb.right - ra.x) < eps:
                    lo, hi = max(ra.y, rb.y), min(ra.bottom, rb.bottom)
                    if hi - lo > min_overlap:
                        seg = ((ra.x, lo), (ra.x, hi))
                        wall_a, wall_b = "left", "right"
                elif abs(ra.bottom - rb.y) < eps:
                    lo, hi = max(ra.x, rb.x), min(ra.right, rb.right)
                    if hi - lo > min_overlap:
                        seg = ((lo, ra.bottom), (hi, ra.bottom))
                        wall_a, wall_b = "bottom", "top"
                elif abs(rb.bottom - ra.y) < eps:
                    lo, hi = max(ra.x, rb.x), min(ra.right, rb.right)
                    if hi - lo > min_overlap:
                        seg = ((lo, ra.y), (hi, ra.y))
                        wall_a, wall_b = "top", "bottom"
                if seg:
                    adj[a.id].append({"neighbor": b.id, "wall": wall_a, "segment": seg})
                    adj[b.id].append({"neighbor": a.id, "wall": wall_b, "segment": seg})
        return adj

    @staticmethod
    def _aligned(anchor_start, anchor_len, room_len, align, offset):
        if align == "center":
            base = anchor_start + (anchor_len - room_len) / 2
        elif align == "end":
            base = anchor_start + anchor_len - room_len
        else:
            base = anchor_start
        return base + offset

    def _place_relative(self, room: Room, anchor: Room, relation: str) -> Rect:
        s, a = room.spec, anchor.rect
        if relation in ("east_of", "west_of"):
            h = s.depth if s.depth is not None else a.h
            w = s.width if s.width is not None else self._area(room) / h
            y = self._aligned(a.y, a.h, h, s.align, s.offset)
            x = a.right + s.gap if relation == "east_of" else a.x - w - s.gap
            return Rect(x, y, w, h)
        else:
            w = s.width if s.width is not None else a.w
            h = s.depth if s.depth is not None else self._area(room) / w
            x = self._aligned(a.x, a.w, w, s.align, s.offset)
            y = a.bottom + s.gap if relation == "south_of" else a.y - h - s.gap
            return Rect(x, y, w, h)

    def _resolve_positions(self) -> None:
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
                        continue
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
        fb = self.footprint
        self._resolve_positions()

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

        for i, a in enumerate(self.rooms):
            for b in self.rooms[i + 1 :]:
                ox = min(a.rect.right, b.rect.right) - max(a.rect.x, b.rect.x)
                oy = min(a.rect.bottom, b.rect.bottom) - max(a.rect.y, b.rect.y)
                if ox > 1e-6 and oy > 1e-6:
                    raise SketchValidationError(
                        f"{a.label!r} and {b.label!r} overlap."
                    )

        adj = self._compute_adjacency()

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

        for r in self.rooms:
            for w in r.spec.entrances if r.spec else []:
                self._side_door(r, w, into=inward[w])

    def _door_on_segment(self, room: Room, wall: str, segment) -> None:
        (sx, sy), (ex, ey) = segment
        cx, cy = (sx + ex) / 2, (sy + ey) / 2
        seg_len = math.hypot(ex - sx, ey - sy)
        dw = min(0.9, seg_len * 0.7)
        into = {"left": (1, 0), "right": (-1, 0), "top": (0, 1), "bottom": (0, -1)}[wall]
        if wall in ("left", "right"):
            hinge, wdir = (cx, cy - dw / 2), (0, 1)
        else:
            hinge, wdir = (cx - dw / 2, cy), (1, 0)
        room.doors.append(self._make_door(hinge, wdir, into, dw))
        room.door_walls.add(wall)

    def _connected_components(self, rooms: List[Room]) -> List[List[str]]:
        """Group room ids into components by declared `adjacent_to`, each
        internally ordered (via `_order_component`) so declared neighbours end
        up contiguous once a group is stacked/flowed in a line."""
        ids = {r.id for r in rooms}
        graph: Dict[str, Set[str]] = {r.id: set() for r in rooms}
        for r in rooms:
            for ref in r.spec.adjacent_to if r.spec else []:
                o = self._resolve(ref)
                if o and o.id in ids:
                    graph[r.id].add(o.id)
                    graph[o.id].add(r.id)

        seen: Set[str] = set()
        components: List[List[str]] = []
        for r in rooms:
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
        return components

    def _balance_groups(self, rooms: List[Room], k: int) -> List[List[Room]]:
        """Split `rooms` into `k` area-balanced groups, keeping each declared-
        adjacent component whole and in a single group (greedy: biggest
        components go first, each to whichever group is lightest so far).

        Components are shuffled before the (stable) sort-by-area, so ties
        between equal-area components/rooms break differently per `seed`
        instead of always the same way — this is the main source of layout
        variety between two requests with the same room program."""
        byid = {r.id: r for r in rooms}
        components = self._connected_components(rooms)
        self._rng.shuffle(components)
        components.sort(key=lambda c: sum(self._area(byid[i]) for i in c), reverse=True)
        groups: List[List[Room]] = [[] for _ in range(k)]
        totals = [0.0] * k
        for comp in components:
            a = sum(self._area(byid[i]) for i in comp)
            i = min(range(k), key=lambda idx: totals[idx])
            groups[i].extend(byid[j] for j in comp)
            totals[i] += a
        return groups

    def _adjacency_columns(self, private: List[Room]):
        left, right = self._balance_groups(private, 2)
        return left, right

    @staticmethod
    def _order_component(comp: Set[str], graph: Dict[str, Set[str]]) -> List[str]:
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

    # -- shared building blocks used by every non-manual archetype --------- #

    def _split_zones(self) -> Tuple[List[Room], List[Room]]:
        public = [r for r in self.rooms if self._is_public(r)]
        private = [r for r in self.rooms if not self._is_public(r)]
        return public, private

    def _front_depth(self, public: List[Room], private: List[Room], rect: Rect) -> float:
        """How deep (along Y) the public band at the front of `rect` should be."""
        t = self.tuning
        if public and private:
            pub_depths = [r.spec.depth for r in public if r.spec and r.spec.depth]
            if pub_depths:
                return min(max(pub_depths), t.front_depth_pinned_max_frac * rect.h)
            pub_area = sum(self._area(r) for r in public)
            lo, hi = t.front_depth_min, t.front_depth_max_frac * rect.h
            base = min(max(pub_area / rect.w, lo), hi)
            # Small seeded jitter for visual variety between similar requests;
            # still clamped to the same valid range as the un-jittered value.
            jittered = base * self._rng.uniform(0.93, 1.07)
            return min(max(jittered, lo), hi) if hi > lo else base
        if public:
            return rect.h
        return 0.0

    def _place_public_band(self, rooms: List[Room], rect: Rect) -> None:
        """Flow public rooms left-to-right across the full width of `rect`,
        living-room-first, with the standard left/right entrance doors and an
        open-plan gap between adjoining living/dining rooms."""
        if not rooms or rect.w <= 0 or rect.h <= 0:
            return
        any_custom_entrance = any(r.spec and r.spec.entrances for r in self.rooms)
        ordered = sorted(
            rooms, key=lambda r: (r.type != RoomType.LIVING_ROOM, -self._area(r))
        )
        widths = self._flow_sizes(
            rect.w,
            [r.spec.width if r.spec else None for r in ordered],
            [0.0 for _ in ordered],
            [self._area(r) for r in ordered],
        )
        x = rect.x
        for r, w in zip(ordered, widths):
            r.rect = Rect(x, rect.y, w, rect.h)
            x += w
        living = next((r for r in ordered if r.type == RoomType.LIVING_ROOM), None)
        dining = next((r for r in ordered if r.type == RoomType.DINING), None)

        if not any_custom_entrance:
            left_room = living or dining
            right_room = dining or living
            if left_room:
                self._side_door(left_room, "left", into=(1, 0))
            if right_room:
                self._side_door(right_room, "right", into=(-1, 0))

        if living and dining and living.rect and dining.rect:
            bound = (
                living.rect.right
                if abs(living.rect.right - dining.rect.x) < 1e-6
                else dining.rect.right
            )
            y0, y1 = rect.y, rect.bottom
            stub = self.tuning.archway_stub
            if y1 - y0 > 2 * stub:
                self.openings.append(((bound, y0 + stub), (bound, y1 - stub)))

    def _place_private_two_column(
        self, rooms: List[Room], rect: Rect, opens_onto_public: bool
    ) -> None:
        """Two columns of private rooms flanking a central hall — the classic
        central-corridor archetype, confined to an arbitrary `rect`."""
        if not rooms or rect.h <= 0:
            return
        bx, by, W, rear_depth = rect.x, rect.y, rect.w, rect.h
        if len(rooms) == 1:
            rooms[0].rect = Rect(bx, by, W, rear_depth)
            self._side_door(rooms[0], "bottom", into=(0, -1))
            return

        t = self.tuning
        cw = min(t.corridor_width_max, max(ROOM_MIN_SIDE[RoomType.CORRIDOR], W * t.corridor_width_frac_two_col))
        col_w = (W - cw) / 2
        left, right = self._adjacency_columns(rooms)

        self._stack(left, bx, by, col_w, rear_depth, door="right")
        self._stack(right, bx + col_w + cw, by, col_w, rear_depth, door="left")

        self.corridor = Room(
            RoomType.CORRIDOR,
            "Hall",
            Rect(bx + col_w, by, cw, rear_depth),
            id=self._unique_id("hall"),
        )
        if opens_onto_public:
            self.openings.append(
                (
                    (bx + col_w, by + rear_depth),
                    (bx + col_w + cw, by + rear_depth),
                )
            )
        else:
            self._side_door(self.corridor, "bottom", into=(0, -1))

    def _place_private_single_column(
        self, rooms: List[Room], rect: Rect, corridor_side: str, opens_onto_public: bool
    ) -> None:
        """One column of private rooms plus a corridor strip beside it, along
        `corridor_side` ('left' or 'right') of `rect`. Suits narrow plots."""
        if not rooms or rect.h <= 0:
            return
        bx, by, W, rear_depth = rect.x, rect.y, rect.w, rect.h
        needed = sum(self._min_d(r) for r in rooms)
        if needed > rear_depth + 1e-6:
            raise SketchValidationError(
                f"'single_loaded' stacks all {len(rooms)} private rooms in one "
                f"column, needing at least {needed:.1f} m of depth there but "
                f"only {rear_depth:.1f} m is available. This plot is too wide "
                f"and shallow for a single-loaded corridor — try "
                f"archetype='central_corridor' or 'courtyard' instead, or a "
                f"deeper/narrower plot."
            )
        t = self.tuning
        cw = min(t.corridor_width_max, max(ROOM_MIN_SIDE[RoomType.CORRIDOR], W * t.corridor_width_frac_single_col))
        if cw >= W:
            raise SketchValidationError(
                f"This wing is only {W:.1f} m wide, not enough for both a "
                f"room column and a {cw:.1f} m corridor. Widen the plot/wing "
                f"or use a different archetype."
            )
        col_w = W - cw
        room_x = bx + cw if corridor_side == "left" else bx
        hall_x = bx if corridor_side == "left" else bx + col_w
        door = "left" if corridor_side == "left" else "right"

        self._stack(rooms, room_x, by, col_w, rear_depth, door=door)

        self.corridor = Room(
            RoomType.CORRIDOR,
            "Hall",
            Rect(hall_x, by, cw, rear_depth),
            id=self._unique_id("hall"),
        )
        if opens_onto_public:
            self.openings.append(
                ((hall_x, by + rear_depth), (hall_x + cw, by + rear_depth))
            )
        else:
            self._side_door(self.corridor, "bottom", into=(0, -1))

    def _place_private_ring(self, rooms: List[Room], rect: Rect) -> None:
        """Private rooms form a U (back row + two side columns) around an open
        central courtyard — no indoor corridor; the courtyard is the void left
        in the middle, and each ring room opens onto it directly."""
        if not rooms or rect.h <= 0:
            return
        bx, by, W, D = rect.x, rect.y, rect.w, rect.h
        t = self.tuning
        back, left, right = self._balance_groups(rooms, 3)

        back_area = sum(self._area(r) for r in back)
        back_d = (
            min(max(back_area / W, t.courtyard_back_depth_min), t.courtyard_back_depth_max_frac * D)
            if back else 0.0
        )
        col_h = D - back_d

        left_area = sum(self._area(r) for r in left)
        right_area = sum(self._area(r) for r in right)
        left_w = (
            min(max(left_area / col_h, t.courtyard_col_width_min), t.courtyard_col_width_max_frac * W)
            if left and col_h > 0 else 0.0
        )
        right_w = (
            min(max(right_area / col_h, t.courtyard_col_width_min), t.courtyard_col_width_max_frac * W)
            if right and col_h > 0 else 0.0
        )

        if back:
            self._flow_row(back, bx, by, W, back_d, door="bottom")
        if left and col_h > 0:
            self._stack(left, bx, by + back_d, left_w, col_h, door="right")
        if right and col_h > 0:
            self._stack(right, bx + W - right_w, by + back_d, right_w, col_h, door="left")

    def _check_min_sizes(self) -> None:
        too_small: List[str] = []
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

    def _place_custom_entrances(self) -> None:
        inward = {"left": (1, 0), "right": (-1, 0), "top": (0, 1), "bottom": (0, -1)}
        for r in self.rooms:
            if r.rect and r.spec:
                for w in r.spec.entrances:
                    self._side_door(r, w, into=inward[w])

    # -- archetypes ----------------------------------------------------------- #

    def _layout_central_corridor(self) -> None:
        fb = self.footprint
        public, private = self._split_zones()
        front_depth = self._front_depth(public, private, fb)
        rear = Rect(fb.x, fb.y, fb.w, fb.h - front_depth)
        front = Rect(fb.x, fb.y + rear.h, fb.w, front_depth)

        self._place_private_two_column(private, rear, opens_onto_public=bool(public))
        self._place_public_band(public, front)
        self._place_custom_entrances()

    def _layout_single_loaded(self) -> None:
        fb = self.footprint
        public, private = self._split_zones()
        front_depth = self._front_depth(public, private, fb)
        rear = Rect(fb.x, fb.y, fb.w, fb.h - front_depth)
        front = Rect(fb.x, fb.y + rear.h, fb.w, front_depth)

        self._place_private_single_column(
            private, rear, corridor_side="right", opens_onto_public=bool(public)
        )
        self._place_public_band(public, front)
        self._place_custom_entrances()

    def _layout_courtyard(self) -> None:
        fb = self.footprint
        public, private = self._split_zones()
        front_depth = self._front_depth(public, private, fb)
        rear = Rect(fb.x, fb.y, fb.w, fb.h - front_depth)
        front = Rect(fb.x, fb.y + rear.h, fb.w, front_depth)

        if len(private) < 3:
            # Not enough rooms to form a meaningful ring — fall back cleanly.
            self._place_private_two_column(private, rear, opens_onto_public=bool(public))
        else:
            self._place_private_ring(private, rear)
        self._place_public_band(public, front)
        self._place_custom_entrances()

    def _layout_l_shape(self) -> None:
        fb = self.footprint
        public, private = self._split_zones()

        if not public or not private:
            # An L needs two distinct wings; fall back to the simple archetype.
            self._layout_central_corridor()
            return

        priv_area = sum(self._area(r) for r in private)
        pub_area = sum(self._area(r) for r in public)
        t = self.tuning
        wing_w = min(max(priv_area / fb.h, t.l_wing_min), t.l_wing_max_frac * fb.w)   # vertical (private) wing
        wing_h = min(
            max(pub_area / max(fb.w - wing_w, 1e-6), t.l_wing_min), t.l_wing_max_frac * fb.h
        )  # horizontal (public) wing

        vertical = Rect(fb.x, fb.y, wing_w, fb.h)
        horizontal = Rect(fb.x + wing_w, fb.y + fb.h - wing_h, fb.w - wing_w, wing_h)
        # The notch (fb.x+wing_w .. fb.right, fb.y .. horizontal.y) is left
        # empty — an open yard tucked into the L.

        self._place_private_single_column(
            private, vertical, corridor_side="right", opens_onto_public=False
        )
        self._place_public_band(public, horizontal)
        self._place_custom_entrances()

        # The private wing's hall meets the public wing along a VERTICAL
        # shared wall (the wings sit side by side, not stacked), so the
        # horizontal-opening logic in _place_private_single_column doesn't
        # apply here — open a vertical archway between them directly.
        if self.corridor:
            c, h = self.corridor.rect, horizontal
            lo, hi = max(c.y, h.y), min(c.bottom, h.bottom)
            stub = t.archway_stub
            if hi - lo > 2 * stub and abs(c.right - h.x) < 1e-6:
                self.openings.append(((c.right, lo + stub), (c.right, hi - stub)))

    def _flow_row(self, rooms, x, y, total_w, h, door) -> None:
        """Place rooms left-to-right, sharing height `h`; each gets a door on
        `door` ('top' or 'bottom') facing away from the row. The horizontal
        analogue of `_stack`."""
        if not rooms:
            return
        widths = self._flow_sizes(
            total_w,
            [r.spec.width if r.spec else None for r in rooms],
            [self._min_w(r) for r in rooms],
            [self._area(r) for r in rooms],
        )
        into = (0, -1) if door == "bottom" else (0, 1)
        cx = x
        for r, w in zip(rooms, widths):
            r.rect = Rect(cx, y, w, h)
            cx += w
            self._side_door(r, door, into=into)

    def _stack(self, rooms, x, y, w, total_h, door) -> None:
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
        pinned = sum(f for f in fixed if f is not None)
        if pinned > total + 1e-6:
            raise SketchValidationError(
                f"Pinned room sizes ({pinned:.1f} m) exceed the available "
                f"{total:.1f} m along that axis. Enlarge the plot or shrink them."
            )
        flex = [i for i, f in enumerate(fixed) if f is None]
        if not flex:
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
            else:
                sizes[i] = fareas[k] / ta * rem
        return sizes

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
        else:
            hinge, wdir = (rect.x, rect.cy - dw / 2), (0, 1)
        room.doors.append(self._make_door(hinge, wdir, into, dw))
        room.door_walls.add(wall)

    @staticmethod
    def _subtract_intervals(a: float, b: float, covered) -> List[Tuple[float, float]]:
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

        edges = {
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
                if abs(x0 - x1) < 1e-9:
                    c = (y0 + y1) / 2
                    room.windows.append(Window((x0, c - win / 2), (x0, c + win / 2)))
                else:
                    c = (x0 + x1) / 2
                    room.windows.append(Window((c - win / 2, y0), (c + win / 2, y0)))

    def _rooms_bbox(self) -> Rect:
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

    C_SHEET = "#FFFFFF"
    C_LOT = "#FCFBF7"
    C_LOT_LINE = "#9AA3AD"
    C_WALL = LEGEND["remaining_wall"]
    C_PARTITION = LEGEND["remaining_wall"]
    C_WINDOW = LEGEND["window"]
    C_DOOR = LEGEND["remaining_wall"]
    C_LABEL = "#2B333B"
    C_DIM = "#9AA3AD"

    def _draw(self, surf: "_Surface", t: "_Transform") -> None:
        plot = self.plot
        wall_px = max(6, int(self.wall * t.scale))
        part_px = max(4, int(self.wall * t.scale * 0.7))

        surf.rect(*t.box(plot), fill=self.C_LOT, stroke=self.C_LOT_LINE, width=2)

        for r in self.all_rooms:
            surf.rect(*t.box(r.rect), fill=ROOM_COLOR[r.type], stroke=None)

        for r in self.all_rooms:
            surf.rect(*t.box(r.rect), fill=None, stroke=self.C_PARTITION, width=part_px)

        for r in self.all_rooms:
            for _side, seg in self._exterior_segments(r):
                surf.line(*t.pt(seg[0]), *t.pt(seg[1]), stroke=self.C_WALL, width=wall_px)

        for seg in self.openings:
            self._erase(surf, t, seg[0], seg[1], part_px)

        for r in self.all_rooms:
            for w in r.windows:
                self._draw_window(surf, t, w, wall_px)

        for r in self.all_rooms:
            for d in r.doors:
                self._erase(surf, t, d.leaf[0], d.arc[-1], wall_px)
                surf.line(
                    *t.pt(d.leaf[0]), *t.pt(d.leaf[1]), stroke=self.C_DOOR, width=4
                )
                surf.polyline([t.pt(p) for p in d.arc], stroke=self.C_DOOR, width=1)

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
        p0, p1 = t.pt(w.p0), t.pt(w.p1)
        surf.line(p0[0], p0[1], p1[0], p1[1], stroke=self.C_WINDOW, width=wall_px)
        surf.line(p0[0], p0[1], p1[0], p1[1], stroke=self.C_WALL, width=max(1, wall_px // 4))

    def _erase(self, surf, t, a, b, wall_px) -> None:
        half = wall_px * 0.7 + 1
        ax, ay = t.pt(a)
        bx, by = t.pt(b)
        if abs(ay - by) < abs(ax - bx):
            surf.rect(min(ax, bx), ay - half, max(ax, bx), ay + half, fill="#FFFFFF")
        else:
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
        margin = (95, 95, 270, 95)
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
                "adjacent_to": list(s.adjacent_to) if s else [],
                "neighbors": self.neighbors_of(r.id),
                "doors": len(r.doors),
                "windows": len(r.windows),
            }

        return {
            "archetype": self.archetype if not self.manual else "manual",
            "mirrored": self.mirrored,
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


if __name__ == "__main__":
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
