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
    
    # Plot boundary
    draw.rectangle([margin, margin, img_width-margin, img_height-margin], outline='green', width=3)
    
    # Building footprint
    scale_factor = math.sqrt(coverage_limit) * 0.8
    bldg_w = plot_w * scale_factor
    bldg_h = plot_h * scale_factor
    bldg_x0 = margin + (plot_w - bldg_w) / 2
    bldg_y0 = margin + (plot_h - bldg_h) / 2
    bldg_x1 = bldg_x0 + bldg_w
    bldg_y1 = bldg_y0 + bldg_h
    
    draw.rectangle([bldg_x0, bldg_y0, bldg_x1, bldg_y1], fill='#E0F7FA', outline='#00838F', width=2)
    
    room_items = []
    for rtype, count in rooms.items():
        for _ in range(count):
            room_items.append((rtype, STANDARD_ROOM_SIZES.get(rtype, 10)))
            
    if room_items:
        # Architect-Level Features: Corridor and doors
        corr_h = 40
        # If building is very small, scale corridor
        if bldg_h < 100: corr_h = 20
        
        corr_y0 = bldg_y0 + (bldg_h - corr_h) / 2
        corr_y1 = corr_y0 + corr_h
        
        top_rect = [bldg_x0, bldg_y0, bldg_x1, corr_y0]
        bottom_rect = [bldg_x0, corr_y1, bldg_x1, bldg_y1]
        
        # Split rooms roughly in half by weight
        top_rooms = []
        bottom_rooms = []
        top_weight = 0
        bottom_weight = 0
        
        # Sort rooms so big rooms go first
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
            for rtype, w in wing_rooms:
                ratio = w / total_w
                room_width = (wx1 - wx0) * ratio
                room_rect = [curr_x, wy0, curr_x + room_width, wy1]
                
                # Draw room
                draw.rectangle(room_rect, fill=ROOM_COLORS.get(rtype, "#EEEEEE"), outline='gray', width=2)
                
                # Draw Door
                door_width = 20
                door_x = curr_x + (room_width - door_width) / 2
                
                if is_top:
                    # Door on bottom edge
                    draw.rectangle([door_x, wy1 - 3, door_x + door_width, wy1 + 3], fill='#E0F7FA', outline='#E0F7FA')
                else:
                    # Door on top edge
                    draw.rectangle([door_x, wy0 - 3, door_x + door_width, wy0 + 3], fill='#E0F7FA', outline='#E0F7FA')

                # Label
                label = rtype[:-1].capitalize() if rtype.endswith('s') else rtype.capitalize()
                draw.text((curr_x + 5, wy0 + 5), label, fill='black')
                
                curr_x += room_width

        draw_wing(top_rect, top_rooms, is_top=True)
        draw_wing(bottom_rect, bottom_rooms, is_top=False)
        
        # Draw Corridor floor
        draw.rectangle([bldg_x0, corr_y0, bldg_x1, corr_y1], fill='#CFD8DC', outline='gray', width=1)
        draw.text((bldg_x0 + 10, corr_y0 + (corr_h/2) - 5), "Central Hallway", fill='#455A64')

    # Parking
    if parking > 0:
        park_w = 40
        park_h = 60
        start_x = margin + 10
        start_y = img_height - margin - park_h - 10
        
        for i in range(min(parking, 5)):
            px0 = start_x + i * (park_w + 10)
            py0 = start_y
            px1 = px0 + park_w
            py1 = py0 + park_h
            draw.rectangle([px0, py0, px1, py1], fill='#EEEEEE', outline='gray', width=1)
            draw.text((px0 + 5, py0 + 20), "P", fill='black')
            
    draw.text((margin + 10, margin + 10), f"Plot Size: {plot_size} sqm", fill='black')
    if not room_items:
        draw.text((bldg_x0 + 10, bldg_y0 + 10), f"Building Footprint", fill='black')
        draw.text((bldg_x0 + 10, bldg_y0 + 30), f"Floors: {floors}", fill='black')
        draw.text((bldg_x0 + 10, bldg_y0 + 50), f"Usage: {usage.capitalize()}", fill='black')
        
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return f"data:image/png;base64,{img_str}"
