import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import json

from ..core.database import get_db
from ..core.models import Template
from ..schemas.template import TemplateCreate, TemplateUpdate, TemplateResponse, TemplateListResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])

DEFAULT_TEMPLATE_CONFIG = {
    "canvas": {
        "width": 1080,
        "height": 1920,
        "fps": 30
    },
    "title": {
        "color": "#FFD400",
        "position": "top",
        "maxLines": 3,
        "fontWeight": 800,
        "fontSize": 64
    },
    "captions": {
        "color": "#FFFFFF",
        "position": "bottom-center",
        "maxWords": 3,
        "maxLines": 1,
        "outline": "#000000",
        "outlineWidth": 6,
        "fontSize": 64,
        "font": "Arial Black",
        "shadow": 2
    },
    "audio": {
        "sourceVideoAudio": False
    }
}


def _template_to_response(template: Template) -> TemplateResponse:
    """Convert Template model to response, deserializing JSON config."""
    return TemplateResponse(
        id=template.id,
        name=template.name,
        version=template.version,
        description=template.description,
        aspect_ratio=template.aspect_ratio,
        resolution_width=template.resolution_width,
        resolution_height=template.resolution_height,
        fps=template.fps,
        config=json.loads(template.config) if isinstance(template.config, str) else template.config,
        is_default=template.is_default,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get("/", response_model=TemplateListResponse)
async def list_templates(db: Session = Depends(get_db)):
    templates = db.query(Template).order_by(Template.created_at.desc()).all()
    return TemplateListResponse(
        items=[_template_to_response(t) for t in templates],
        total=len(templates),
    )


@router.post("/", response_model=TemplateResponse)
async def create_template(req: TemplateCreate, db: Session = Depends(get_db)):
    template = Template(
        id=str(uuid.uuid4()),
        name=req.name,
        description=req.description,
        config=json.dumps(req.config),
    )
    db.add(template)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to create template")
        raise HTTPException(status_code=500, detail=f"Failed to create template: {e}")
    return _template_to_response(template)


@router.get("/defaults", response_model=TemplateResponse)
async def get_default_template(db: Session = Depends(get_db)):
    """Get the default Yellow Story template."""
    existing = db.query(Template).filter(Template.is_default == True).first()
    if existing:
        return _template_to_response(existing)

    # Return a virtual default template without creating a DB record
    return TemplateResponse(
        id="default",
        name="Yellow Story",
        version=1,
        description="Default template with yellow title and captions",
        config=DEFAULT_TEMPLATE_CONFIG,
        is_default=True,
    )


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str, db: Session = Depends(get_db)):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_to_response(template)


@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(template_id: str, req: TemplateUpdate, db: Session = Depends(get_db)):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    try:
        if req.name is not None:
            template.name = req.name
        if req.description is not None:
            template.description = req.description
        if req.config is not None:
            template.config = json.dumps(req.config)
            template.version += 1
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to update template")
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    return _template_to_response(template)


@router.delete("/{template_id}")
async def delete_template(template_id: str, db: Session = Depends(get_db)):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default template")

    try:
        db.delete(template)
        db.commit()
    except Exception as e:
        db.rollback()
        log.exception("Failed to delete template")
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    return {"deleted": True}
