from fastapi import APIRouter, HTTPException
from app.api.schemas import ProjectDescriptionRequest, AnalysisResponse, ProjectParameters, ComplianceResult
from app.nlp.extractor import extract_parameters
from app.compliance.validator import validate_project
from app.visualization.floorplan_generator import generate_floorplan

router = APIRouter()

@router.post("/analyze", response_model=AnalysisResponse)
def analyze_project(request: ProjectDescriptionRequest):
    # 1. NLP Extraction
    try:
        params_dict = extract_parameters(request.description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in NLP extraction: {str(e)}")
        
    # 2. Compliance Evaluation
    try:
        compliance_dict = validate_project(params_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in compliance validation: {str(e)}")
        
    # 3. Floor Plan Generation
    try:
        img_base64 = generate_floorplan(params_dict, compliance_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in image generation: {str(e)}")
        
    # Construct Report Data (passed to frontend for rendering)
    report_data = {
        "title": "Smart Building Compliance Report",
        "summary": f"A proposed {params_dict.get('usage', 'residential')} building with {params_dict.get('floors', 1)} floors on a {params_dict.get('plot_size', 'unknown')} sqm plot.",
    }
    
    return AnalysisResponse(
        extracted_parameters=ProjectParameters(**params_dict),
        compliance=ComplianceResult(**compliance_dict),
        floor_plan_base64=img_base64,
        report_data=report_data
    )
