from fastapi import APIRouter, HTTPException, Response, Depends
from sqlalchemy.orm import Session
from app.api.schemas import (
    ProjectDescriptionRequest,
    AnalysisResponse,
    ProjectParameters,
    ComplianceResult,
    ChatRequest,
    ChatResponse,
    ChatMessage as SchemaChatMessage,
    ReportData,
)
from app.nlp.extractor import extract_parameters, extract_parameters_from_history
from app.compliance.validator import validate_project
from app.compliance.graph_validator import validate_and_repair_graph
from app.visualization.floorplan_generator import generate_floorplan
from app.data.db import get_db, ChatSession, ChatMessage

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def chat_with_architect(request: ChatRequest, db: Session = Depends(get_db)):
    session_id = request.session_id
    try:
        # 1. Load or create session
        if session_id:
            chat_session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if not chat_session:
                raise HTTPException(status_code=404, detail="Session not found")
        else:
            chat_session = ChatSession()
            db.add(chat_session)
            db.commit()
            db.refresh(chat_session)
            session_id = chat_session.id
            
        # 2. Save user message
        user_msg = ChatMessage(session_id=session_id, role="user", content=request.message)
        db.add(user_msg)
        db.commit()
        
        # 3. Retrieve full history
        history = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.timestamp).all()
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Database or route error: {str(e)}\n{tb}")
    messages_list = [{"role": msg.role, "content": msg.content} for msg in history]
    
    # 4. Generate parameters from history
    try:
        params_dict = extract_parameters_from_history(messages_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in NLP extraction: {str(e)}")
        
    # 5. Generate floor plan
    try:
        params_dict, ai_fixes = validate_and_repair_graph(params_dict)
        compliance_dict = validate_project(params_dict)
        if ai_fixes:
            compliance_dict["recommendations"].extend(ai_fixes)
        img_data, dxf_data, score = generate_floorplan(params_dict, compliance_dict, 'png')
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Error in layout generation: {str(e)}\n\n{tb}")
        
    # 6. Save AI response (a summary of actions)
    # The AI does not generate a text response in extractor right now, it just generates JSON.
    # We can create a simple summary string as the AI's response message.
    ai_content = f"I've updated the layout! It's a {params_dict.get('usage', 'residential')} building with {params_dict.get('floors', 1)} floors on a {params_dict.get('plot_size')} sqm plot."
    ai_msg = ChatMessage(session_id=session_id, role="assistant", content=ai_content)
    db.add(ai_msg)
    
    # Save the project state
    chat_session.current_state = params_dict
    db.commit()
    
    # Append the new AI message to our history for the response
    messages_list.append({"role": "assistant", "content": ai_content})
    schema_messages = [SchemaChatMessage(**m) for m in messages_list]
    
    report_data = ReportData(
        title="Smart Building Compliance Report",
        summary=ai_content,
    )
    
    analysis = AnalysisResponse(
        extracted_parameters=ProjectParameters(**params_dict),
        compliance=ComplianceResult(**compliance_dict),
        floor_plan_base64=img_data,
        dxf_base64=dxf_data,
        architectural_score=score,
        report_data=report_data,
    )
    
    return ChatResponse(
        session_id=session_id,
        messages=schema_messages,
        analysis=analysis
    )


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

    # 1.5 Graph Validation and Repair
    try:
        params_dict, ai_fixes = validate_and_repair_graph(params_dict)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error in graph validation: {str(e)}"
        )

    # 2. Compliance Evaluation
    try:
        compliance_dict = validate_project(params_dict)
        if ai_fixes:
            compliance_dict["recommendations"].extend(ai_fixes)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error in compliance validation: {str(e)}"
        )

    # 3. Floor Plan Generation
    try:
        img_data, dxf_data, score = generate_floorplan(params_dict, compliance_dict, request.export_format)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=str(e)
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500, detail=f"Error in image generation: {str(e)}\n\n{tb}"
        )

    # Construct Report Data (passed to frontend for rendering)
    report_data = {
        "title": "Smart Building Compliance Report",
        "summary": f"A proposed {params_dict.get('usage', 'residential')} building with {params_dict.get('floors', 1)} floors on a {params_dict.get('plot_size', 'unknown')} sqm plot.",
    }

    return AnalysisResponse(
        extracted_parameters=ProjectParameters(**params_dict),
        compliance=ComplianceResult(**compliance_dict),
        floor_plan_base64=img_data,
        dxf_base64=dxf_data,
        architectural_score=score,
        report_data=report_data,
    )


@router.post("/render", response_model=AnalysisResponse)
def render_project(params: ProjectParameters):
    """Bypasses NLP and directly renders the layout from parameters."""
    params_dict = params.model_dump()
    
    try:
        params_dict, ai_fixes = validate_and_repair_graph(params_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in graph validation: {str(e)}")

    try:
        compliance_dict = validate_project(params_dict)
        if ai_fixes:
            compliance_dict["recommendations"].extend(ai_fixes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in compliance validation: {str(e)}")

    try:
        img_data, dxf_data, score = generate_floorplan(params_dict, compliance_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Error in image generation: {str(e)}\n\n{tb}")

    report_data = {
        "title": "Smart Building Compliance Report",
        "summary": f"A proposed {params_dict.get('usage', 'residential')} building with {params_dict.get('floors', 1)} floors on a {params_dict.get('plot_size', 'unknown')} sqm plot.",
    }

    return AnalysisResponse(
        extracted_parameters=params,
        compliance=ComplianceResult(**compliance_dict),
        floor_plan_base64=img_data,
        dxf_base64=dxf_data,
        architectural_score=score,
        report_data=report_data,
    )
