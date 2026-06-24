from PIL import Image, ImageDraw, ImageFont

def create_detailed_site_plan(output_path="detailed_site_plan.png"):
    # 1. Canvas Setup
    width, height = 2400, 1800
    bg_color = (245, 247, 248)       # Light warm gray background
    line_dark = (40, 50, 60)          # Thick exterior/lot lines
    line_thin = (80, 95, 110)         # Interior wall lines
    door_color = (0, 100, 180)        # Distinct blue for doors/swings
    concrete_color = (220, 225, 230)  # Driveway
    building_color = (255, 255, 255)  # White background inside house for clarity
    text_color = (50, 60, 70)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    try:
        font_body = ImageFont.truetype("arial.ttf", 24)
        font_room = ImageFont.truetype("arial.ttf", 26)
    except IOError:
        font_body = ImageFont.load_default()
        font_room = ImageFont.load_default()

    # 2. Draw Property Boundaries & Driveway (From previous script)
    lot = [(300, 300), (2100, 300), (2100, 1400), (300, 1400)]
    draw.polygon(lot, fill=None, outline=line_dark, width=6)
    draw.rectangle([650, 950, 900, 1400], fill=concrete_color, outline=line_dark, width=3)

    # 3. Primary Building Outer Shell
    # House bounds: X from 900 to 1700 (Width 800), Y from 550 to 1150 (Height 600)
    hx0, hy0, hx1, hy1 = 900, 550, 1700, 1150
    draw.rectangle([hx0, hy0, hx1, hy1], fill=building_color, outline=line_dark, width=6)

    # 4. Interior Wall Layout (Thinner lines)
    # Living Room / Bedroom Divider (Vertical wall at X = 1350)
    draw.line([(1350, hy0), (1350, hy1)], fill=line_thin, width=4)
    # Bedroom / Bathroom Divider (Horizontal wall at Y = 850, inside the right wing)
    draw.line([(1350, 850), (hx1, 850)], fill=line_thin, width=4)

    # 5. Erase Wall Sections to Create Rough Door Openings
    # Front Door Opening (Bottom wall of Living room near driveway)
    draw.line([(960, hy1), (1040, hy1)], fill=building_color, width=8)
    # Bedroom Door Opening (In the vertical divider wall)
    draw.line([(1350, 600), (1350, 680)], fill=building_color, width=8)

    # 6. Draw Architectural Doors (Door Leaf + Swing Arc)

    # --- FRONT ENTRY DOOR (90-Degree Swing Inward Left) ---
    # Door Leaf (The actual wood panel swung open 90 degrees inside)
    draw.line([(960, hy1), (960, hy1 - 80)], fill=door_color, width=3)
    # Door Swing Arc (Bounding box for a full circle, drawn as 90-degree slice)
    # Bounding box centers on the hinge point (960, hy1) with radius 80
    draw.arc([960 - 80, hy1 - 80, 960 + 80, hy1 + 80], start=270, end=360, fill=door_color, width=2)

    # --- BEDROOM DOOR (90-Degree Swing Inward to Bedroom) ---
    # Door Leaf hinge at (1350, 680), swings open into the bedroom right side
    draw.line([(1350, 680), (1350 + 80, 680)], fill=door_color, width=3)
    # Swing Arc curve
    draw.arc([1350 - 80, 680 - 80, 1350 + 80, 680 + 80], start=0, end=90, fill=door_color, width=2)

    # 7. Add Interior Room Labels
    draw.text((1125, 850), "LIVING ROOM\n(18' x 24')", fill=text_color, font=font_room, align="center")
    draw.text((1525, 700), "BEDROOM\n(14' x 12')", fill=text_color, font=font_room, align="center")
    draw.text((1525, 1000), "BATH", fill=text_color, font=font_room, align="center")

    # 8. Clean up Exterior Labels
    draw.text((710, 1150), "DRIVEWAY", fill=text_color, font=font_body)
    draw.text((1200, 500), "PROPOSED RESIDENCE FOOTPRINT", fill=text_color, font=font_body)

    # Save Output Layout
    img.save(output_path)
    print(f"Detailed floor layout plan saved to: {output_path}")
