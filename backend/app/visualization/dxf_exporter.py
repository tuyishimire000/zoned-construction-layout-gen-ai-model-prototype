"""DXF exporter: a second consumer of the FloorPlan model.

This is a deliberately minimal CAD export — proof that the geometry model is
format-agnostic. It walks the same `FloorPlan` (in meters) that the PNG renderer
draws, and emits real vector geometry via ezdxf. No pixels involved.

ezdxf is imported lazily so the rest of the app keeps running even if the
dependency isn't installed yet.

DXF uses a bottom-left origin with Y pointing *up*; the model uses a top-left
origin with Y pointing *down* (screen convention). We flip Y on the way out so
the exported drawing is the right way up in CAD.
"""

from .model import FloorPlan, Rect, Opening, OpeningType


def _flip_y(plan: FloorPlan, y: float) -> float:
    """Convert model Y (top-left, down) to DXF Y (bottom-left, up)."""
    return plan.plot.height - y


def _add_rect(msp, plan: FloorPlan, r: Rect, layer: str):
    y0 = _flip_y(plan, r.bottom)
    y1 = _flip_y(plan, r.y)
    points = [(r.x, y0), (r.right, y0), (r.right, y1), (r.x, y1)]
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def _add_opening(msp, plan: FloorPlan, o: Opening):
    layer = "WINDOWS" if o.type == OpeningType.WINDOW else "DOORS"
    y = _flip_y(plan, o.y)
    msp.add_line((o.x, y), (o.x + o.length, y), dxfattribs={"layer": layer})


def export_dxf(plan: FloorPlan, output_path: str) -> str:
    """Write the FloorPlan to a .dxf file (in meters) and return the path."""
    import ezdxf  # lazy: keeps ezdxf optional until CAD export is used

    doc = ezdxf.new(dxfversion="R2010")
    doc.units = ezdxf.units.M  # drawing units are meters
    msp = doc.modelspace()

    for name in ("PLOT", "BUILDING", "ROOMS", "DOORS", "WINDOWS"):
        if name not in doc.layers:
            doc.layers.add(name)

    _add_rect(msp, plan, plan.plot, "PLOT")
    _add_rect(msp, plan, plan.building, "BUILDING")

    for room in plan.rooms:
        _add_rect(msp, plan, room.bounds, "ROOMS")
        for opening in room.openings:
            _add_opening(msp, plan, opening)

    doc.saveas(output_path)
    return output_path
