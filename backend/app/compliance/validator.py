import json
import os
from typing import Dict, Any

RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "zoning_rules.json")

def load_rules() -> dict:
    with open(RULES_PATH, "r") as f:
        return json.load(f)

def validate_project(params: dict) -> dict:
    rules = load_rules()
    
    usage = params.get("usage", "residential") # Default to residential if not specified
    if usage not in rules:
        usage = "residential"
        
    usage_rules = rules[usage]
    
    plot_size = params.get("plot_size") or 600.0
    floors = params.get("floors") or 1
    
    allowed_area = plot_size * usage_rules["max_site_coverage"]
    
    violations = []
    recommendations = []
    
    if floors > usage_rules["max_floors"]:
        violations.append(f"Number of floors ({floors}) exceeds maximum allowed ({usage_rules['max_floors']}) for {usage} zoning.")
        recommendations.append(f"Reduce the number of floors to {usage_rules['max_floors']} or apply for a special variance.")
        
    # Mocking footprint based on a standard assumption if not provided
    # Assuming building takes up roughly 50% of the plot to check coverage
    assumed_footprint = plot_size * 0.5
    coverage = assumed_footprint / plot_size if plot_size > 0 else 0
    
    if coverage > usage_rules["max_site_coverage"]:
        violations.append(f"Site coverage ({coverage*100:.1f}%) exceeds maximum allowed ({usage_rules['max_site_coverage']*100:.1f}%).")
        recommendations.append(f"Reduce building footprint to be under {allowed_area} sqm.")
        
    STANDARD_ROOM_SIZES = {
        "bedrooms": 24,
        "bathrooms": 8,
        "kitchens": 18,
        "living_rooms": 35,
        "offices": 16,
        "outside_kitchens": 12,
        "outside_bathrooms": 6,
        "maid_rooms": 12,
        "corridors": 15
    }
    
    rooms = params.get("rooms", {})
    total_room_area = sum(rooms.get(room_type, 0) * size for room_type, size in STANDARD_ROOM_SIZES.items())
    total_allowed_internal_area = allowed_area * floors
    
    if total_room_area > total_allowed_internal_area:
        violations.append(f"Total requested room area ({total_room_area} sqm) exceeds estimated available internal area ({total_allowed_internal_area:.1f} sqm).")
        recommendations.append("Reduce the number of rooms or increase the plot size/floors.")
        
    # AI-assisted architectural recommendations
    bedrooms = rooms.get("bedrooms", 0)
    bathrooms = rooms.get("bathrooms", 0)
    kitchens = rooms.get("kitchens", 0)
    
    if bedrooms > 0 and bathrooms == 0:
        recommendations.append("AI Tip: A residential home with bedrooms should have at least 1 bathroom.")
    elif bedrooms >= 3 and bathrooms < 2:
        recommendations.append(f"AI Tip: For a {bedrooms}-bedroom home, it is highly recommended to have at least 2 bathrooms.")
        
    if (bedrooms > 0 or bathrooms > 0) and kitchens == 0:
        recommendations.append("AI Tip: Most residential homes require at least 1 kitchen area.")

        
    compliant = len(violations) == 0
    
    if compliant:
        recommendations.append("Project meets basic zoning requirements.")
    
    return {
        "compliant": compliant,
        "allowed_area": allowed_area,
        "max_floors": usage_rules["max_floors"],
        "violated_regulations": violations,
        "recommendations": recommendations,
        "metrics": {
            "site_coverage_limit": usage_rules["max_site_coverage"],
            "assumed_footprint": assumed_footprint,
            "plot_size": plot_size,
            "floors": floors,
            "usage": usage,
            "total_room_area": total_room_area,
            "total_allowed_internal_area": total_allowed_internal_area
        }
    }
