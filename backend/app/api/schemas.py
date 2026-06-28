from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ProjectDescriptionRequest(BaseModel):
    description: str
    export_format: str = "png"

class RoomCounts(BaseModel):
    bedrooms: int = 0
    bathrooms: int = 0
    kitchens: int = 0
    living_rooms: int = 0
    offices: int = 0
    outside_kitchens: int = 0
    outside_bathrooms: int = 0
    maid_rooms: int = 0
    corridors: int = 0

class RoomInstance(BaseModel):
    id: str
    room_type: str

class AdjacencyEdge(BaseModel):
    room_a: str
    room_b: str
    weight: int = 1

class LayoutGraph(BaseModel):
    rooms: List[RoomInstance] = []
    connections: List[AdjacencyEdge] = []

class ProjectParameters(BaseModel):
    plot_size: Optional[float] = None
    floors: Optional[int] = None
    usage: Optional[str] = None
    parking_spaces: Optional[int] = None
    rooms: RoomCounts = RoomCounts()
    graph: Optional[LayoutGraph] = None

class ComplianceResult(BaseModel):
    compliant: bool
    allowed_area: Optional[float] = None
    max_floors: Optional[int] = None
    violated_regulations: List[str] = []
    recommendations: List[str] = []
    metrics: Dict[str, Any] = {}

class AnalysisResponse(BaseModel):
    extracted_parameters: ProjectParameters
    compliance: ComplianceResult
    floor_plan_base64: str
    architectural_score: float = 0.0
    report_data: Dict[str, Any]
