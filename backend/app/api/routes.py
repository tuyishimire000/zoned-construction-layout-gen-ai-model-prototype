from fastapi import APIRouter, HTTPException, Response
from app.api.schemas import (
    ProjectDescriptionRequest,
    AnalysisResponse,
    ProjectParameters,
    ComplianceResult,
)
from app.nlp.extractor import extract_parameters
from app.compliance.validator import validate_project
from app.visualization.floorplan_generator import generate_floorplan
from app.visualization.site_plan_spec import build_site_plan
from app.visualization.png_renderer import render_png, render_png_bytes

router = APIRouter()


@router.get("/site-plan/sample.png")
def sample_site_plan_png():
    """Raw PNG of the hand-authored static site plan.

    Open in a browser (http://localhost:8000/api/site-plan/sample.png) and just
    refresh after editing site_plan_spec.py to iterate on the layout.
    """
    return Response(content=render_png_bytes(build_site_plan()), media_type="image/png")


@router.get("/site-plan/sample")
def sample_site_plan():
    """Same static plan as a base64 data URI, for the frontend <img> pattern."""
    return {"floor_plan_base64": render_png(build_site_plan())}


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_project(request: ProjectDescriptionRequest):
    # 1. NLP Extraction
    try:
        params_dict = extract_parameters(request.description)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error in NLP extraction: {str(e)}"
        )

    # 2. Compliance Evaluation
    try:
        compliance_dict = validate_project(params_dict)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error in compliance validation: {str(e)}"
        )

    # 3. Floor Plan Generation
    try:
        img_base64 = generate_floorplan(params_dict, compliance_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error in image generation: {str(e)}"
        )

    # Construct Report Data (passed to frontend for rendering)
    report_data = {
        "title": "Smart Building Compliance Report",
        "summary": f"A proposed {params_dict.get('usage', 'residential')} building with {params_dict.get('floors', 1)} floors on a {params_dict.get('plot_size', 'unknown')} sqm plot.",
    }

    return AnalysisResponse(
        extracted_parameters=ProjectParameters(**params_dict),
        compliance=ComplianceResult(**compliance_dict),
        floor_plan_base64=img_base64,
        report_data=report_data,
    )


@router.post("/render", response_model=AnalysisResponse)
def render_project(params: ProjectParameters):
    """Bypasses NLP and directly renders the layout from parameters."""
    params_dict = params.model_dump()
    
    try:
        compliance_dict = validate_project(params_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in compliance validation: {str(e)}")

    try:
        img_base64 = generate_floorplan(params_dict, compliance_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in image generation: {str(e)}")

    report_data = {
        "title": "Smart Building Compliance Report",
        "summary": f"A proposed {params_dict.get('usage', 'residential')} building with {params_dict.get('floors', 1)} floors on a {params_dict.get('plot_size', 'unknown')} sqm plot.",
    }

    return AnalysisResponse(
        extracted_parameters=params,
        compliance=ComplianceResult(**compliance_dict),
        floor_plan_base64=img_base64,
        report_data=report_data,
    )
