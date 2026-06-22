import io
import base64
import math
from PIL import Image, ImageDraw

ROOM_COLORS = {
    "bedrooms": "#C8E6C9", # Green
    "bathrooms": "#BBDEFB", # Blue
    "kitchens": "#FFE082", # Yellow
    "living_rooms": "#F8BBD0", # Pink
    "offices": "#E1BEE7" # Purple
}

STANDARD_ROOM_SIZES = {
    "bedrooms": 15,
    "bathrooms": 5,
    "kitchens": 10,
    "living_rooms": 20,
    "offices": 12
}

def generate_floorplan(params: dict, compliance: dict) -> str:
    img_width = 800
    img_height = 600
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    plot_size = params.get('plot_size') or 500
    floors = params.get('floors') or 1
    parking = params.get('parking_spaces') or 0
    usage = params.get('usage', 'residential')
    rooms = params.get('rooms', {})
    
    metrics = compliance.get('metrics', {})
    coverage_limit = metrics.get('site_coverage_limit', 0.6)
    
    margin = 50
    plot_w = img_width - 2 * margin
    plot_h = img_height - 2 * margin
    
    # Pixel to meters conversion (assuming square plot)
    plot_side_m = math.sqrt(plot_size)
    px_to_m = plot_side_m / plot_w
    
    # Draw Landscaping: Base Grass
    draw.rectangle([margin, margin, img_width-margin, img_height-margin], fill='#F1F8E9', outline='#81C784', width=3)
    
    # Trees / Bushes
    tree_positions = [
        (margin + 20, margin + 20),
        (img_width - margin - 50, margin + 20),
        (img_width - margin - 50, img_height - margin - 50)
    ]
    for tx, ty in tree_positions:
        draw.ellipse([tx, ty, tx+30, ty+30], fill='#81C784', outline='#388E3C')
        draw.ellipse([tx+10, ty+5, tx+40, ty+35], fill='#AED581', outline='#388E3C')
    
    # Building footprint
    scale_factor = math.sqrt(coverage_limit) * 0.8
    bldg_w = plot_w * scale_factor
    bldg_h = plot_h * scale_factor
    bldg_x0 = margin + (plot_w - bldg_w) / 2
    bldg_y0 = margin + (plot_h - bldg_h) / 2
    bldg_x1 = bldg_x0 + bldg_w
    bldg_y1 = bldg_y0 + bldg_h
    
    # Concrete base
    draw.rectangle([bldg_x0, bldg_y0, bldg_x1, bldg_y1], fill='#E0F7FA', outline='#00838F', width=2)
    
    room_items = []
    for rtype, count in rooms.items():
        for _ in range(count):
            room_items.append((rtype, STANDARD_ROOM_SIZES.get(rtype, 10)))
            
    corr_y0 = bldg_y0
    corr_y1 = bldg_y1
    corr_h = 0
            
    if room_items:
        corr_h = 40
        if bldg_h < 100: corr_h = 20
        
        corr_y0 = bldg_y0 + (bldg_h - corr_h) / 2
        corr_y1 = corr_y0 + corr_h
        
        top_rect = [bldg_x0, bldg_y0, bldg_x1, corr_y0]
        bottom_rect = [bldg_x0, corr_y1, bldg_x1, bldg_y1]
        
        top_rooms = []
        bottom_rooms = []
        top_weight = 0
        bottom_weight = 0
        
        room_items.sort(key=lambda x: x[1], reverse=True)
        
        for r in room_items:
            if top_weight <= bottom_weight:
                top_rooms.append(r)
                top_weight += r[1]
            else:
                bottom_rooms.append(r)
                bottom_weight += r[1]
                
        def draw_wing(wing_rect, wing_rooms, is_top):
            wx0, wy0, wx1, wy1 = wing_rect
            total_w = sum(w for _, w in wing_rooms)
            if total_w == 0: return
            
            curr_x = wx0
            for i, (rtype, w) in enumerate(wing_rooms):
                ratio = w / total_w
                room_width = (wx1 - wx0) * ratio
                room_rect = [curr_x, wy0, curr_x + room_width, wy1]
                
                # Draw room
                draw.rectangle(room_rect, fill=ROOM_COLORS.get(rtype, "#EEEEEE"), outline='#78909C', width=2)
                
                # Dimensions
                real_w = room_width * px_to_m
                real_h = (wy1 - wy0) * px_to_m
                dim_str = f"{real_w:.1f}m x {real_h:.1f}m"
                
                # Draw Windows (blue rectangles on exterior walls)
                win_len = min(40, room_width * 0.5)
                win_x0 = curr_x + (room_width - win_len) / 2
                if is_top:
                    draw.rectangle([win_x0, wy0 - 2, win_x0 + win_len, wy0 + 2], fill='#81D4FA', outline='#0277BD')
                else:
                    draw.rectangle([win_x0, wy1 - 2, win_x0 + win_len, wy1 + 2], fill='#81D4FA', outline='#0277BD')

                # Draw Furniture
                furn_x = curr_x + 10
                furn_y = wy0 + 25 if is_top else wy0 + 10
                
                if rtype == "bedrooms":
                    # Bed
                    draw.rectangle([furn_x, furn_y, furn_x + 20, furn_y + 30], fill='#FFFFFF', outline='#9E9E9E')
                    # Pillow
                    draw.rectangle([furn_x + 2, furn_y + 2, furn_x + 18, furn_y + 10], fill='#E0E0E0')
                elif rtype == "bathrooms":
                    # Bathtub
                    draw.rectangle([furn_x, furn_y, furn_x + 15, furn_y + 25], fill='#FFFFFF', outline='#9E9E9E')
                    draw.ellipse([furn_x+2, furn_y+2, furn_x + 13, furn_y + 23], outline='#BDBDBD')
                elif rtype == "kitchens":
                    # Counter
                    draw.rectangle([curr_x + 5, wy0 + 5, curr_x + room_width - 5, wy0 + 15], fill='#BDBDBD', outline='#757575')
                    # Stove circles
                    draw.ellipse([curr_x + 10, wy0 + 7, curr_x + 14, wy0 + 11], fill='#424242')
                    draw.ellipse([curr_x + 16, wy0 + 7, curr_x + 20, wy0 + 11], fill='#424242')
                elif rtype == "living_rooms":
                    # Sofa (L-shape)
                    draw.rectangle([furn_x, furn_y, furn_x + 30, furn_y + 10], fill='#90CAF9')
                    draw.rectangle([furn_x, furn_y, furn_x + 10, furn_y + 25], fill='#90CAF9')
                elif rtype == "offices":
                    # Desk
                    draw.rectangle([furn_x, furn_y, furn_x + 25, furn_y + 10], fill='#A1887F')
                    # Chair
                    draw.ellipse([furn_x + 8, furn_y + 12, furn_x + 17, furn_y + 21], fill='#607D8B')

                # Draw Door
                door_width = 15
                door_x = curr_x + (room_width - door_width) / 2
                
                if is_top:
                    draw.rectangle([door_x, wy1 - 2, door_x + door_width, wy1 + 2], fill='#FFFFFF', outline='#FFFFFF')
                else:
                    draw.rectangle([door_x, wy0 - 2, door_x + door_width, wy0 + 2], fill='#FFFFFF', outline='#FFFFFF')

                # Labels
                label = rtype[:-1].capitalize() if rtype.endswith('s') else rtype.capitalize()
                draw.text((curr_x + 5, wy0 + 5 if is_top else wy1 - 30), label, fill='#263238')
                draw.text((curr_x + 5, wy0 + 15 if is_top else wy1 - 18), dim_str, fill='#546E7A')
                
                curr_x += room_width

        draw_wing(top_rect, top_rooms, is_top=True)
        draw_wing(bottom_rect, bottom_rooms, is_top=False)
        
        # Draw Corridor floor
        draw.rectangle([bldg_x0, corr_y0, bldg_x1, corr_y1], fill='#CFD8DC', outline='#90A4AE', width=1)
        draw.text((bldg_x0 + 10, corr_y0 + (corr_h/2) - 5), "Central Hallway", fill='#455A64')

    # Parking & Path
    if parking > 0:
        park_w = 40
        park_h = 60
        start_x = margin + 10
        start_y = img_height - margin - park_h - 10
        
        # Entrance Path from Parking to Hallway
        path_x0 = start_x + (min(parking, 5) * (park_w + 10)) + 10
        path_x1 = bldg_x0
        # Draw path
        if room_items:
            draw.rectangle([path_x0, corr_y0 + 5, path_x1, corr_y1 - 5], fill='#E0E0E0', outline='#9E9E9E')
        
        for i in range(min(parking, 5)):
            px0 = start_x + i * (park_w + 10)
            py0 = start_y
            px1 = px0 + park_w
            py1 = py0 + park_h
            draw.rectangle([px0, py0, px1, py1], fill='#9E9E9E', outline='#616161', width=2)
            # Parking lines
            draw.line([px0+10, py0, px0+10, py1], fill='#FFFFFF', width=1)
            draw.text((px0 + 15, py0 + 20), "P", fill='#FFFFFF')
            
    draw.rectangle([margin, margin, margin + 150, margin + 40], fill='#FFFFFF', outline='#000000')
    draw.text((margin + 10, margin + 10), f"Plot Size: {plot_size} sqm", fill='black')
    
    if not room_items:
        draw.text((bldg_x0 + 10, bldg_y0 + 10), f"Building Footprint", fill='black')
        draw.text((bldg_x0 + 10, bldg_y0 + 30), f"Floors: {floors}", fill='black')
        draw.text((bldg_x0 + 10, bldg_y0 + 50), f"Usage: {usage.capitalize()}", fill='black')
        
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return f"data:image/png;base64,{img_str}"
