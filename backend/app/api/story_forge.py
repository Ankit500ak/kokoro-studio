"""
Story Forge API
Endpoints for the 10-stage hooking story generation pipeline.
"""
import logging
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from ..services.auto_gen.story_forge import story_forge, PipelineResult
from ..services.theme_tracker import get_used_count, get_recent_themes, is_theme_used
from ..core.config import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/forge", tags=["story-forge"])


# ─────────────────────────────────────────────────────
# Request / Response schemas
# ─────────────────────────────────────────────────────

class StartPipelineRequest(BaseModel):
    theme: str = Field(..., min_length=2, max_length=200, description="Theme or topic for the story")
    target_duration: int = Field(default=120, ge=60, le=600, description="Target duration in seconds (default 2 minutes)")

class SelectHookRequest(BaseModel):
    session_id: str
    hook_id: str

class StageResponse(BaseModel):
    session_id: str
    current_stage: int
    completed_stages: list[int]
    error: Optional[str] = None

class ClassificationResponse(BaseModel):
    category: str
    sub_category: str
    tone: str
    target_audience: str
    lead_gender: str = "male"

class ColdHookResponse(BaseModel):
    id: str
    text: str
    hook_category: str
    psychological_trigger: str
    pattern_formula: str
    score: float
    selected: bool

class RetentionPlanResponse(BaseModel):
    hook_type: str
    placement: str
    timecode: str
    purpose: str

class BeatResponse(BaseModel):
    beat_number: int
    timecode_start: str
    timecode_end: str
    purpose: str
    content: str
    word_count: int
    emotion: str
    micro_hook: str

class FullResultResponse(BaseModel):
    session_id: str
    theme: str
    target_duration: int = 120
    classification: Optional[ClassificationResponse] = None
    cold_hooks: list[ColdHookResponse] = []
    selected_hook: Optional[ColdHookResponse] = None
    retention_plan: list[RetentionPlanResponse] = []
    architecture: list[BeatResponse] = []
    draft: str = ""
    hook_injected: str = ""
    retention_optimized: str = ""
    retention_notes: list[str] = []
    voice_polished: str = ""
    pause_map: list[dict] = []
    final_tightened: str = ""
    quality_score: float = 0
    quality_breakdown: dict = {}
    suggestions: list[str] = []
    final_script: str = ""
    word_count: int = 0
    estimated_duration: float = 0
    current_stage: int = 0
    completed_stages: list[int] = []
    errors: list[str] = []


def _result_to_response(result: PipelineResult) -> FullResultResponse:
    classification = None
    if result.classification:
        classification = ClassificationResponse(
            category=str(result.classification.category or "unknown"),
            sub_category=str(result.classification.sub_category or "general"),
            tone=str(result.classification.tone or "dramatic"),
            target_audience=str(result.classification.target_audience or "general"),
            lead_gender=str(getattr(result.classification, 'lead_gender', 'male') or "male"),
        )

    selected_hook = None
    if result.selected_hook:
        selected_hook = ColdHookResponse(
            id=result.selected_hook.id,
            text=result.selected_hook.text,
            hook_category=result.selected_hook.hook_category,
            psychological_trigger=result.selected_hook.psychological_trigger,
            pattern_formula=result.selected_hook.pattern_formula,
            score=result.selected_hook.score,
            selected=result.selected_hook.selected,
        )

    return FullResultResponse(
        session_id=result.session_id,
        theme=result.theme,
        target_duration=result.target_duration,
        classification=classification,
        cold_hooks=[
            ColdHookResponse(
                id=str(h.id), text=str(h.text), hook_category=str(h.hook_category),
                psychological_trigger=str(h.psychological_trigger),
                pattern_formula=str(h.pattern_formula),
                score=float(h.score), selected=bool(h.selected),
            )
            for h in result.cold_hooks
        ],
        selected_hook=selected_hook,
        retention_plan=[
            RetentionPlanResponse(
                hook_type=str(rp.hook_type), placement=str(rp.placement),
                timecode=str(rp.timecode), purpose=str(rp.purpose),
            )
            for rp in result.retention_plan
        ],
        architecture=[
            BeatResponse(
                beat_number=int(b.beat_number), timecode_start=str(b.timecode_start),
                timecode_end=str(b.timecode_end), purpose=str(b.purpose),
                content=str(b.content), word_count=int(b.word_count), emotion=str(b.emotion),
                micro_hook=str(b.micro_hook),
            )
            for b in result.architecture
        ],
        draft=result.draft,
        hook_injected=result.hook_injected,
        retention_optimized=result.retention_optimized,
        retention_notes=result.retention_notes,
        voice_polished=result.voice_polished,
        pause_map=result.pause_map,
        final_tightened=result.final_tightened,
        quality_score=result.quality_score,
        quality_breakdown=result.quality_breakdown,
        suggestions=result.suggestions,
        final_script=result.final_script,
        word_count=result.word_count,
        estimated_duration=result.estimated_duration,
        current_stage=result.current_stage,
        completed_stages=result.completed_stages,
        errors=result.errors,
    )


# ─────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────

@router.post("/start", response_model=StageResponse)
async def start_pipeline(req: StartPipelineRequest):
    """Stage 1: Classify story type and generate 5 cold open hooks."""
    try:
        result = story_forge.create_session(req.theme, target_duration=req.target_duration)
        result = await story_forge.stage_with_fallback(
            result.session_id,
            story_forge.stage_1_story_classification,
            "1_story_classification",
        )
        result = await story_forge.stage_with_fallback(
            result.session_id,
            story_forge.stage_2_cold_open_hook,
            "2_cold_open_hook",
        )
        return StageResponse(
            session_id=result.session_id,
            current_stage=result.current_stage,
            completed_stages=result.completed_stages,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        log.error(f"[StoryForge] Pipeline start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=FullResultResponse)
async def get_session(session_id: str):
    """Get full pipeline state for a session."""
    result = story_forge.get_session(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    return _result_to_response(result)


@router.post("/select-hook", response_model=StageResponse)
async def select_hook(req: SelectHookRequest):
    """Stages 3-4: Select a hook, plan retention hooks, build architecture."""
    try:
        result = await story_forge.stage_3_retention_hook_planning(req.session_id, req.hook_id)
        result = await story_forge.stage_4_story_architecture(req.session_id)
        return StageResponse(
            session_id=result.session_id,
            current_stage=result.current_stage,
            completed_stages=result.completed_stages,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"[StoryForge] Hook selection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-draft/{session_id}", response_model=StageResponse)
async def generate_draft(session_id: str):
    """Stages 5-6: Generate draft and inject micro-hooks."""
    try:
        result = await story_forge.stage_5_draft_generation(session_id)
        result = await story_forge.stage_6_micro_hook_injection(session_id)
        return StageResponse(
            session_id=result.session_id,
            current_stage=result.current_stage,
            completed_stages=result.completed_stages,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404 if "session not found" in str(e).lower() else 409,
            detail=str(e),
        )
    except Exception as e:
        log.error(f"[StoryForge] Draft generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retention-pass/{session_id}", response_model=StageResponse)
async def retention_pass(session_id: str):
    """Stages 7-8: Optimize for retention and polish for voice."""
    try:
        result = await story_forge.stage_7_retention_pass(session_id)
        result = await story_forge.stage_8_voice_rhythm(session_id)
        return StageResponse(
            session_id=result.session_id,
            current_stage=result.current_stage,
            completed_stages=result.completed_stages,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404 if "session not found" in str(e).lower() else 409,
            detail=str(e),
        )
    except Exception as e:
        log.error(f"[StoryForge] Retention pass failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quality-score/{session_id}", response_model=StageResponse)
async def quality_score(session_id: str):
    """Stages 9-10: Final polish and quality scoring."""
    try:
        result = await story_forge.stage_9_final_polish(session_id)
        result = await story_forge.stage_10_quality_scoring(session_id)
        return StageResponse(
            session_id=result.session_id,
            current_stage=result.current_stage,
            completed_stages=result.completed_stages,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404 if "session not found" in str(e).lower() else 409,
            detail=str(e),
        )
    except Exception as e:
        log.error(f"[StoryForge] Quality scoring failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-all", response_model=FullResultResponse)
async def run_full_pipeline(req: StartPipelineRequest):
    """Run all 10 stages in one click (full auto mode)."""
    try:
        result = await asyncio.wait_for(
            story_forge.run_full_pipeline(req.theme, target_duration=req.target_duration),
            timeout=settings.STORY_PIPELINE_TIMEOUT,
        )
        return _result_to_response(result)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except asyncio.TimeoutError:
        log.error("[StoryForge] Full pipeline exceeded %.0f seconds", settings.STORY_PIPELINE_TIMEOUT)
        raise HTTPException(status_code=504, detail="Story generation timed out")
    except Exception as e:
        log.error(f"[StoryForge] Full pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/used-themes")
async def list_used_themes(limit: int = 50):
    """List previously used themes to prevent repetition."""
    themes = get_recent_themes(limit=limit)
    return {
        "total": get_used_count(),
        "themes": themes,
    }


@router.post("/check-theme")
async def check_theme_duplicate(req: StartPipelineRequest):
    """Check if a theme has already been used."""
    used = is_theme_used(req.theme)
    return {
        "theme": req.theme,
        "is_used": used,
        "message": "This theme has been used before." if used else "Theme is available.",
    }
