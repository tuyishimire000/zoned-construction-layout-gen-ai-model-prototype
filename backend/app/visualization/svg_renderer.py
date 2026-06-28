import math
from typing import List

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
MARGIN = 130

# Palette
BG = "#F5F7F8"
GRASS_FILL = "#ECF4E6"
GRASS_LINE = "#81C784"
WALL_DARK = "#28323C"
WALL_THIN = "#505F6E"
DOOR_COLOR = "#0064B4"
WINDOW_GLASS = "#78BEE6"
WINDOW_FRAME = "#285A82"
CONCRETE = "#DCDFE6"
BUILDING_FILL = "#FFFFFF"
TEXT_COLOR = "#323C46"
DIM_COLOR = "#5A646E"

ROOM_COLORS = {
    "bedrooms": "#C8E6C9",
    "bathrooms": "#BBDEFB",
    "kitchens": "#FFE082",
    "living_rooms": "#F8BBD0",
    "offices": "#E1BEE7",
}

class SvgTransform:
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

    def w(self, mw: float) -> float:
        return mw * self.scale

    def h(self, mh: float) -> float:
        return mh * self.scale

class SvgBuilder:
    def __init__(self):
        self.elements = []
        
    def add(self, tag: str, **kwargs):
        attrs = ' '.join(f'{k.replace("_", "-")}="{v}"' for k, v in kwargs.items() if v is not None)
        self.elements.append(f'<{tag} {attrs} />')
        
    def text(self, x, y, content, fill, font_size, anchor="middle", font_weight="normal"):
        self.elements.append(f'<text x="{x}" y="{y}" fill="{fill}" font-size="{font_size}" font-family="sans-serif" font-weight="{font_weight}" text-anchor="{anchor}" dominant-baseline="central">{content}</text>')

    def rect(self, x, y, width, height, fill="none", stroke="none", stroke_width=0, rx=0, stroke_dasharray=None):
        self.add("rect", x=x, y=y, width=width, height=height, fill=fill, stroke=stroke, stroke_width=stroke_width, rx=rx, stroke_dasharray=stroke_dasharray)

    def line(self, x1, y1, x2, y2, stroke="black", stroke_width=1):
        self.add("line", x1=x1, y1=y1, x2=x2, y2=y2, stroke=stroke, stroke_width=stroke_width)

    def polyline(self, points, stroke="black", stroke_width=1, fill="none"):
        pts = " ".join(f"{x},{y}" for x, y in points)
        self.add("polyline", points=pts, stroke=stroke, stroke_width=stroke_width, fill=fill)

    def circle(self, cx, cy, r, fill="none", stroke="none", stroke_width=0):
        self.add("circle", cx=cx, cy=cy, r=r, fill=fill, stroke=stroke, stroke_width=stroke_width)

    def path(self, d, fill="none", stroke="none", stroke_width=0, stroke_dasharray=None):
        self.add("path", d=d, fill=fill, stroke=stroke, stroke_width=stroke_width, stroke_dasharray=stroke_dasharray)

    def render(self):
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS_W} {CANVAS_H}">\n  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="{BG}" />\n  ' + '\n  '.join(self.elements) + '\n</svg>'

def _draw_site_feature(svg: SvgBuilder, t: SvgTransform, f: SiteFeature):
    if f.points:
        scaled_pts = [(t.x(px), t.y(py)) for px, py in f.points]
        if f.type == FeatureType.PATH:
            svg.polyline(scaled_pts, stroke="#E0E0E0", stroke_width=t.w(1.5), fill="none")
        elif f.type == FeatureType.DRIVEWAY:
            svg.polyline(scaled_pts, stroke="#BDBDBD", stroke_width=t.w(3.0), fill="none")
        return

    x = t.x(f.bounds.x)
    y = t.y(f.bounds.y)
    w = t.w(f.bounds.width)
    h = t.h(f.bounds.height)
    
    if f.type == FeatureType.GRASS:
        svg.rect(x, y, w, h, fill=GRASS_FILL, stroke=GRASS_LINE, stroke_width=4)
    elif f.type == FeatureType.TREE:
        svg.circle(x + w/2, y + h/2, min(w, h)/2, fill="#81C784", stroke="#388E3C", stroke_width=2)
        svg.circle(x + w/2, y + h/2, min(w, h)/4, fill="#AED581", stroke="#388E3C", stroke_width=1)
    elif f.type in (FeatureType.DRIVEWAY, FeatureType.PATH):
        svg.rect(x, y, w, h, fill=CONCRETE, stroke=WALL_DARK, stroke_width=3)
        if f.label:
            svg.text(t.x(f.bounds.cx), t.y(f.bounds.bottom) - 16, f.label, TEXT_COLOR, 14)
    elif f.type == FeatureType.CORRIDOR:
        svg.rect(x, y, w, h, fill="#CFD8DC", stroke="#90A4AE", stroke_width=1)
        if f.label:
            svg.text(t.x(f.bounds.cx), t.y(f.bounds.cy), f.label, "#455A64", 14)
    elif f.type == FeatureType.PARKING:
        svg.rect(x, y, w, h, fill="#9E9E9E", stroke="#616161", stroke_width=2)
        if f.label:
            svg.text(x + w/2, y + h/2, f.label, "#FFFFFF", 16, font_weight="bold")

def _draw_furniture(svg: SvgBuilder, t: SvgTransform, item: Furniture):
    x = t.x(item.bounds.x)
    y = t.y(item.bounds.y)
    w = t.w(item.bounds.width)
    h = t.h(item.bounds.height)
    
    if item.type == "bed":
        svg.rect(x, y, w, h, fill="#E0F7FA", stroke="#4DD0E1", stroke_width=2, rx=4)
        svg.rect(x + w * 0.1, y + h * 0.1, w * 0.8, h * 0.25, fill="#FFFFFF", stroke="#4DD0E1", stroke_width=1, rx=2)
    elif item.type == "wardrobe":
        svg.rect(x, y, w, h, fill="#A1887F", stroke="#7B5E54", stroke_width=2)
    elif item.type == "bathtub":
        svg.rect(x, y, w, h, fill="#E3F2FD", stroke="#90CAF9", stroke_width=2, rx=8)
    elif item.type == "toilet":
        svg.rect(x + w*0.2, y, w*0.6, h*0.3, fill="#FFFFFF", stroke="#B0BEC5", stroke_width=2)
        svg.circle(x + w/2, y + h*0.65, w*0.35, fill="#FFFFFF", stroke="#B0BEC5", stroke_width=2)
    elif item.type == "sink":
        svg.rect(x, y, w, h, fill="#F5F5F5", stroke="#E0E0E0", stroke_width=2, rx=2)
        svg.circle(x + w/2, y + h/2, min(w, h)*0.35, fill="#FFFFFF", stroke="#B0BEC5", stroke_width=1)
    elif item.type == "kitchen_counter":
        svg.rect(x, y, w, h, fill="#BDBDBD", stroke="#757575", stroke_width=2)
    elif item.type == "kitchen_island":
        svg.rect(x, y, w, h, fill="#EEEEEE", stroke="#BDBDBD", stroke_width=2)
    elif item.type == "sofa":
        svg.rect(x, y + h*0.3, w, h*0.7, fill="#90CAF9", stroke="#5C9CD6", rx=4)
        svg.rect(x + w*0.1, y, w*0.8, h*0.5, fill="#90CAF9", stroke="#5C9CD6", rx=4)
    elif item.type == "tv_stand":
        svg.rect(x, y, w, h, fill="#424242", stroke="#212121", stroke_width=2)
    elif item.type == "desk":
        svg.rect(x, y, w, h*0.55, fill="#A1887F", stroke="#7B5E54")
        r = min(w, h) * 0.3
        svg.circle(x + w/2, y + h - r, r, fill="#607D8B")

def _draw_room_fill(svg: SvgBuilder, t: SvgTransform, room: Room):
    x = t.x(room.bounds.x)
    y = t.y(room.bounds.y)
    w = t.w(room.bounds.width)
    h = t.h(room.bounds.height)
    fill = ROOM_COLORS.get(room.type, "#EEEEEE")
    svg.rect(x, y, w, h, fill=fill)

def _draw_room_label(svg: SvgBuilder, t: SvgTransform, room: Room):
    cx = t.x(room.bounds.cx)
    cy = t.y(room.bounds.cy)
    svg.text(cx, cy - 9, room.label, TEXT_COLOR, 16, font_weight="bold")
    svg.text(cx, cy + 12, f"{room.bounds.width:.1f} x {room.bounds.height:.1f} m", DIM_COLOR, 14)

def _draw_exterior_walls(svg: SvgBuilder, t: SvgTransform, plan: FloorPlan):
    def is_exposed(cx, cy, all_rooms):
        for r in all_rooms:
            if r.bounds.x < cx < r.bounds.right and r.bounds.y < cy < r.bounds.bottom:
                return False
        return True

    all_rooms = plan.rooms + plan.annex_rooms
    for room in all_rooms:
        b = room.bounds
        if is_exposed(b.cx, b.y - 0.1, all_rooms):
            svg.line(t.x(b.x), t.y(b.y), t.x(b.right), t.y(b.y), stroke=WALL_DARK, stroke_width=4)
        if is_exposed(b.cx, b.bottom + 0.1, all_rooms):
            svg.line(t.x(b.x), t.y(b.bottom), t.x(b.right), t.y(b.bottom), stroke=WALL_DARK, stroke_width=4)
        if is_exposed(b.x - 0.1, b.cy, all_rooms):
            svg.line(t.x(b.x), t.y(b.y), t.x(b.x), t.y(b.bottom), stroke=WALL_DARK, stroke_width=4)
        if is_exposed(b.right + 0.1, b.cy, all_rooms):
            svg.line(t.x(b.right), t.y(b.y), t.x(b.right), t.y(b.bottom), stroke=WALL_DARK, stroke_width=4)

def _draw_interior_walls(svg: SvgBuilder, t: SvgTransform, plan: FloorPlan):
    width = max(2, int(plan.wall_thickness * t.scale * 0.7))
    for room in plan.rooms + plan.annex_rooms:
        x = t.x(room.bounds.x)
        y = t.y(room.bounds.y)
        w = t.w(room.bounds.width)
        h = t.h(room.bounds.height)
        svg.rect(x, y, w, h, fill="none", stroke=WALL_THIN, stroke_width=width)

def _draw_openings(svg: SvgBuilder, t: SvgTransform, plan: FloorPlan):
    for room in plan.rooms + plan.annex_rooms:
        for o in room.openings:
            x = t.x(o.x)
            y = t.y(o.y)
            length = t.w(o.length) # Assumes uniform scale
            
            if o.orientation == Orientation.HORIZONTAL:
                svg.line(x, y, x + length, y, stroke=BUILDING_FILL, stroke_width=6)
                if o.type == OpeningType.DOOR:
                    sign = -1 if o.swing == "up" else 1
                    # Leaf
                    svg.line(x, y, x, y + sign * length, stroke=DOOR_COLOR, stroke_width=2)
                    # Arc
                    sweep = 0 if o.swing == "up" else 1
                    svg.path(f"M {x + length} {y} A {length} {length} 0 0 {sweep} {x} {y + sign * length}", stroke=DOOR_COLOR, stroke_width=1, stroke_dasharray="4,4")
                elif o.type == OpeningType.WINDOW:
                    svg.line(x, y, x + length, y, stroke=WINDOW_GLASS, stroke_width=3)
                    svg.line(x, y, x + length, y, stroke=WINDOW_FRAME, stroke_width=1)
            else:
                svg.line(x, y, x, y + length, stroke=BUILDING_FILL, stroke_width=6)
                if o.type == OpeningType.DOOR:
                    sign = -1 if o.swing == "left" else 1
                    # Leaf
                    svg.line(x, y, x + sign * length, y, stroke=DOOR_COLOR, stroke_width=2)
                    # Arc
                    sweep = 1 if o.swing == "left" else 0
                    svg.path(f"M {x} {y + length} A {length} {length} 0 0 {sweep} {x + sign * length} {y}", stroke=DOOR_COLOR, stroke_width=1, stroke_dasharray="4,4")
                elif o.type == OpeningType.WINDOW:
                    svg.line(x, y, x, y + length, stroke=WINDOW_GLASS, stroke_width=3)
                    svg.line(x, y, x, y + length, stroke=WINDOW_FRAME, stroke_width=1)

def render_svg(plan: FloorPlan) -> str:
    t = SvgTransform(plan)
    svg = SvgBuilder()

    for f in plan.site_features:
        if f.type in (FeatureType.GRASS, FeatureType.TREE):
            _draw_site_feature(svg, t, f)
            
    for f in plan.site_features:
        if f.type in (FeatureType.DRIVEWAY, FeatureType.PATH, FeatureType.PARKING):
            _draw_site_feature(svg, t, f)
            
    for f in plan.site_features:
        if f.type == FeatureType.CORRIDOR:
            _draw_site_feature(svg, t, f)

    all_rooms = plan.rooms + plan.annex_rooms
    for room in all_rooms:
        _draw_room_fill(svg, t, room)

    _draw_interior_walls(svg, t, plan)
    _draw_exterior_walls(svg, t, plan)
    _draw_openings(svg, t, plan)

    for room in all_rooms:
        for f in room.furniture:
            _draw_furniture(svg, t, f)
            
    for room in all_rooms:
        _draw_room_label(svg, t, room)

    # Plot boundaries
    svg.rect(t.x(0), t.y(0), t.w(plan.plot.width), t.h(plan.plot.height), fill="none", stroke=WALL_DARK, stroke_width=4, stroke_dasharray="10,10")

    return svg.render()
