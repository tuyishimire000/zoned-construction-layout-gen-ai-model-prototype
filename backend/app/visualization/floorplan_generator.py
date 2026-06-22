import io
import base64
import math
from PIL import Image, ImageDraw, ImageFont

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
    
    # Process Rooms partitioning
    room_items = []
    for rtype, count in rooms.items():
        for _ in range(count):
            room_items.append((rtype, STANDARD_ROOM_SIZES.get(rtype, 10)))
            
    if room_items:
        # Alternating split partitioning
        total_weight = sum(w for _, w in room_items)
        current_rect = [bldg_x0, bldg_y0, bldg_x1, bldg_y1]
        
        remaining_weight = total_weight
        
        for i, (rtype, weight) in enumerate(room_items):
            ratio = weight / remaining_weight
            x0, y0, x1, y1 = current_rect
            w = x1 - x0
            h = y1 - y0
            
            # Split along longest axis
            if w > h:
                split_x = x0 + w * ratio
                room_rect = [x0, y0, split_x, y1]
                current_rect = [split_x, y0, x1, y1]
            else:
                split_y = y0 + h * ratio
                room_rect = [x0, y0, x1, split_y]
                current_rect = [x0, split_y, x1, y1]
                
            remaining_weight -= weight
            
            # Draw room
            draw.rectangle(room_rect, fill=ROOM_COLORS.get(rtype, "#EEEEEE"), outline='gray', width=1)
            # Label
            label = rtype[:-1].capitalize() if rtype.endswith('s') else rtype.capitalize()
            # Simple text centering logic
            text_x = room_rect[0] + 5
            text_y = room_rect[1] + 5
            draw.text((text_x, text_y), label, fill='black')

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
