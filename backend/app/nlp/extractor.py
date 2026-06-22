import spacy
from typing import Dict, Any

# Load English tokenizer, tagger, parser and NER
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Fallback if not downloaded yet
    import spacy.cli
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

word_to_num = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'fifteen': 15, 'twenty': 20
}

def parse_number(text: str) -> float | None:
    text = text.lower().strip()
    if text in word_to_num:
        return float(word_to_num[text])
    try:
        return float(text)
    except ValueError:
        return None

def extract_parameters(description: str) -> Dict[str, Any]:
    doc = nlp(description)
    
    params = {
        "plot_size": None,
        "floors": None,
        "usage": None,
        "parking_spaces": None,
        "rooms": {
            "bedrooms": 0,
            "bathrooms": 0,
            "kitchens": 0,
            "living_rooms": 0,
            "offices": 0
        }
    }
    
    # 1. Extract usage
    usages = ["residential", "commercial", "industrial", "mixed-use"]
    desc_lower = description.lower()
    for u in usages:
        if u in desc_lower:
            params["usage"] = u
            break

    # 2. Extract numbers using a window-based proximity search
    # This is much more robust than strict phrase matchers
    
    area_keywords = {"sqm", "square", "meters", "m2", "m²", "area", "plot", "size"}
    floor_keywords = {"floors", "floor", "story", "stories", "storey", "levels", "level"}
    parking_keywords = {"parking", "cars", "vehicles", "spaces", "spots"}
    bedroom_keywords = {"bedroom", "bedrooms", "bed", "beds"}
    bathroom_keywords = {"bathroom", "bathrooms", "bath", "baths"}
    kitchen_keywords = {"kitchen", "kitchens"}
    living_keywords = {"living", "lounge"}
    office_keywords = {"office", "offices", "study"}

    for i, token in enumerate(doc):
        num = parse_number(token.text)
        if num is None and token.like_num:
            try:
                num = float(token.text)
            except:
                pass

        if num is not None:
            dist_area = 999
            dist_floor = 999
            dist_parking = 999
            dist_bedroom = 999
            dist_bathroom = 999
            dist_kitchen = 999
            dist_living = 999
            dist_office = 999
            
            # Look at a window of tokens around the number
            window = 8
            for j in range(max(0, i - window), min(len(doc), i + window + 1)):
                t = doc[j].text.lower()
                
                # Base distance is absolute difference in position
                d = abs(i - j)
                # Tie-breaker: keywords before the number are more likely labels
                if j > i:
                    d += 0.1
                    
                if t in area_keywords:
                    dist_area = min(dist_area, d)
                if t in floor_keywords:
                    dist_floor = min(dist_floor, d)
                if t in parking_keywords:
                    dist_parking = min(dist_parking, d)
                if t in bedroom_keywords:
                    dist_bedroom = min(dist_bedroom, d)
                if t in bathroom_keywords:
                    dist_bathroom = min(dist_bathroom, d)
                if t in kitchen_keywords:
                    dist_kitchen = min(dist_kitchen, d)
                if t in living_keywords:
                    dist_living = min(dist_living, d)
                if t in office_keywords:
                    dist_office = min(dist_office, d)

            min_dist = min(dist_area, dist_floor, dist_parking, dist_bedroom, dist_bathroom, dist_kitchen, dist_living, dist_office)
            
            if min_dist < 999:
                if min_dist == dist_area:
                    # Prefer larger numbers for area if ambiguous
                    if params["plot_size"] is None or num > params["plot_size"]:
                        params["plot_size"] = num
                elif min_dist == dist_floor:
                    if params["floors"] is None:
                        params["floors"] = int(num)
                elif min_dist == dist_parking:
                    if params["parking_spaces"] is None:
                        params["parking_spaces"] = int(num)
                elif min_dist == dist_bedroom:
                    params["rooms"]["bedrooms"] = int(num)
                elif min_dist == dist_bathroom:
                    params["rooms"]["bathrooms"] = int(num)
                elif min_dist == dist_kitchen:
                    params["rooms"]["kitchens"] = int(num)
                elif min_dist == dist_living:
                    params["rooms"]["living_rooms"] = int(num)
                elif min_dist == dist_office:
                    params["rooms"]["offices"] = int(num)

    return params
