import spacy
from spacy.matcher import Matcher
import re

# Load English tokenizer, tagger, parser and NER
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Fallback if not downloaded yet
    import spacy.cli
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

matcher = Matcher(nlp.vocab)

# Patterns for plot size
size_pattern1 = [{"LIKE_NUM": True}, {"LOWER": "sqm"}]
size_pattern2 = [{"LIKE_NUM": True}, {"LOWER": "square"}, {"LOWER": "meters"}]
matcher.add("PLOT_SIZE", [size_pattern1, size_pattern2])

# Patterns for floors
floor_pattern1 = [{"LIKE_NUM": True}, {"LOWER": "floors"}]
floor_pattern2 = [{"LIKE_NUM": True}, {"LOWER": "story"}]
floor_pattern3 = [{"LIKE_NUM": True}, {"LOWER": "-"}, {"LOWER": "story"}]
floor_pattern4 = [{"LIKE_NUM": True}, {"LOWER": "storey"}]
floor_pattern5 = [{"LIKE_NUM": True}, {"LOWER": "-"}, {"LOWER": "storey"}]
matcher.add("FLOORS", [floor_pattern1, floor_pattern2, floor_pattern3, floor_pattern4, floor_pattern5])

# Patterns for parking
parking_pattern1 = [{"LOWER": "parking"}, {"LOWER": "for", "OP": "?"}, {"LIKE_NUM": True}]
matcher.add("PARKING", [parking_pattern1])

# Usage types
usages = ["residential", "commercial", "industrial", "mixed-use"]

# Word to number mapping
word_to_num = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
}

def parse_number(text):
    text = text.lower().strip()
    if text in word_to_num:
        return word_to_num[text]
    try:
        return float(text)
    except ValueError:
        return None

def extract_parameters(description: str) -> dict:
    doc = nlp(description)
    matches = matcher(doc)
    
    params = {
        "plot_size": None,
        "floors": None,
        "usage": None,
        "parking_spaces": None
    }
    
    for match_id, start, end in matches:
        string_id = nlp.vocab.strings[match_id]
        span = doc[start:end]
        
        if string_id == "PLOT_SIZE":
            num = parse_number(span[0].text)
            if num is not None:
                params["plot_size"] = num
                
        elif string_id == "FLOORS":
            num = parse_number(span[0].text)
            if num is not None:
                params["floors"] = int(num)
                
        elif string_id == "PARKING":
            # the number is the last token
            num = parse_number(span[-1].text)
            if num is not None:
                params["parking_spaces"] = int(num)
                
    # Search for usage directly
    desc_lower = description.lower()
    for u in usages:
        if u in desc_lower:
            params["usage"] = u
            break
            
    return params
