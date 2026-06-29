import base64
import io
import ezdxf
from ezdxf.enums import TextEntityAlignment
from app.visualization.model import FloorPlan, Room, SiteFeature, FeatureType, Opening, OpeningType, Furniture, Orientation

def _draw_rect_filled(msp, rect, outline_layer, fill_layer, lineweight=0, const_width=0, room=None):
    x, y, w, h = rect
    if fill_layer:
        hatch = msp.add_hatch(color=256, dxfattribs={"layer": fill_layer})
        hatch.paths.add_polyline_path([(x, y), (x+w, y), (x+w, y+h), (x, y+h), (x, y)], is_closed=True)
        
    if outline_layer:
        if room and hasattr(room, 'openings'):
            gaps_top, gaps_bottom, gaps_left, gaps_right = [], [], [], []
            for op in room.openings:
                is_horiz = op.orientation == Orientation.HORIZONTAL
                # the opening is defined by its x,y and length
                gap_len = op.length
                start_op = op.x if is_horiz else op.y
                end_op = (op.x + op.length) if is_horiz else (op.y + op.length)
                
                if is_horiz:
                    if abs(op.y - y) < 0.1: gaps_top.append((start_op, end_op))
                    elif abs(op.y - (y+h)) < 0.1: gaps_bottom.append((start_op, end_op))
                else:
                    if abs(op.x - x) < 0.1: gaps_left.append((start_op, end_op))
                    elif abs(op.x - (x+w)) < 0.1: gaps_right.append((start_op, end_op))
            
            def draw_broken_edge(start_val, end_val, gaps, is_horiz, coord):
                curr = start_val
                for gs, ge in sorted(gaps):
                    if curr < gs:
                        pts = [(curr, coord), (gs, coord)] if is_horiz else [(coord, curr), (coord, gs)]
                        msp.add_lwpolyline(pts, dxfattribs={"layer": outline_layer, "lineweight": lineweight, "const_width": const_width})
                    curr = max(curr, ge)
                if curr < end_val:
                    pts = [(curr, coord), (end_val, coord)] if is_horiz else [(coord, curr), (coord, end_val)]
                    msp.add_lwpolyline(pts, dxfattribs={"layer": outline_layer, "lineweight": lineweight, "const_width": const_width})
                    
            draw_broken_edge(x, x+w, gaps_top, True, y)
            draw_broken_edge(x, x+w, gaps_bottom, True, y+h)
            draw_broken_edge(y, y+h, gaps_left, False, x)
            draw_broken_edge(y, y+h, gaps_right, False, x+w)
        else:
            points = [(x, y), (x+w, y), (x+w, y+h), (x, y+h), (x, y)]
            attribs = {"layer": outline_layer, "lineweight": lineweight}
            if const_width > 0:
                attribs["const_width"] = const_width
            msp.add_lwpolyline(points, dxfattribs=attribs)

def _rgb(r, g, b):
    return ezdxf.colors.rgb2int((r, g, b))

def render_dxf_bytes(plan: FloorPlan) -> tuple[ezdxf.document.Drawing, bytes]:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    
    # Setup layers with professional true colors (Light CAD style)
    doc.layers.add("GRID", color=7, true_color=_rgb(224, 242, 254))      # Very pale blue grid
    doc.layers.add("PLOT_FILL", color=7, true_color=_rgb(255, 255, 255)) # White
    doc.layers.add("PLOT_OUTLINE", color=7, true_color=_rgb(0, 0, 0))    # Thick Black
    
    # Fill colors
    doc.layers.add("ROAD_FILL", color=8, true_color=_rgb(156, 163, 175)) # Gray road
    doc.layers.add("ROOM_FILL", color=7, true_color=_rgb(219, 234, 254)) # Pale blue (default room)
    doc.layers.add("ROOM_GREEN", color=7, true_color=_rgb(187, 247, 208))# Pale green (garden/balcony)
    
    # Structural Outlines
    doc.layers.add("WALLS", color=7, true_color=_rgb(0, 0, 0))           # Thick black
    doc.layers.add("WIPEOUT", color=7, true_color=_rgb(255, 255, 255))   # Solid White mask
    doc.layers.add("DOORS", color=7, true_color=_rgb(0, 0, 0))           # Black
    doc.layers.add("WINDOWS", color=5, true_color=_rgb(59, 130, 246))    # Blue windows
    
    doc.layers.add("FURNITURE", color=7, true_color=_rgb(107, 114, 128)) # Gray furniture
    doc.layers.add("SITE", color=9, true_color=_rgb(167, 139, 250))      # Soft purple
    doc.layers.add("TEXT", color=7, true_color=_rgb(0, 0, 0))            # Black text
    doc.layers.add("DIMENSIONS", color=5, true_color=_rgb(59, 130, 246)) # Blue dims
    
    # 0. Draw Grid inside Plot only
    grid_size = 1.0
    gx_min, gy_min = plan.plot.x, plan.plot.y
    gx_max, gy_max = plan.plot.x + plan.plot.width, plan.plot.y + plan.plot.height
    x_val = gx_min
    while x_val <= gx_max:
        msp.add_line((x_val, gy_min), (x_val, gy_max), dxfattribs={"layer": "GRID"})
        x_val += grid_size
    y_val = gy_min
    while y_val <= gy_max:
        msp.add_line((gx_min, y_val), (gx_max, y_val), dxfattribs={"layer": "GRID"})
        y_val += grid_size

    # Draw Site Features (Roads, Zoning, Parking)
    for sf in plan.site_features:
        if sf.type == FeatureType.CORRIDOR or "road" in str(sf.label).lower():
            # Draw Road
            rx, ry, rw, rh = sf.bounds.x, sf.bounds.y, sf.bounds.width, sf.bounds.height
            if rw > rh:
                _draw_rect_filled(msp, (rx-10, ry, rw+20, rh), outline_layer=None, fill_layer="ROAD_FILL")
                msp.add_text(sf.label or "EXISTING ROAD", dxfattribs={"layer": "SITE_TEXT", "height": 1.5}).set_placement((rx + rw/2, ry + rh/2), align=TextEntityAlignment.MIDDLE_CENTER)
            else:
                text = msp.add_text(sf.label or "EXISTING ROAD", dxfattribs={"layer": "SITE_TEXT", "height": 1.5}).set_placement((rx + rw/2, ry + rh/2), align=TextEntityAlignment.MIDDLE_CENTER)
                text.dxf.rotation = 90
        else:
            # Grass, Parking, etc
            _draw_rect_filled(msp, (sf.bounds.x, sf.bounds.y, sf.bounds.width, sf.bounds.height), outline_layer=None, fill_layer="SITE_GREEN")
            if sf.label:
                mtext = msp.add_mtext(sf.label.upper(), dxfattribs={"layer": "SITE_TEXT", "char_height": 0.18, "color": 7})
                mtext.set_location((sf.bounds.cx, sf.bounds.cy), attachment_point=5)

    # 1. Plot
    _draw_rect_filled(msp, (plan.plot.x, plan.plot.y, plan.plot.width, plan.plot.height), outline_layer="PLOT_OUTLINE", fill_layer="PLOT_FILL", lineweight=35) # 0.35mm thick
    
    # 2. Building (Removed global bounding box wall to allow organic perimeters and disconnected annexes)

    # 4. Rooms
    for r in plan.rooms:
        if r.type.lower() in ['balcony', 'garden', 'yard', 'terrace', 'parking']:
            fill_layer = "ROOM_GREEN"
        else:
            fill_layer = "ROOM_FILL"
            
        _draw_rect_filled(msp, (r.bounds.x, r.bounds.y, r.bounds.width, r.bounds.height), outline_layer="WALLS", fill_layer=fill_layer, const_width=plan.wall_thickness, room=r)
        
        # Room text
        label = r.label.upper() if getattr(r, "label", None) else r.type.replace('_', ' ').upper()
        text_content = f"{label}\n{r.bounds.width:.1f}m x {r.bounds.height:.1f}m\n{r.bounds.area:.1f}m²"
        mtext = msp.add_mtext(text_content, dxfattribs={"layer": "TEXT", "char_height": 0.18, "color": 7})
        mtext.set_location((r.bounds.cx, r.bounds.cy), attachment_point=5) # 5 = Middle Center
        
        # Furniture rendering removed per user request
        # for f in r.furniture:
        #     fx, fy, fw, fh = f.bounds.x, f.bounds.y, f.bounds.width, f.bounds.height
        #     _draw_rect_filled(msp, (fx, fy, fw, fh), outline_layer="FURNITURE", fill_layer=None, lineweight=13)
        #     # Add a cross for beds to make it look like a bed block
        #     if "bed" in f.type.lower():
        #         msp.add_line((fx, fy), (fx+fw, fy+fh), dxfattribs={"layer": "FURNITURE"})
        #         msp.add_line((fx, fy+fh), (fx+fw, fy), dxfattribs={"layer": "FURNITURE"})
        #     elif "car" in f.type.lower():
        #         # Car generic block (chamfered rect)
        #         _draw_rect_filled(msp, (fx+0.2, fy+0.2, fw-0.4, fh-0.4), outline_layer="FURNITURE", fill_layer=None)
        
        # Openings
        for op in r.openings:
            is_horiz = op.orientation == Orientation.HORIZONTAL
            layer = "DOORS" if op.type == OpeningType.DOOR else "WINDOWS"
            
            x1, y1 = op.x, op.y
            x2 = op.x + (op.length if is_horiz else 0)
            y2 = op.y + (0 if is_horiz else op.length)
            
            # Draw Wipeout removed because wall lines are dynamically broken
            wt = plan.wall_thickness
            
            if op.type == OpeningType.PASSAGE:
                # Draw jambs (wall end-caps) for cased openings
                if is_horiz:
                    msp.add_line((x1, y1 - wt/2), (x1, y1 + wt/2), dxfattribs={"layer": layer})
                    msp.add_line((x2, y2 - wt/2), (x2, y2 + wt/2), dxfattribs={"layer": layer})
                else:
                    msp.add_line((x1 - wt/2, y1), (x1 + wt/2, y1), dxfattribs={"layer": layer})
                    msp.add_line((x2 - wt/2, y2), (x2 + wt/2, y2), dxfattribs={"layer": layer})
                # No door leaf or arc
                continue
                
            elif op.type == OpeningType.DOOR:
                # Door jambs
                if is_horiz:
                    msp.add_line((x1, y1 - wt/2), (x1, y1 + wt/2), dxfattribs={"layer": layer})
                    msp.add_line((x2, y2 - wt/2), (x2, y2 + wt/2), dxfattribs={"layer": layer})
                else:
                    msp.add_line((x1 - wt/2, y1), (x1 + wt/2, y1), dxfattribs={"layer": layer})
                    msp.add_line((x2 - wt/2, y2), (x2 + wt/2, y2), dxfattribs={"layer": layer})
                
                # Door panel and realistic arc
                if op.swing:
                    is_pivot = getattr(op, "style", None) == "pivot"
                    offset = 0.2 if is_pivot else 0.0
                    leaf_len = op.length - offset
                    
                    if is_horiz:
                        if op.hinge_at_start:
                            cx = x1 + offset
                            cy = y1
                            leaf_y = cy - leaf_len if op.swing == "up" else cy + leaf_len
                            if is_pivot: msp.add_line((x1, y1), (cx, cy), dxfattribs={"layer": layer, "lineweight": 15})
                            msp.add_line((cx, cy), (cx, leaf_y), dxfattribs={"layer": layer, "lineweight": 15})
                            if op.swing == "up":
                                sa, ea = 270, 360
                            else:
                                sa, ea = 0, 90
                        else:
                            cx = x2 - offset
                            cy = y2
                            leaf_y = cy - leaf_len if op.swing == "up" else cy + leaf_len
                            if is_pivot: msp.add_line((x2, y2), (cx, cy), dxfattribs={"layer": layer, "lineweight": 15})
                            msp.add_line((cx, cy), (cx, leaf_y), dxfattribs={"layer": layer, "lineweight": 15})
                            if op.swing == "up":
                                sa, ea = 180, 270
                            else:
                                sa, ea = 90, 180
                                
                        msp.add_arc((cx, cy), radius=leaf_len, start_angle=sa, end_angle=ea, dxfattribs={"layer": layer, "lineweight": 0})
                    else:
                        if op.hinge_at_start:
                            cx = x1
                            cy = y1 + offset
                            leaf_x = cx - leaf_len if op.swing == "left" else cx + leaf_len
                            if is_pivot: msp.add_line((x1, y1), (cx, cy), dxfattribs={"layer": layer, "lineweight": 15})
                            msp.add_line((cx, cy), (leaf_x, cy), dxfattribs={"layer": layer, "lineweight": 15})
                            if op.swing == "left":
                                sa, ea = 90, 180
                            else:
                                sa, ea = 0, 90
                        else:
                            cx = x2
                            cy = y2 - offset
                            leaf_x = cx - leaf_len if op.swing == "left" else cx + leaf_len
                            if is_pivot: msp.add_line((x2, y2), (cx, cy), dxfattribs={"layer": layer, "lineweight": 15})
                            msp.add_line((cx, cy), (leaf_x, cy), dxfattribs={"layer": layer, "lineweight": 15})
                            if op.swing == "left":
                                sa, ea = 180, 270
                            else:
                                sa, ea = 270, 360
                                
                        msp.add_arc((cx, cy), radius=leaf_len, start_angle=sa, end_angle=ea, dxfattribs={"layer": layer, "lineweight": 0})
            elif op.type == OpeningType.WINDOW:
                # Window
                frame_w = 0.04
                if getattr(op, "style", "sliding") == "sliding":
                    if is_horiz:
                        msp.add_line((x1, y1 - wt/2), (x1, y1 + wt/2), dxfattribs={"layer": layer})
                        msp.add_line((x2, y2 - wt/2), (x2, y2 + wt/2), dxfattribs={"layer": layer})
                        
                        # Sill lines (window depth edge)
                        msp.add_line((x1, y1 - wt/2), (x2, y2 - wt/2), dxfattribs={"layer": "OPENINGS", "lineweight": 0, "color": 8})
                        msp.add_line((x1, y1 + wt/2), (x2, y2 + wt/2), dxfattribs={"layer": "OPENINGS", "lineweight": 0, "color": 8})
                        
                        # Frame borders
                        msp.add_line((x1+frame_w, y1 - wt/2 + frame_w), (x1+frame_w, y1 + wt/2 - frame_w), dxfattribs={"layer": layer})
                        msp.add_line((x2-frame_w, y1 - wt/2 + frame_w), (x2-frame_w, y1 + wt/2 - frame_w), dxfattribs={"layer": layer})
                        
                        # two overlapping sliding panes
                        mid_x = (x1 + x2) / 2
                        msp.add_line((x1+frame_w, y1 - 0.02), (mid_x + 0.02, y1 - 0.02), dxfattribs={"layer": layer, "lineweight": 15})
                        msp.add_line((mid_x - 0.02, y1 + 0.02), (x2-frame_w, y1 + 0.02), dxfattribs={"layer": layer, "lineweight": 15})
                    else:
                        msp.add_line((x1 - wt/2, y1), (x1 + wt/2, y1), dxfattribs={"layer": layer})
                        msp.add_line((x2 - wt/2, y2), (x2 + wt/2, y2), dxfattribs={"layer": layer})
                        
                        # Sill lines
                        msp.add_line((x1 - wt/2, y1), (x1 - wt/2, y2), dxfattribs={"layer": "OPENINGS", "lineweight": 0, "color": 8})
                        msp.add_line((x1 + wt/2, y1), (x1 + wt/2, y2), dxfattribs={"layer": "OPENINGS", "lineweight": 0, "color": 8})
                        
                        # Frame borders
                        msp.add_line((x1 - wt/2 + frame_w, y1+frame_w), (x1 + wt/2 - frame_w, y1+frame_w), dxfattribs={"layer": layer})
                        msp.add_line((x1 - wt/2 + frame_w, y2-frame_w), (x1 + wt/2 - frame_w, y2-frame_w), dxfattribs={"layer": layer})
                        
                        # two overlapping sliding panes
                        mid_y = (y1 + y2) / 2
                        msp.add_line((x1 - 0.02, y1+frame_w), (x1 - 0.02, mid_y + 0.02), dxfattribs={"layer": layer, "lineweight": 15})
                        msp.add_line((x1 + 0.02, mid_y - 0.02), (x1 + 0.02, y2-frame_w), dxfattribs={"layer": layer, "lineweight": 15})
                else:
                    # awning or standard
                    if is_horiz:
                        msp.add_line((x1, y1 - wt/2), (x1, y1 + wt/2), dxfattribs={"layer": layer})
                        msp.add_line((x2, y2 - wt/2), (x2, y2 + wt/2), dxfattribs={"layer": layer})
                        msp.add_line((x1, y1), (x2, y1), dxfattribs={"layer": layer, "lineweight": 15})
                    else:
                        msp.add_line((x1 - wt/2, y1), (x1 + wt/2, y1), dxfattribs={"layer": layer})
                        msp.add_line((x2 - wt/2, y2), (x2 + wt/2, y2), dxfattribs={"layer": layer})
                        msp.add_line((x1, y1), (x1, y2), dxfattribs={"layer": layer, "lineweight": 15})
    # Save to bytes
    buffer = io.StringIO()
    doc.write(buffer)
    return doc, buffer.getvalue().encode('utf-8')

def render_dxf(plan: FloorPlan) -> tuple[ezdxf.document.Drawing, str]:
    """Returns (ezdxf_doc, base64_encoded_dxf)."""
    doc, dxf_bytes = render_dxf_bytes(plan)
    return doc, "data:application/dxf;base64," + base64.b64encode(dxf_bytes).decode("ascii")

def export_to_svg(doc: ezdxf.document.Drawing) -> str:
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.svg import SVGBackend
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy, LinePolicy
    from ezdxf.addons.drawing.layout import Page, Margins
    from ezdxf.fonts.fonts import font_manager
    import os
    import pathlib
    
    font_folder = os.path.dirname(__file__)
    font_path = os.path.join(font_folder, "Roboto-Regular.ttf")
    if os.path.exists(font_path):
        font_manager.scan_folder(pathlib.Path(font_folder))
        font_manager._fallback_font_name = "roboto-regular.ttf"
        
    msp = doc.modelspace()
    
    # Delete massive background elements so the SVG tightly crops around the building geometry
    to_delete = []
    for e in msp:
        if e.dxf.layer in ("GRID", "PLOT_OUTLINE", "PLOT_FILL", "ROAD_FILL", "SITE_GREEN", "SITE_TEXT"):
            to_delete.append(e)
    for e in to_delete:
        msp.delete_entity(e)
        
    context = RenderContext(doc)
    backend = SVGBackend()
    
    config = Configuration(
        background_policy=BackgroundPolicy.CUSTOM,
        custom_bg_color="#FFFFFF",  # White paper background
        color_policy=ColorPolicy.COLOR,
        line_policy=LinePolicy.ACCURATE,
        lineweight_scaling=0.1,     # Enable thick lines
        min_lineweight=0.05         # Default thin lines
    )
    frontend = Frontend(context, backend, config=config)
    frontend.draw_layout(msp)
    
    # Export with small margin so it automatically fits
    page = Page(width=0, height=0, margins=Margins(2, 2, 2, 2))
    svg_string = backend.get_string(page)
    
    # Return as base64 data URI
    return "data:image/svg+xml;base64," + base64.b64encode(svg_string.encode('utf-8')).decode('ascii')
