"""Public entry point for site-plan generation.

The work is split into two stages:

1. `build_floorplan` (layout_engine) computes the geometry as a `FloorPlan`
   model in real-world meters.
2. `render_png` (png_renderer) draws that model to a PNG.

This separation keeps the geometry independent of the output format, so the
same model can feed future DXF/JSON exporters without touching the layout logic.
"""

from .layout_engine import build_floorplan
from .png_renderer import render_png


def generate_floorplan(params: dict, compliance: dict) -> str:
    """Build the layout model and render it to a base64 PNG data URI."""
    plan = build_floorplan(params, compliance)
    return render_png(plan)
