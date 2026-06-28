"""PNG renderer: draws a FloorPlan model to a base64-encoded PNG.

Owns everything presentational — the meters-to-pixels transform, colors, fonts,
furniture glyphs, walls/doors/windows and drawing-sheet chrome (dimensions,
north arrow, title block, scale bar). It reads geometry from the model in meters
and never decides layout itself.
"""

import io
import math
import base64

from PIL import Image, ImageDraw, ImageFont

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

CANVAS_W = 1600
CANVAS_H = 1200
MARGIN = 130  # leaves room for dimension lines outside the plot

# Palette
BG = (245, 247, 248)
GRASS_FILL = (236, 244, 230)
GRASS_LINE = (129, 199, 132)
WALL_DARK = (40, 50, 60)      # exterior walls
WALL_THIN = (80, 95, 110)     # interior partitions
DOOR_COLOR = (0, 100, 180)
WINDOW_GLASS = (120, 190, 230)
WINDOW_FRAME = (40, 90, 130)
CONCRETE = (220, 225, 230)
BUILDING_FILL = (255, 255, 255)
TEXT_COLOR = (50, 60, 70)
DIM_COLOR = (90, 100, 110)

ROOM_COLORS = {
    "bedrooms": "#C8E6C9",
    "bathrooms": "#BBDEFB",
    "kitchens": "#FFE082",
    "living_rooms": "#F8BBD0",
    "offices": "#E1BEE7",
}

SCALE_BAR_METERS = 5


def _load_font(size: int):
    """Best-effort TrueType font, falling back to PIL's bitmap default."""
    for path in (
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_ROOM = _load_font(22)
FONT_DIM = _load_font(17)
FONT_SMALL = _load_font(15)
FONT_TITLE = _load_font(21)


class _Transform:
    """Maps model meters onto canvas pixels with a single uniform scale."""

    def __init__(self, plan: FloorPlan):
        avail_w = CANVAS_W - 2 * MARGIN
        avail_h = CANVAS_H - 2 * MARGIN
        self.scale = min(avail_w / plan.plot.width, avail_h / plan.plot.height)
        self.ox = MARGIN + (avail_w - plan.plot.width * self.scale) / 2
        self.oy = MARGIN + (avail_h - plan.plot.height * self.scale) / 2

    def x(self, mx: float) -> float:
        return self.ox + mx * self.scale

    def y(self, my: float) -> float:
        return self.oy + my * self.scale

    def pt(self, p):
        return (self.x(p[0]), self.y(p[1]))

    def box(self, r: Rect):
        return [self.x(r.x), self.y(r.y), self.x(r.right), self.y(r.bottom)]


# --- Site features -------------------------------------------------------- #


def _draw_site_feature(draw, t, f: SiteFeature):
    if f.points:
        scaled_pts = [(t.x(px), t.y(py)) for px, py in f.points]
        if f.type == FeatureType.PATH:
            draw.line(scaled_pts, fill="#E0E0E0", width=int(t.scale * 1.5), joint="curve")
        elif f.type == FeatureType.DRIVEWAY:
            draw.line(scaled_pts, fill="#BDBDBD", width=int(t.scale * 3.0), joint="curve")
        return

    if f.type == FeatureType.GRASS:
        draw.rectangle(t.box(f.bounds), fill=GRASS_FILL, outline=GRASS_LINE, width=4)
    elif f.type == FeatureType.TREE:
        x0, y0, x1, y1 = t.box(f.bounds)
        draw.ellipse([x0, y0, x1, y1], fill=(129, 199, 132), outline=(56, 142, 60), width=2)
        off = (x1 - x0) * 0.3
        draw.ellipse([x0 + off, y0, x1 + off, y1 - off], fill=(174, 213, 129), outline=(56, 142, 60))
    elif f.type in (FeatureType.DRIVEWAY, FeatureType.PATH):
        draw.rectangle(t.box(f.bounds), fill=CONCRETE, outline=WALL_DARK, width=3)
        if f.label:
            cx, cy = (t.x(f.bounds.cx), t.y(f.bounds.bottom) - 16)
            draw.text((cx, cy), f.label, fill=TEXT_COLOR, font=FONT_SMALL, anchor="mm")
    elif f.type == FeatureType.CORRIDOR:
        draw.rectangle(t.box(f.bounds), fill="#CFD8DC", outline="#90A4AE", width=1)
        if f.label:
            draw.text((t.x(f.bounds.cx), t.y(f.bounds.cy)), f.label, fill="#455A64",
                      font=FONT_SMALL, anchor="mm")
    elif f.type == FeatureType.PARKING:
        x0, y0, x1, y1 = t.box(f.bounds)
        draw.rectangle([x0, y0, x1, y1], fill="#9E9E9E", outline="#616161", width=2)
        if f.label:
            draw.text(((x0 + x1) / 2, (y0 + y1) / 2), f.label, fill="#FFFFFF",
                      font=FONT_SMALL, anchor="mm")


# --- Furniture glyphs (boxes are in meters) ------------------------------- #


def _draw_furniture(draw, t, item: Furniture):
    x0, y0, x1, y1 = t.box(item.bounds)
    w, h = x1 - x0, y1 - y0
    if item.type == "bed":
        draw.rectangle([x0, y0, x1, y1], fill="#E0F7FA", outline="#4DD0E1", width=2)
        draw.rectangle([x0 + w * 0.1, y0 + h * 0.1, x1 - w * 0.1, y0 + h * 0.35], fill="#FFFFFF", outline="#4DD0E1", width=1)
    elif item.type == "wardrobe":
        draw.rectangle([x0, y0, x1, y1], fill="#A1887F", outline="#7B5E54", width=2)
    elif item.type == "bathtub":
        draw.rectangle([x0, y0, x1, y1], fill="#E3F2FD", outline="#90CAF9", width=2)
    elif item.type == "toilet":
        draw.rectangle([x0 + w*0.2, y0, x1 - w*0.2, y0 + h*0.3], fill="#FFFFFF", outline="#B0BEC5", width=2)
        draw.ellipse([x0 + w*0.15, y0 + h*0.3, x1 - w*0.15, y1], fill="#FFFFFF", outline="#B0BEC5", width=2)
    elif item.type == "sink":
        draw.rectangle([x0, y0, x1, y1], fill="#F5F5F5", outline="#E0E0E0", width=2)
        draw.ellipse([x0 + w*0.15, y0 + h*0.15, x1 - w*0.15, y1 - h*0.15], fill="#FFFFFF", outline="#B0BEC5", width=1)
    elif item.type == "kitchen_counter":
        draw.rectangle([x0, y0, x1, y1], fill="#BDBDBD", outline="#757575", width=2)
    elif item.type == "kitchen_island":
        draw.rectangle([x0, y0, x1, y1], fill="#EEEEEE", outline="#BDBDBD", width=2)
    elif item.type == "sofa":
        draw.rectangle([x0, y0 + h * 0.3, x1, y1], fill="#90CAF9", outline="#5C9CD6")
        draw.rectangle([x0 + w * 0.1, y0, x1 - w * 0.1, y0 + h * 0.5], fill="#90CAF9", outline="#5C9CD6")
    elif item.type == "tv_stand":
        draw.rectangle([x0, y0, x1, y1], fill="#424242", outline="#212121", width=2)
    elif item.type == "desk":
        draw.rectangle([x0, y0, x1, y0 + h * 0.55], fill="#A1887F", outline="#7B5E54")
        r = min(w, h) * 0.3
        draw.ellipse([x0 + w * 0.35, y1 - r*2, x0 + w * 0.35 + r*2, y1], fill="#607D8B")


def _draw_interior_walls(draw, t, plan: FloorPlan):
    """Single thick lines on room boundaries (the partitions between spaces)."""
    width = max(2, int(plan.wall_thickness * t.scale * 0.7))
    for room in plan.rooms + plan.annex_rooms:
        draw.rectangle(t.box(room.bounds), outline=WALL_THIN, width=width)

def _draw_exterior_walls(draw, t, plan: FloorPlan):
    """Draw thick lines only on exposed edges to support non-rectangular shapes."""
    wt = plan.wall_thickness
    
    def is_exposed(cx, cy, all_rooms):
        # A point slightly outside the wall center
        for r in all_rooms:
            if r.bounds.x < cx < r.bounds.right and r.bounds.y < cy < r.bounds.bottom:
                return False
        return True

    all_rooms = plan.rooms + plan.annex_rooms
    
    for room in all_rooms:
        b = room.bounds
        # Top edge
        if is_exposed(b.cx, b.y - 0.1, all_rooms):
            draw.line([t.x(b.x), t.y(b.y), t.x(b.right), t.y(b.y)], fill=WALL_DARK, width=4)
        # Bottom edge
        if is_exposed(b.cx, b.bottom + 0.1, all_rooms):
            draw.line([t.x(b.x), t.y(b.bottom), t.x(b.right), t.y(b.bottom)], fill=WALL_DARK, width=4)
        # Left edge
        if is_exposed(b.x - 0.1, b.cy, all_rooms):
            draw.line([t.x(b.x), t.y(b.y), t.x(b.x), t.y(b.bottom)], fill=WALL_DARK, width=4)
        # Right edge
        if is_exposed(b.right + 0.1, b.cy, all_rooms):
            draw.line([t.x(b.right), t.y(b.y), t.x(b.right), t.y(b.bottom)], fill=WALL_DARK, width=4)

    # We removed the global BUILDING_FILL earlier, so we don't need to draw the inner outline anymore.


def _opening_endpoints(o: Opening):
    """(start, end) meter points of the opening segment along its wall."""
    if o.orientation == Orientation.HORIZONTAL:
        return (o.x, o.y), (o.x + o.length, o.y)
    return (o.x, o.y), (o.x, o.y + o.length)


def _cut_gap(draw, t, plan: FloorPlan, o: Opening, color=BUILDING_FILL):
    """Overpaint the wall along the opening so it reads as an opening, not a wall."""
    half = max(t.scale * plan.wall_thickness, 4) * 0.9
    (sx, sy), (ex, ey) = _opening_endpoints(o)
    p0 = t.pt((sx, sy))
    p1 = t.pt((ex, ey))
    if o.orientation == Orientation.HORIZONTAL:
        draw.rectangle([p0[0], p0[1] - half, p1[0], p1[1] + half], fill=color)
    else:
        draw.rectangle([p0[0] - half, p0[1], p1[0] + half, p1[1]], fill=color)


def _draw_window(draw, t, plan: FloorPlan, o: Opening):
    _cut_gap(draw, t, plan, o, color=BUILDING_FILL)
    (sx, sy), (ex, ey) = _opening_endpoints(o)
    p0, p1 = t.pt((sx, sy)), t.pt((ex, ey))
    frame = max(t.scale * plan.wall_thickness, 4) * 0.45
    if o.orientation == Orientation.HORIZONTAL:
        draw.rectangle([p0[0], p0[1] - frame, p1[0], p1[1] + frame], outline=WINDOW_FRAME, width=2)
        draw.line([p0[0], p0[1], p1[0], p1[1]], fill=WINDOW_GLASS, width=3)
    else:
        draw.rectangle([p0[0] - frame, p0[1], p1[0] + frame, p1[1]], outline=WINDOW_FRAME, width=2)
        draw.line([p0[0], p0[1], p1[0], p1[1]], fill=WINDOW_GLASS, width=3)


def _door_vectors(plan: FloorPlan, o: Opening):
    """Return (hinge, wall_dir, normal) in meters for a door's leaf and arc."""
    (sx, sy), (ex, ey) = _opening_endpoints(o)
    if o.hinge_at_start:
        hinge = (sx, sy)
        wall_dir = (ex - sx, ey - sy)
    else:
        hinge = (ex, ey)
        wall_dir = (sx - ex, sy - ey)
    mag = math.hypot(*wall_dir) or 1.0
    wall_dir = (wall_dir[0] / mag, wall_dir[1] / mag)

    swing = o.swing
    if swing is None:
        # Default: open toward the building interior (center).
        if o.orientation == Orientation.HORIZONTAL:
            swing = "up" if plan.building.cy < o.y else "down"
        else:
            swing = "left" if plan.building.cx < o.x else "right"
    normal = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[swing]
    return hinge, wall_dir, normal


def _draw_door(draw, t, plan: FloorPlan, o: Opening):
    _cut_gap(draw, t, plan, o, color=BUILDING_FILL)
    hinge, wall_dir, normal = _door_vectors(plan, o)
    leaf = o.length

    hx, hy = t.pt(hinge)
    r = leaf * t.scale

    # Door leaf (the open panel), pointing along the swing normal.
    leaf_end = t.pt((hinge[0] + normal[0] * leaf, hinge[1] + normal[1] * leaf))
    draw.line([hx, hy, leaf_end[0], leaf_end[1]], fill=DOOR_COLOR, width=3)

    # Swing arc: the 90° quarter between the wall direction and the leaf.
    a_wall = math.degrees(math.atan2(wall_dir[1], wall_dir[0])) % 360
    a_norm = math.degrees(math.atan2(normal[1], normal[0])) % 360
    if (a_norm - a_wall) % 360 == 90:
        start, end = a_wall, a_norm
    else:
        start, end = a_norm, a_wall
    draw.arc([hx - r, hy - r, hx + r, hy + r], start, end, fill=DOOR_COLOR, width=2)


# --- Rooms ---------------------------------------------------------------- #


def _draw_room_fill(draw, t, room: Room):
    draw.rectangle(t.box(room.bounds), fill=ROOM_COLORS.get(room.type, "#EEEEEE"))


def _draw_room_label(draw, t, room: Room):
    cx, cy = t.x(room.bounds.cx), t.y(room.bounds.cy)
    draw.text((cx, cy - 9), room.label, fill=TEXT_COLOR, font=FONT_ROOM, anchor="mm")
    dim = f"{room.bounds.width:.1f} x {room.bounds.height:.1f} m"
    draw.text((cx, cy + 12), dim, fill="#78909C", font=FONT_SMALL, anchor="mm")


# --- Dimensions, north arrow, chrome -------------------------------------- #


def _tick(draw, x, y, size=6):
    draw.line([x - size, y + size, x + size, y - size], fill=DIM_COLOR, width=2)


def _draw_dim(draw, t, p1, p2, offset, text, vertical=False):
    """Architectural dimension line with end ticks and a centered label."""
    if not vertical:
        yb = t.y(p1[1])
        yl = yb + offset
        x1, x2 = t.x(p1[0]), t.x(p2[0])
        draw.line([x1, yb, x1, yl], fill=DIM_COLOR, width=1)
        draw.line([x2, yb, x2, yl], fill=DIM_COLOR, width=1)
        draw.line([x1, yl, x2, yl], fill=DIM_COLOR, width=2)
        _tick(draw, x1, yl)
        _tick(draw, x2, yl)
        ty = yl - 12 if offset < 0 else yl + 12
        draw.text(((x1 + x2) / 2, ty), text, fill=DIM_COLOR, font=FONT_DIM, anchor="mm")
    else:
        xb = t.x(p1[0])
        xl = xb + offset
        y1, y2 = t.y(p1[1]), t.y(p2[1])
        draw.line([xb, y1, xl, y1], fill=DIM_COLOR, width=1)
        draw.line([xb, y2, xl, y2], fill=DIM_COLOR, width=1)
        draw.line([xl, y1, xl, y2], fill=DIM_COLOR, width=2)
        _tick(draw, xl, y1)
        _tick(draw, xl, y2)
        tx = xl - 14 if offset < 0 else xl + 14
        draw.text((tx, (y1 + y2) / 2), text, fill=DIM_COLOR, font=FONT_DIM, anchor="mm")


def _draw_dimensions(draw, t, plan: FloorPlan):
    plot, b = plan.plot, plan.building
    # Overall plot extents.
    _draw_dim(draw, t, (0, 0), (plot.width, 0), -60, f"{plot.width:.1f} m")
    _draw_dim(draw, t, (0, 0), (0, plot.height), -60, f"{plot.height:.1f} m", vertical=True)
    # Building footprint.
    _draw_dim(draw, t, (b.x, b.bottom), (b.right, b.bottom), 45, f"{b.width:.1f} m")
    _draw_dim(draw, t, (b.right, b.y), (b.right, b.bottom), 45, f"{b.height:.1f} m", vertical=True)
    # Front setback (building front → street boundary), on the right side.
    _draw_dim(draw, t, (b.right, b.bottom), (b.right, plot.height), 90,
              f"{plot.height - b.bottom:.1f} m", vertical=True)
    # Side setback (left boundary → building), along the building top.
    _draw_dim(draw, t, (0, b.y), (b.x, b.y), -28, f"{b.x:.1f} m")


def _draw_north(draw):
    nx, ny = MARGIN - 40, MARGIN + 10
    draw.ellipse([nx - 18, ny - 18, nx + 18, ny + 18], outline=WALL_DARK, width=2)
    draw.line([nx, ny + 14, nx, ny - 14], fill=WALL_DARK, width=3)
    draw.polygon([(nx, ny - 20), (nx - 6, ny - 8), (nx + 6, ny - 8)], fill=WALL_DARK)
    draw.text((nx, ny - 32), "N", fill=WALL_DARK, font=FONT_DIM, anchor="mm")


def _draw_chrome(draw, t, plan: FloorPlan):
    # Title block (top-right).
    tx0, ty0 = CANVAS_W - 380, MARGIN - 70
    draw.rectangle([tx0, ty0, CANVAS_W - 40, ty0 + 92], fill="#FFFFFF",
                   outline=WALL_DARK, width=2)
    draw.text((tx0 + 14, ty0 + 14), "PROPOSED SITE PLAN", fill=WALL_DARK, font=FONT_TITLE)
    draw.text((tx0 + 14, ty0 + 46), f"Usage: {plan.usage.capitalize()}", fill=TEXT_COLOR, font=FONT_SMALL)
    draw.text((tx0 + 14, ty0 + 66), f"Plot: {plan.plot_size_sqm:.0f} sqm   Floors: {plan.floors}",
              fill=TEXT_COLOR, font=FONT_SMALL)

    # Graphical scale bar (bottom-right).
    bar = SCALE_BAR_METERS * t.scale
    x1 = CANVAS_W - MARGIN
    x0 = x1 - bar
    y = CANVAS_H - MARGIN + 70
    draw.line([x0, y, x1, y], fill=WALL_DARK, width=4)
    draw.line([x0, y - 6, x0, y + 6], fill=WALL_DARK, width=2)
    draw.line([x1, y - 6, x1, y + 6], fill=WALL_DARK, width=2)
    draw.line([x0 + bar / 2, y - 4, x0 + bar / 2, y + 4], fill=WALL_DARK, width=2)
    draw.text((x0, y + 14), "0", fill=WALL_DARK, font=FONT_SMALL, anchor="mm")
    draw.text((x1, y + 14), f"{SCALE_BAR_METERS} m", fill=WALL_DARK, font=FONT_SMALL, anchor="mm")


def render_png_bytes(plan: FloorPlan) -> bytes:
    """Render a FloorPlan to raw PNG bytes."""
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), color=BG)
    draw = ImageDraw.Draw(img)
    t = _Transform(plan)

    # Ground: grass, then driveway/trees.
    for f in plan.site_features:
        if f.type in (FeatureType.GRASS, FeatureType.TREE):
            _draw_site_feature(draw, t, f)
    for f in plan.site_features:
        if f.type in (FeatureType.DRIVEWAY, FeatureType.PATH, FeatureType.PARKING):
            _draw_site_feature(draw, t, f)

    # Building shell and rooms.
    # We no longer fill a single global building rect. The rooms themselves define the footprint.
        
    for f in plan.site_features:
        if f.type == FeatureType.CORRIDOR:
            _draw_site_feature(draw, t, f)
            
    all_rooms = plan.rooms + plan.annex_rooms
    for room in all_rooms:
        _draw_room_fill(draw, t, room)
    for room in all_rooms:
        for item in room.furniture:
            _draw_furniture(draw, t, item)

    # Walls, then openings cut into them.
    # Interior walls only need to be drawn for rooms.
    width = max(2, int(plan.wall_thickness * t.scale * 0.7))
    for room in all_rooms:
        draw.rectangle(t.box(room.bounds), outline=WALL_THIN, width=width)
        
    _draw_exterior_walls(draw, t, plan)
    for room in all_rooms:
        for o in room.openings:
            if o.type == OpeningType.WINDOW:
                _draw_window(draw, t, plan, o)
        for o in room.openings:
            if o.type == OpeningType.DOOR:
                _draw_door(draw, t, plan, o)

    # Labels and annotations.
    for room in all_rooms:
        _draw_room_label(draw, t, room)
    _draw_dimensions(draw, t, plan)
    _draw_north(draw)
    _draw_chrome(draw, t, plan)

    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return buffered.getvalue()


def render_png(plan: FloorPlan) -> str:
    """Render a FloorPlan to a base64 PNG data URI."""
    img_str = base64.b64encode(render_png_bytes(plan)).decode("utf-8")
    return f"data:image/png;base64,{img_str}"
