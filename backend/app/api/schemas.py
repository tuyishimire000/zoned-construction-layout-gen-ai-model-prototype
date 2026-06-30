from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class UserCreate(BaseModel):
    full_name: Optional[str] = None
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    full_name: Optional[str] = None
    email: str

class Token(BaseModel):
    access_token: str
    token_type: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class VerifyEmailRequest(BaseModel):
    token: str

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

class ReportData(BaseModel):
    title: str
    summary: str

class AnalysisResponse(BaseModel):
    extracted_parameters: ProjectParameters
    compliance: ComplianceResult
    floor_plan_base64: str
    dxf_base64: Optional[str] = None
    architectural_score: float = 0.0
    report_data: Optional[ReportData] = None

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatResponse(BaseModel):
    session_id: str
    messages: List[ChatMessage]
    analysis: Optional[AnalysisResponse] = None
    is_owner: bool = True
    is_public: bool = False
