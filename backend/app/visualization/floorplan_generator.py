import io
import base64
from PIL import Image, ImageDraw, ImageFont

def generate_floorplan(params: dict, compliance: dict) -> str:
    # Basic dimensions
    img_width = 800
    img_height = 600
    
    # Create a white canvas
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Extract params
    plot_size = params.get('plot_size') or 500
    floors = params.get('floors') or 1
    parking = params.get('parking_spaces') or 0
    usage = params.get('usage', 'residential')
    
    metrics = compliance.get('metrics', {})
    coverage_limit = metrics.get('site_coverage_limit', 0.6)
    
    # Margin
    margin = 50
    plot_w = img_width - 2 * margin
    plot_h = img_height - 2 * margin
    
    # Draw plot boundary (Green dashed outline)
    draw.rectangle([margin, margin, img_width-margin, img_height-margin], outline='green', width=3)
    
    # Draw Building footprint
    # Simplified: put it in the middle, scaled to coverage limit (roughly)
    # Using sqrt to map area ratio to linear scale ratio
    import math
    scale_factor = math.sqrt(coverage_limit) * 0.8 # 80% of allowed max to look nice
    
    bldg_w = plot_w * scale_factor
    bldg_h = plot_h * scale_factor
    
    bldg_x0 = margin + (plot_w - bldg_w) / 2
    bldg_y0 = margin + (plot_h - bldg_h) / 2
    bldg_x1 = bldg_x0 + bldg_w
    bldg_y1 = bldg_y0 + bldg_h
    
    # Draw building footprint
    draw.rectangle([bldg_x0, bldg_y0, bldg_x1, bldg_y1], fill='#E0F7FA', outline='#00838F', width=2)
    
    # Draw parking
    if parking > 0:
        park_w = 40
        park_h = 60
        start_x = margin + 10
        start_y = img_height - margin - park_h - 10
        
        for i in range(min(parking, 5)): # Draw max 5 to fit
            px0 = start_x + i * (park_w + 10)
            py0 = start_y
            px1 = px0 + park_w
            py1 = py0 + park_h
            draw.rectangle([px0, py0, px1, py1], fill='#EEEEEE', outline='gray', width=1)
            draw.text((px0 + 5, py0 + 20), "P", fill='black')
            
    # Add text labels
    draw.text((margin + 10, margin + 10), f"Plot Size: {plot_size} sqm", fill='black')
    draw.text((bldg_x0 + 10, bldg_y0 + 10), f"Building Footprint", fill='black')
    draw.text((bldg_x0 + 10, bldg_y0 + 30), f"Floors: {floors}", fill='black')
    draw.text((bldg_x0 + 10, bldg_y0 + 50), f"Usage: {usage.capitalize()}", fill='black')
    
    # Encode to base64
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    
    return f"data:image/png;base64,{img_str}"
