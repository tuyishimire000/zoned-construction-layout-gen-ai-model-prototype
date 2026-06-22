from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class ProjectDescriptionRequest(BaseModel):
    description: str

class ProjectParameters(BaseModel):
    plot_size: Optional[float] = None
    floors: Optional[int] = None
    usage: Optional[str] = None
    parking_spaces: Optional[int] = None

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
    report_data: Dict[str, Any]
