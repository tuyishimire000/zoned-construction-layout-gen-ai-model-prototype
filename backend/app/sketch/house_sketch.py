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
    type: RoomType
    label: str
    rect: Optional[Rect] = None
    doors: List[Door] = field(default_factory=list)
    windows: List[Window] = field(default_factory=list)
    door_walls: Set[str] = field(default_factory=set)


class SketchValidationError(ValueError):
    """Raised when the requested rooms cannot reasonably fit the plot."""


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
        rooms: Union[Dict[Union[str, RoomType], int], List[Union[str, RoomType]]],
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
        self.rooms: List[Room] = self._expand_rooms(rooms)
        if not self.rooms:
            raise SketchValidationError("At least one room is required.")

        self.corridor: Optional[Room] = None
        # Wall segments left open as passages (corridor mouth, open-plan, etc.).
        self.openings: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []

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
    def _expand_rooms(rooms) -> List[Room]:
        counts: Dict[RoomType, int] = {}
        if isinstance(rooms, dict):
            for rtype, n in rooms.items():
                rt = _normalize(rtype)
                counts[rt] = counts.get(rt, 0) + int(n)
        else:
            for rtype in rooms:
                rt = _normalize(rtype)
                counts[rt] = counts.get(rt, 0) + 1

        out: List[Room] = []
        for rtype, n in counts.items():
            for i in range(n):
                label = rtype.value.replace("_", " ").title()
                if n > 1:
                    label = f"{label} {i + 1}"
                out.append(Room(type=rtype, label=label))
        return out

    @property
    def all_rooms(self) -> List[Room]:
        return self.rooms + ([self.corridor] if self.corridor else [])

    # -- validation --------------------------------------------------------- #

    def required_area(self) -> float:
        """Desired total floor area incl. a circulation allowance."""
        return sum(ROOM_AREA[r.type] for r in self.rooms) * self.circulation

    def validate(self) -> None:
        """Raise SketchValidationError if the rooms cannot fit the plot."""
        buildable = self.footprint.area
        needed = self.required_area()
        if needed > buildable + 1e-6:
            raise SketchValidationError(
                f"Rooms need about {needed:.0f} m² (incl. circulation) but the "
                f"buildable footprint is only {buildable:.0f} m² "
                f"({self.plot.area:.0f} m² plot minus {self.setback} m setbacks). "
                f"Reduce rooms, shrink setbacks, or enlarge the plot."
            )

    # -- layout: central corridor + full-width public band ------------------ #

    def _layout(self) -> None:
        bx, by, W, D = (
            self.footprint.x,
            self.footprint.y,
            self.footprint.w,
            self.footprint.h,
        )

        public = [r for r in self.rooms if r.type in PUBLIC_TYPES]
        private = [r for r in self.rooms if r.type not in PUBLIC_TYPES]

        # Front public band depth (full width). Target ~4 m deep so the living
        # room reads as 6.5 x 4, kept within bounds so the rear keeps enough depth.
        if public and private:
            pub_area = sum(ROOM_AREA[r.type] for r in public)
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
                left, right, la, ra = [], [], 0.0, 0.0
                for r in sorted(private, key=lambda r: ROOM_AREA[r.type], reverse=True):
                    if la <= ra:
                        left.append(r)
                        la += ROOM_AREA[r.type]
                    else:
                        right.append(r)
                        ra += ROOM_AREA[r.type]

                self._stack(left, bx, by, col_w, rear_depth, door="right")
                self._stack(right, bx + col_w + cw, by, col_w, rear_depth, door="left")

                self.corridor = Room(
                    RoomType.CORRIDOR, "Hall", Rect(bx + col_w, by, cw, rear_depth)
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
            total = sum(ROOM_AREA[r.type] for r in public)
            x = bx
            # Living first (left), then dining, so the entry lands on the living.
            ordered = sorted(
                public,
                key=lambda r: (r.type != RoomType.LIVING_ROOM, -ROOM_AREA[r.type]),
            )
            for r in ordered:
                w = ROOM_AREA[r.type] / total * W
                r.rect = Rect(x, by + rear_depth, w, front_depth)
                x += w
            living = next((r for r in ordered if r.type == RoomType.LIVING_ROOM), None)
            dining = next((r for r in ordered if r.type == RoomType.DINING), None)

            # Entrances on the two long (12 m) sides of the house: into the living
            # room on the left and the dining room on the right. If only one public
            # room exists it spans the full width and takes both entrances.
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

        # Windows on every exterior wall (skipping walls that hold a door).
        for r in self.all_rooms:
            self._exterior_windows(r)

        # Min-size sanity check.
        for r in self.all_rooms:
            if r.rect and min(r.rect.w, r.rect.h) < ROOM_MIN_SIDE[r.type] - 1e-6:
                too_small.append(
                    f"{r.label} would be {r.rect.w:.1f}x{r.rect.h:.1f} m "
                    f"(min side {ROOM_MIN_SIDE[r.type]} m)"
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
        areas = [ROOM_AREA[r.type] for r in rooms]
        mins = [ROOM_MIN_SIDE[r.type] for r in rooms]
        extra = total_h - sum(mins)
        if extra >= 0:
            total_area = sum(areas)
            heights = [m + extra * a / total_area for m, a in zip(mins, areas)]
        else:  # column can't even fit the minimums; validation will flag it
            total_area = sum(areas)
            heights = [a / total_area * total_h for a in areas]

        cy = y
        for r, h in zip(rooms, heights):
            r.rect = Rect(x, cy, w, h)
            cy += h
            self._side_door(r, door, into=((1, 0) if door == "left" else (-1, 0)))

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

    def _exterior_windows(self, room: Room) -> None:
        fb, eps = self.footprint, 1e-6
        rect = room.rect
        if rect is None:
            return

        def add(p0, p1):
            room.windows.append(Window(p0, p1))

        if abs(rect.y - fb.y) < eps and "top" not in room.door_walls and rect.w > 1.4:
            c, L = rect.cx, min(1.6, rect.w * 0.5)
            add((c - L / 2, rect.y), (c + L / 2, rect.y))
        if (
            abs(rect.bottom - fb.bottom) < eps
            and "bottom" not in room.door_walls
            and rect.w > 1.4
        ):
            c, L = rect.cx, min(1.6, rect.w * 0.5)
            add((c - L / 2, rect.bottom), (c + L / 2, rect.bottom))
        if abs(rect.x - fb.x) < eps and "left" not in room.door_walls and rect.h > 1.4:
            c, L = rect.cy, min(1.6, rect.h * 0.5)
            add((rect.x, c - L / 2), (rect.x, c + L / 2))
        if (
            abs(rect.right - fb.right) < eps
            and "right" not in room.door_walls
            and rect.h > 1.4
        ):
            c, L = rect.cy, min(1.6, rect.h * 0.5)
            add((rect.right, c - L / 2), (rect.right, c + L / 2))

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
        fb, plot = self.footprint, self.plot
        # Solid wall bands: exterior heavier than interior partitions.
        wall_px = max(6, int(self.wall * t.scale))
        part_px = max(4, int(self.wall * t.scale * 0.7))

        # Property boundary (lot) — light fill, thin line, generous yard around.
        surf.rect(*t.box(plot), fill=self.C_LOT, stroke=self.C_LOT_LINE, width=2)

        # Building base.
        surf.rect(*t.box(fb), fill="#FFFFFF", stroke=None)

        # Room fills (walls are drawn separately as solid bands on top).
        for r in self.all_rooms:
            surf.rect(*t.box(r.rect), fill=ROOM_COLOR[r.type], stroke=None)

        # Interior partitions: solid thick black bands on room boundaries.
        for r in self.all_rooms:
            surf.rect(*t.box(r.rect), fill=None, stroke=self.C_PARTITION, width=part_px)

        # Exterior wall: a heavier solid black band around the footprint.
        surf.rect(*t.box(fb), fill=None, stroke=self.C_WALL, width=wall_px)

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

        # Overall building dimensions, north arrow, title, scale bar.
        self._dim(surf, t, (fb.x, fb.y), (fb.right, fb.y), -24, f"{fb.w:.1f} m")
        self._dim(
            surf,
            t,
            (fb.right, fb.y),
            (fb.right, fb.bottom),
            24,
            f"{fb.h:.1f} m",
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
    sketch = HouseSketch(
        plot_width=16,
        plot_depth=18,
        rooms={
            "bedroom": 3,
            "bathroom": 1,
            "kitchen": 1,
            "living_room": 1,
            "dining": 1,
        },
        setback=3.0,
    )
    sketch.to_png("house.png")
    sketch.to_svg("house.svg")
    print("Wrote house.png and house.svg")
    print(f"Buildable footprint: {sketch.footprint.w:.1f} x {sketch.footprint.h:.1f} m")
    print(f"Required area (incl. circulation): {sketch.required_area():.0f} m2")
