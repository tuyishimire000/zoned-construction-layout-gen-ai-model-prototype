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
    corridors: int = Field(default=0, description="Connecting hallways")

class RoomInstance(BaseModel):
    id: str = Field(description="Unique ID, e.g., 'bedroom_1'")
    room_type: str = Field(description="Must exactly match a field in RoomCounts, e.g., 'bedrooms', 'corridors'")

class AdjacencyEdge(BaseModel):
    room_a: str = Field(description="ID of first room")
    room_b: str = Field(description="ID of second room")
    weight: int = Field(default=1, description="Importance of the connection (1 to 10)")

class LayoutGraph(BaseModel):
    rooms: list[RoomInstance] = Field(description="All individual rooms in the house, including inserted corridors.")
    connections: list[AdjacencyEdge] = Field(description="Pairs of rooms that share a door/wall. Insert and use 'corridor' nodes to connect private rooms together.")

class ExtractorSchema(BaseModel):
    plot_size: float | None = Field(default=600.0, description="Plot size in sqm. Default to 600 if not specified.")
    floors: int | None = Field(default=1, description="Number of floors. Default to 1.")
    usage: str | None = Field(default="residential", description="Usage type: residential, commercial, industrial, or mixed-use.")
    parking_spaces: int | None = Field(default=0, description="Number of parking spaces.")
    rooms: RoomCounts
    graph: LayoutGraph = Field(description="Topological map of how the rooms physically connect.")

def extract_parameters(description: str) -> Dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing. Please create a .env file and add your key.")
        
    from google import genai
    from google.genai import types
    
    client = genai.Client()
    
    prompt = f"""
    You are an expert architectural assistant. Extract building parameters, room counts, and generate an Adjacency Graph from the user request.
    
    Rules for the Adjacency Graph:
    1. For every room counted, create exactly that many RoomInstances with unique IDs.
    2. Define connections between rooms that should be adjacent.
    3. IMPORTANT: Assign a `weight` (1 to 10) to every connection. 10 means the connection is extremely critical (e.g., Living-Kitchen), 1 means it's a minor or optional connection.
    4. IMPORTANT: Unless the user specifically requests an open layout or NO hallways, do NOT connect bedrooms directly to living rooms or kitchens. Create "corridor" nodes to act as central spines. If they DO ask for no hallways, honor their request and connect rooms directly!
    5. Provide different layout styles based on clues in the prompt (e.g. L-shape if requested, courtyard if requested, otherwise standard functional flow).
    6. Always ensure standard rooms exist even if the user only specifies a subset (e.g., if they say "2-bedroom home", infer there must be a living room and a kitchen).
    7. If the user asks for a "long", "linear", or "shotgun" style layout, do not connect many rooms to a single corridor. Instead, create a chain of multiple corridor nodes (e.g., corridor_1 connecting to corridor_2) so the layout can stretch out linearly!
    8. If the user asks for bedrooms or living spaces in a separate annex, guest house, or outdoor area, you MUST classify those specific rooms as "maid_rooms" so the system knows to place them in the separate annex building.
    
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
