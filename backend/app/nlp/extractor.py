import os
import json
from typing import Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class RoomSpecSchema(BaseModel):
    type: str = Field(description="Room type: bedroom, bathroom, kitchen, living_room, dining, office, corridor (use for hallway), veranda, store")
    name: str | None = Field(default=None, description="Friendly name, e.g. 'Master Bedroom'")
    id: str = Field(description="A short, unique identifier, e.g. 'porch', 'liv', 'kit', 'bed1'")
    width: float | None = Field(default=None, description="Width in meters (X-axis)")
    depth: float | None = Field(default=None, description="Depth in meters (Y-axis)")
    position: list[float] | None = Field(default=None, description="Absolute position [x, y] in meters. The very first anchor room MUST have this set, e.g. [2, 0].")
    adjacent_to: list[str] = Field(default_factory=list, description="List of room IDs this room must share an internal door with.")
    east_of: str | None = Field(default=None, description="ID of the room this is explicitly placed to the east (right) of.")
    west_of: str | None = Field(default=None, description="ID of the room this is explicitly placed to the west (left) of.")
    north_of: str | None = Field(default=None, description="ID of the room this is explicitly placed to the north (above) of.")
    south_of: str | None = Field(default=None, description="ID of the room this is explicitly placed to the south (below) of.")
    align: str | None = Field(default=None, description="Alignment along shared wall: 'start', 'center', or 'end'. Use with east_of, west_of, north_of, or south_of.")
    offset: float | None = Field(default=None, description="Offset in meters to slide the room along the shared wall.")
    gap: float | None = Field(default=None, description="Gap in meters to leave instead of sharing the wall directly.")
    entrances: list[str] = Field(default_factory=list, description="Exterior doors on walls: 'left', 'right', 'top', 'bottom'.")
    zone: str | None = Field(default=None, description="'public' or 'private'")

class ExtractorSchema(BaseModel):
    plot_size: float | None = Field(default=600.0, description="Plot size in sqm. Default to 600 if not specified.")
    setback: float | None = Field(default=3.0, description="Plot setback in meters (yard space). Default is 3.0.")
    floors: int | None = Field(default=1, description="Number of floors. Default to 1.")
    usage: str | None = Field(default="residential", description="Usage type: residential, commercial, industrial, or mixed-use.")
    parking_spaces: int | None = Field(default=0, description="Number of parking spaces.")
    rooms: list[RoomSpecSchema] = Field(description="List of rooms defining the floor plan layout.")
    archetype: str | None = Field(default="auto", description="Deprecated, leave as 'auto'.")

def extract_parameters_from_history(messages: list[dict], current_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing. Please create a .env file and add your key.")
        
    from google import genai
    from google.genai import types
    
    client = genai.Client()
    
    # Format the conversation history into a single string for context
    history_text = ""
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role}: {msg['content']}\n\n"
        
    state_prompt = ""
    if current_state:
        state_prompt = f"""
    CURRENT LAYOUT STATE:
    {json.dumps(current_state, indent=2)}
    
    CRITICAL INSTRUCTION: You MUST retain the existing layout exactly as provided above, including room IDs, anchors, widths, depths, and existing relationships. ONLY modify the specific parts of the layout requested in the user's latest message (e.g. updating the `adjacent_to` list to add a door, or modifying a specific room's dimensions). DO NOT generate a brand new layout from scratch!
    """
    
    prompt = f"""
    You are an expert architectural assistant and layout engine. Based on the conversation history below, design the FINAL floor plan.
    {state_prompt}
    
    Rules for Layout Generation:
    0. USER INSTRUCTIONS OVERRIDE DEFAULTS: If the user explicitly asks for specific room sizes (e.g., irregular dimensions), specific connections, or a unique layout, you MUST follow their exact instructions. The user's prompt is absolute law.
    1. To create U-shapes, L-shapes, or tuck/move rooms inward/outward (e.g. "move bedroom 3 inward by 2 meters"), you MUST use the `offset` parameter. For example, setting `offset=2.0` on a room placed `south_of` another room will slide it 2 meters along the shared wall, creating a staggered/irregular footprint! Use the `gap` parameter to create a separation between rooms instead of sharing a full wall.
    2. Output a list of RoomSpecSchema objects representing the exact layout of the house.
    3. Assign a unique `id` to each room (e.g., 'porch', 'liv', 'din', 'kit', 'corridor', 'bed1', 'master').
    4. The VERY FIRST room in the list (usually the anchor/living room) MUST have a `position` specified (e.g. [0,0] or [2,0]). All other rooms should ideally NOT have `position`, but instead use `east_of`, `west_of`, `north_of`, or `south_of` referencing an already-placed room `id`. 
       CRITICAL: Each subsequent room MUST have EXACTLY ONE directional field set pointing to a previously defined room.
       DO NOT create cyclic dependencies (e.g., A east_of B, B south_of A).
    4. Connect rooms with internal doors using the `adjacent_to` list (list the IDs of rooms it connects to).
    5. Specify exterior doors using `entrances` (e.g., ["bottom"] for the front porch, ["top"] for a back kitchen door).
    6. Include a 'corridor' (hallway) if necessary to connect private bedrooms and bathrooms. If the user mentions a hallway, map it to the 'corridor' type.
    7. Standard sizes (use unless user specifies otherwise): bedroom (~4x4), bathroom (~2.5x2.5), kitchen (~4x4), living_room (~6x5).
    8. ARCHITECTURAL BEST PRACTICES (Apply these as sensible defaults UNLESS the user requests otherwise):
       - Bathrooms MUST be distributed close to bedrooms (e.g., a Master Bedroom should have its own en-suite bathroom adjacent to it, and a secondary bathroom should be near the other bedrooms). Do NOT clump all bathrooms together far from bedrooms.
       - A 'veranda' or 'porch' MUST be adjacent to the 'living_room' and lead directly into it. It should NOT be isolated or connected only to the kitchen.
       - The kitchen should generally be near the dining room.
       - CONNECTIVITY: EVERY single room MUST be accessible. Ensure all rooms are connected via the `adjacent_to` list to create a sensible flow (e.g., bedrooms connect to the corridor, corridor connects to the living room). There must be NO isolated rooms without doors.
       - EXTERIOR DOORS: The house MUST have a main front entrance (e.g., an entrance on the Living Room or Porch) and a back exit (e.g., an entrance on the Kitchen or a back corridor).
       - The Dining Room MUST be directly adjacent to and connected to the Kitchen via `adjacent_to`.
    
    CONVERSATION HISTORY:
    {history_text}
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

def extract_parameters(description: str) -> Dict[str, Any]:
    # Backward compatibility for the /analyze endpoint
    return extract_parameters_from_history([{"role": "user", "content": description}])

def generate_summary(messages: list[dict], params: dict, compliance: dict) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "I've updated the layout based on your request."
        
    from google import genai
    from google.genai import types
    
    client = genai.Client()
    
    history_text = ""
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role}: {msg['content']}\n\n"
        
    prompt = f"""
    You are an expert architectural assistant. You just generated a new procedural floor plan based on the user's latest request.
    
    Here is the conversation history so far:
    {history_text}
    
    Here is the final layout specification that was just generated by the architectural engine:
    {json.dumps(params, indent=2)}
    
    Write a short, friendly, conversational response (1-3 sentences) to the user summarizing what you just built for them.
    Highlight any specific architectural style or archetype (e.g., L-shaped, central corridor) if one was chosen, and confirm the room counts. 
    Make it read naturally, as if you are presenting the updated design.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.4,
        ),
    )
    
    return response.text.strip()

def generate_title(prompt: str) -> str:
    """Generate a very short 2-4 word title for the project based on the initial prompt."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "New Project"
        
    from google import genai
    from google.genai import types
    client = genai.Client()
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Generate a short, snappy 2 to 4 word title for this architectural project based on this prompt: '{prompt}'. Output only the title, no quotes or extra text.",
            config=types.GenerateContentConfig(
                temperature=0.4,
            ),
        )
        title = response.text.strip().strip('"').strip("'")
        if not title:
            return "New Project"
        return title
    except Exception:
        # Fallback to thes first few words of the prompt
        words = prompt.split()
        if len(words) > 5:
            return " ".join(words[:5]) + "..."
        return prompt[:30]
