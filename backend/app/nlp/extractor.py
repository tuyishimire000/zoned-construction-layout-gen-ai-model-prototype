import os
import json
from typing import Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class RoomCounts(BaseModel):
    bedrooms: int = Field(default=0)
    bathrooms: int = Field(default=0)
    kitchens: int = Field(default=0)
    living_rooms: int = Field(default=0)
    offices: int = Field(default=0)
    outside_kitchens: int = Field(default=0, description="Outdoor or annex kitchens")
    outside_bathrooms: int = Field(default=0, description="Outdoor or annex bathrooms")
    maid_rooms: int = Field(default=0, description="Maid or staff rooms in the annex")

class ExtractorSchema(BaseModel):
    plot_size: float | None = Field(default=600.0, description="Plot size in sqm. Default to 600 if not specified.")
    floors: int | None = Field(default=1, description="Number of floors. Default to 1.")
    usage: str | None = Field(default="residential", description="Usage type: residential, commercial, industrial, or mixed-use.")
    parking_spaces: int | None = Field(default=0, description="Number of parking spaces.")
    rooms: RoomCounts

def extract_parameters(description: str) -> Dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing. Please create a .env file and add your key.")
        
    from google import genai
    from google.genai import types
    
    client = genai.Client()
    
    prompt = f"""
    You are an expert architectural assistant. Extract the exact building parameters and room counts from the following user request.
    Pay close attention to implicit counts (e.g., 'a master suite and a guest room' = 2 bedrooms).
    If a plot size is not specified, default to 600. If floors are not specified, default to 1.
    Distinguish between regular kitchens/bathrooms and "outside" or "annex" ones. 
    Map "maid house" or "staff room" to maid_rooms.
    
    User Request: "{description}"
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractorSchema,
            temperature=0.1,
        ),
    )
    
    try:
        data = json.loads(response.text)
        return data
    except Exception as e:
        raise ValueError(f"Failed to parse AI output: {e}")
