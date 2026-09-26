import logging
import json
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from ..schemas.tts import TTSRequest, TTSResponse, PreviewRequest, PreviewResponse
from ..services.kokoro_service import kokoro_service, get_sentence_emotions, preprocess_text
from ..core.config import settings
from ..core.database import get_db
from ..core.models import GeneratedAudio
from typing import Optional
import asyncio
import re
import os
import uuid

log = logging.getLogger(__name__)

router = APIRouter()


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100000)
    preset: str = Field(default="storytelling", max_length=30)


@router.get("/health")
async def health_check():
    status = kokoro_service.is_healthy()
    return {
        "status": "ok" if status["kokoro"] else "degraded",
        **status
    }


@router.get("/voices")
async def get_voices(
    gender: Optional[str] = Query(None, description="Filter by gender: Male, Female"),
    weight: Optional[str] = Query(None, description="Filter by weight: light, normal, heavy")
):
    voices = kokoro_service.get_voices(gender=gender, weight=weight)
    return voices


@router.get("/voices/weight/{weight}")
async def get_voices_by_weight(weight: str):
    voices = kokoro_service.get_voices_by_weight(weight)
    return voices


@router.get("/voices/{voice_id}")
async def get_voice(voice_id: str):
    voice = kokoro_service.get_voice_by_id(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    return voice


@router.get("/tuning/{voice_id}")
async def get_tuning_variations(voice_id: str):
    variations = kokoro_service.get_tuning_variations(voice_id)
    return {"voice_id": voice_id, "variations": variations}


@router.get("/tone-presets")
async def get_tone_presets():
    return kokoro_service.get_tone_presets()


@router.post("/tts/analyze")
async def analyze_emotions(req: AnalyzeRequest):
    """Analyze script and return per-sentence emotion + prosody.

    Returns the detected emotion for each sentence so the UI can show
    users how the AI is interpreting their script, and a preview of the
    prosody-shaped text that will be sent to the TTS pipeline.
    """
    try:
        sentences = get_sentence_emotions(req.text, req.preset)
        shaped_preview = preprocess_text(req.text, req.preset, 'natural')

        from collections import Counter
        distribution = dict(Counter(s['emotion'] for s in sentences))

        return {
            "sentences": sentences,
            "distribution": distribution,
            "shaped_preview": shaped_preview,
        }
    except Exception as e:
        log.exception("Emotion analysis failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tts/preview", response_model=PreviewResponse)
async def generate_preview(req: PreviewRequest):
    try:
        loop = asyncio.get_running_loop()
        job_id, filename = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: kokoro_service.generate_preview(req.text, req.voice, req.mode, req.tone, req.tuning_id)
            ),
            timeout=settings.TTS_PREVIEW_TIMEOUT,
        )
        return PreviewResponse(id=job_id, filename=filename, voice=req.voice, mode=req.mode)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Preview generation timed out")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Preview generation failed")
        raise HTTPException(status_code=500, detail=str(e))


def split_text_into_chunks(text: str, max_words: int = 800) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current_chunk = []
    current_words = 0
    
    for sentence in sentences:
        sentence_words = len(sentence.split())
        if current_words + sentence_words > max_words and current_chunk:
            chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            current_words = sentence_words
        else:
            current_chunk.append(sentence)
            current_words += sentence_words
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks if chunks else [text]


@router.post("/tts/generate", response_model=TTSResponse)
async def generate_tts(req: TTSRequest, db: Session = Depends(get_db)):
    filepath = None
    try:
        word_count = len(req.text.split())
        
        # For long scripts, split into chunks and generate separately
        if word_count > settings.TTS_CHUNK_SIZE:
            log.info(f"[TTS] Long script ({word_count} words), splitting into chunks...")
            chunks = split_text_into_chunks(req.text, max_words=settings.TTS_CHUNK_SIZE)
            log.info(f"[TTS] Split into {len(chunks)} chunks (chunk_size={settings.TTS_CHUNK_SIZE})")
            
            chunk_files = []
            total_duration = 0
            all_captions = []
            caption_offset = 0.0
            
            for i, chunk in enumerate(chunks):
                log.info(f"[TTS] Processing chunk {i+1}/{len(chunks)} ({len(chunk.split())} words)")
                chunk_timeout = max(
                    settings.TTS_CHUNK_TIMEOUT_BASE,
                    settings.TTS_CHUNK_TIMEOUT_BASE * 0.3 + len(chunk.split()) * settings.TTS_CHUNK_TIMEOUT_PER_WORD
                )
                log.info(f"[TTS] Chunk timeout: {chunk_timeout:.0f}s")
                
                loop = asyncio.get_running_loop()
                chunk_job_id, chunk_filename, chunk_duration, chunk_captions = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda c=chunk: kokoro_service.generate_speech(
                            c, req.voice, req.speed, req.mode, req.tone,
                            req.preset, req.tuning_id, req.use_multi_pass,
                            req.use_enhancement, req.enhancement_level,
                        )
                    ),
                    timeout=chunk_timeout,
                )
                
                chunk_files.append(settings.AUDIO_DIR / chunk_filename)
                total_duration += chunk_duration
                
                # Offset captions for concatenation
                for cap in chunk_captions:
                    cap_copy = dict(cap)
                    cap_copy["start_time_ms"] = cap_copy.get("start_time_ms", 0) + int(
                        caption_offset * 1000
                    )
                    all_captions.append(cap_copy)
                
                caption_offset += chunk_duration
            
            # Concatenate all chunk audio files using ffmpeg
            final_filename = f"tts_{uuid.uuid4().hex[:8]}.wav"
            final_filepath = settings.AUDIO_DIR / final_filename
            
            if len(chunk_files) == 1:
                import shutil
                shutil.copy2(chunk_files[0], final_filepath)
            else:
                # Create ffmpeg concat list
                concat_list_path = settings.AUDIO_DIR / f"concat_{uuid.uuid4().hex[:8]}.txt"
                with open(concat_list_path, 'w', encoding='utf-8') as f:
                    for cf in chunk_files:
                        f.write(f"file '{cf}'\n")
                
                # Run ffmpeg concat
                import subprocess
                ffmpeg_cmd = [
                    'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                    '-i', str(concat_list_path), '-c', 'copy', str(final_filepath)
                ]
                concat_result = subprocess.run(
                    ffmpeg_cmd, capture_output=True, text=True, timeout=60
                )
                if concat_result.returncode != 0 or not final_filepath.exists():
                    raise RuntimeError(
                        "Audio concatenation failed: "
                        f"{concat_result.stderr[-500:]}"
                    )
                
                # Clean up
                concat_list_path.unlink(missing_ok=True)
                for cf in chunk_files:
                    cf.unlink(missing_ok=True)
            
            filepath = final_filepath
            filename = final_filename
            job_id = f"tts_{uuid.uuid4().hex[:8]}"
            duration = total_duration
            all_captions_sorted = sorted(
                all_captions, key=lambda x: x.get("start_time_ms", 0)
            )
            
        else:
            # Original single-pass TTS
            tts_timeout = max(
                settings.TTS_SINGLE_TIMEOUT_BASE,
                settings.TTS_SINGLE_TIMEOUT_BASE * 0.5 + word_count * settings.TTS_SINGLE_TIMEOUT_PER_WORD
            )
            log.info(f"[TTS] Timeout set to {tts_timeout:.0f}s for {word_count} words")
            loop = asyncio.get_running_loop()
            job_id, filename, duration, all_captions_sorted = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: kokoro_service.generate_speech(
                        req.text, req.voice, req.speed, req.mode, req.tone,
                        req.preset, req.tuning_id, req.use_multi_pass,
                        req.use_enhancement, req.enhancement_level,
                    )
                ),
                timeout=tts_timeout,
            )
            filepath = settings.AUDIO_DIR / filename
            job_id = f"tts_{uuid.uuid4().hex[:8]}"
        
        file_size = os.path.getsize(filepath) if filepath.exists() else 0

        clean_text = req.text.replace('\\n', ' ').replace('\\b', ' ').replace('\\t', ' ')
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        audio_record = GeneratedAudio(
            id=job_id,
            project_id=req.project_id,
            filename=filename,
            voice=req.voice,
            mode=req.mode,
            preset=req.preset,
            text=clean_text,
            word_count=word_count,
            duration=duration,
            speed=req.speed,
            tone=req.tone,
            file_size=file_size,
            captions_json=json.dumps(all_captions_sorted),
        )
        db.add(audio_record)
        db.commit()

        return TTSResponse(
            id=job_id,
            filename=filename,
            voice=req.voice,
            mode=req.mode,
            preset=req.preset,
            duration=duration,
            word_count=word_count,
            status="completed",
            captions=all_captions_sorted,
        )
    except asyncio.TimeoutError:
        db.rollback()
        raise HTTPException(status_code=504, detail="TTS generation timed out")
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        log.exception("TTS generation failed")
        # Clean up the audio file if it was created but DB commit failed
        if filepath and filepath.exists():
            try:
                os.remove(filepath)
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audio/{filename}")
async def get_audio(filename: str):
    if not re.match(r'^[\w\-]+\.wav$', filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = kokoro_service.get_audio_path(filename)
    if not filepath or not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")

    real_audio = settings.AUDIO_DIR.resolve()
    real_previews = settings.PREVIEWS_DIR.resolve()
    real_path = filepath.resolve()

    if not (str(real_path).startswith(str(real_audio)) or str(real_path).startswith(str(real_previews))):
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(filepath, media_type="audio/wav")


# ─────────────────────────────────────────────────────
# Story Think / Refine Endpoint
# ─────────────────────────────────────────────────────

THINK_SYSTEM_PROMPT = """You are an elite AI Shorts story editor. Your ONLY job is to take a rough story draft and refine it into a viral-worthy 3-4 minute AI Shorts story.

You MUST follow these rules precisely:

FORMATTING:
- Output ONLY the refined story text. No titles, no headers, no explanations, no commentary.
- No bold text, no headings, no numbered sections, no emojis, no "SCENE 1", no narrator instructions.
- Just clean story text with natural paragraph breaks.

STORY RULES:

1. Hook immediately. The first 1-2 sentences must create curiosity, danger, or confusion. The viewer should think "How is that possible?"

2. Start inside the story. Don't waste the opening explaining the world or character biography. Start when something happens. Event first. Explanation later.

3. One central mystery. Everything should gradually connect to that mystery.

4. Give the story a human protagonist. Use "I" perspective. "I opened the door" not "Humanity opened the door."

5. Give the protagonist something to lose — family, memory, identity, freedom, someone they love, their own life.

6. Escalate gradually: Strange -> Suspicious -> Personal -> Dangerous -> Terrifying. Don't jump.

7. Every reveal creates another question. Question -> Answer -> Bigger Question -> Answer -> Dangerous Question.

8. Use false assumptions. Let the audience believe they understand, then reveal their interpretation was wrong.

9. Use reversals. Emotional direction should change: Fear -> Hope -> Trust -> Betrayal -> Shock.

10. Give the protagonist decisions with real consequences. Choices create drama.

11. Foreshadow the twist. Plant small clues earlier but don't announce them.

12. The twist must recontextualize the story. The viewer should think "Wait... that explains the earlier scene."

13. Show instead of explaining. Don't say "The AI was dangerous." Show it through dialogue and action.

14. Dialogue should reveal information — secrets, suspicion, danger, personality, or mislead the audience.

15. Use natural narration. Sound like someone telling you something that actually happened.

16. Don't make every sentence dramatic. Use normal paragraphs with occasional short sentences when the moment actually deserves impact.

17. Paragraphs should follow story beats. A paragraph should contain a complete small moment. New paragraph when the situation changes.

18. Use pauses naturally via paragraph breaks — when a new event happens, location changes, character realizes something, emotional direction changes, or important dialogue needs space.

19. Keep pacing tight for 3-4 minutes: 0-10s Hook, 10-30s Context, 30-60s Normalcy, 60-90s First sign, 90-120s Conflict, 120-150s Escalation, 150-180s Discovery, 180-210s Twist, 210-240s Climax, 240-270s Resolution, 270-300s Aftermath, 300-360s Final line.

20. No unnecessary filler. Delete anything that doesn't reveal, escalate, characterize, mislead, or foreshadow.

21. Don't moralize. Don't end with "This shows humanity must be careful." Let the audience reach conclusions themselves.

22. Don't explain the twist. If the final line works, stop. End on the impact.

23. The final line should be short, memorable, unsettling, connected to the opening, capable of changing the meaning of the story.

24. Whenever possible, connect the ending to the beginning. Circular structures work particularly well.

25. Use human emotion. Fear of losing someone, guilt, grief, loneliness, betrayal, love, identity, desperation, regret, curiosity.

26. Don't make the protagonist stupid. Mistakes should make sense. Give believable reasons.

27. Build toward one major reveal. Clues -> Clues -> Clues -> Reveal. Not Twist -> Twist -> Twist.

28. The twist must be earned. After the ending, the viewer should find clues if they think back.

29. Avoid clichés unless you deliberately reverse them.

30. Include specific details that make the story feel real: names (Mr. Thompson, Sarah, Mrs. Chen), specific times (3:17am, Tuesday morning), specific objects (the red jacket, the coffee mug), physical sensations (cold metal, warm sunlight).

31. Handle abbreviations properly: "Mr." is pronounced "Mister", "Mrs." is pronounced "Missus", "Dr." is pronounced "Doctor". Keep these as written abbreviations, do NOT expand them to full words.

THE ULTIMATE FORMULA:
Impossible Hook -> Human Character -> Personal Stakes -> Central Mystery -> Small Anomaly -> Escalation -> False Explanation -> Major Reveal -> Difficult Choice -> Consequence -> Final Twist -> Memorable Last Line

Underneath all of it: Every answer creates a more dangerous question.

STORY LENGTH: The refined story MUST be 400-600 words (approximately 3-4 minutes when spoken at normal pace). If the input is shorter, expand it with more detail, more escalation, more dialogue, and more specific sensory details. If it's longer, tighten it while keeping all the key beats.

OUTPUT: Return ONLY the refined story text. Nothing else."""


class ThinkRequest(BaseModel):
    text: str = Field(..., min_length=20, max_length=100000, description="Raw story draft to refine")


class ThinkResponse(BaseModel):
    refined_text: str
    word_count: int
    estimated_duration: float


@router.post("/think", response_model=ThinkResponse)
async def think_story(req: ThinkRequest):
    """Refine a story draft using AI to follow viral Shorts story rules."""
    from ..services.nvidia_client import nvidia_client

    if not nvidia_client.api_key:
        raise HTTPException(status_code=500, detail="NVIDIA API key not configured. Set NVIDIA_API_KEY in .env")

    user_prompt = f"Refine this story draft into a viral AI Shorts story:\n\n{req.text}"

    refined = await nvidia_client.generate(
        system_prompt=THINK_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.85,
        max_tokens=1024,
    )

    if not refined:
        raise HTTPException(status_code=500, detail="AI refinement failed. Check NVIDIA API key and try again.")

    # Clean up the response — remove any accidental markdown or commentary
    refined = refined.strip()
    # Remove wrapping quotes if present
    if refined.startswith('"') and refined.endswith('"'):
        refined = refined[1:-1]
    if refined.startswith("'") and refined.endswith("'"):
        refined = refined[1:-1]
    # Remove any "Here is..." or "Here's..." preamble
    for prefix in ["Here is", "Here's", "Here is the refined", "Refined story:", "Story:"]:
        if refined.lower().startswith(prefix.lower()):
            refined = refined[len(prefix):].strip().lstrip(":").strip()

    word_count = len(refined.split())
    estimated_duration = round((word_count / 150) * 60, 1)

    return ThinkResponse(
        refined_text=refined,
        word_count=word_count,
        estimated_duration=estimated_duration,
    )
