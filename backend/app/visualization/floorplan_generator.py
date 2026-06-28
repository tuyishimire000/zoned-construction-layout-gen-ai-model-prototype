"""Public entry point for site-plan generation.

The work is split into two stages:

1. `build_floorplan` (layout_engine) computes the geometry as a `FloorPlan`
   model in real-world meters.
2. `render_png` (png_renderer) draws that model to a PNG.

This separation keeps the geometry independent of the output format, so the
same model can feed future DXF/JSON exporters without touching the layout logic.
"""

from .layout_engine import build_floorplan
from .dxf_renderer import render_dxf, export_to_svg
from typing import Tuple

def generate_floorplan(params: dict, compliance: dict, export_format: str = "png") -> Tuple[str, str, float]:
    """Build the layout model and render it to the specified format and DXF. 
    Returns (image_data, dxf_data, score).
    """
    plan = build_floorplan(params, compliance)
    
    doc, dxf_data = render_dxf(plan)
    img_data = export_to_svg(doc)
    
    return img_data, dxf_data, plan.score
