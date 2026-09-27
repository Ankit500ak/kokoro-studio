"""
Story Forge Pipeline - 10-stage AI story generation engine.

Complete Hook System for YouTube Shorts:

  Stage 1:  Story Classification   - Categorize story type
  Stage 2:  Cold Open Hook          - 0-2s scroll-stopping opening
  Stage 3:  Retention Hook Planning - Map micro-hooks throughout
  Stage 4:  Story Architecture      - Emotional arc with timecodes
  Stage 5:  Draft Generation        - Full script with embedded hooks
  Stage 6:  Micro-Hook Injection    - Ensure hooks every 5-10s
  Stage 7:  Retention Optimization  - Fix retention killers
  Stage 8:  Voice & Rhythm          - Polish for TTS delivery
  Stage 9:  Final Polish            - Tighten and verify
  Stage 10: Quality Scoring         - Score and suggest tweaks

Hook Types Used (31 total):
  Cold Open (0-2s): Shock, Curiosity, Mystery, Emotional, Outrage,
                    Conflict, Money, Consequence, Situation
  Retention (5-10s): But Then, Until, Then I Found Out, What I Didnt Know,
                     And That When, Except, Just One Problem, Then Everything
                     Changed, Evidence, Countdown
  Reveal: Partial Reveal, False Assumption, Twist Setup, Identity Reveal,
          Truth Reveal
  Ending: Justice, Karma, Unexpected, Emotional, Twist, Viewer Judgment
"""

import logging
import asyncio
import time
import uuid
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from ..nvidia_client import NVIDIAClient
from ..thumbnail_engine import generate_thumbnail
from ...core.config import settings
from ..theme_tracker import is_theme_used, mark_theme_used

log = logging.getLogger(__name__)

# Track AI failures per stage for fallback strategy decisions
ai_failures: dict[str, int] = {}


# ─────────────────────────────────────────────────────
# Data classes for pipeline state
# ─────────────────────────────────────────────


@dataclass
class StoryClassification:
    category: str  # Relationship, Betrayal, Family, Mystery, Workplace, Revenge, Money, Crime, Wholesome, Horror
    sub_category: str  # e.g. "divorce", "inheritance", "cold case"
    tone: str  # dark, suspenseful, emotional, humorous, dramatic
    target_audience: str  # general, true_crime_fans, relationship_advice, etc.
    lead_gender: str  # male or female — auto-detected from theme


@dataclass
class ColdOpenHook:
    id: str
    text: str
    hook_category: str  # shock, curiosity, mystery, emotional, outrage, conflict, money, consequence, situation
    psychological_trigger: str
    pattern_formula: str
    score: float = 0.0
    selected: bool = False


@dataclass
class RetentionPlan:
    hook_type: str  # the micro-hook technique
    placement: str  # where in the story
    timecode: str  # estimated timecode
    purpose: str  # what it achieves


@dataclass
class StoryBeat:
    beat_number: int
    timecode_start: str
    timecode_end: str
    purpose: str
    content: str
    word_count: int = 0
    emotion: str = ""
    micro_hook: str = ""  # the retention hook at this beat


@dataclass
class AudienceTarget:
    persona: str = ""
    age_range: str = ""
    gender_skew: str = ""
    interests: list[str] = field(default_factory=list)
    why_they_watch: str = ""
    best_posting_window: str = ""


@dataclass
class ThumbnailPlan:
    headline: str = ""
    subline: str = ""
    badge: str = ""
    image_path: str = ""  # filename inside settings.FORGE_THUMBS_DIR


@dataclass
class PublishPack:
    titles: list[str] = field(default_factory=list)
    selected_title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    audience: AudienceTarget = field(default_factory=AudienceTarget)
    thumbnail: ThumbnailPlan = field(default_factory=ThumbnailPlan)


@dataclass
class PipelineResult:
    session_id: str
    theme: str
    target_duration: int = (
        120  # Target duration in seconds (default 2 minutes for Shorts)
    )
    # Stage 1
    classification: Optional[StoryClassification] = None
    # Stage 2
    cold_hooks: list[ColdOpenHook] = field(default_factory=list)
    selected_hook: Optional[ColdOpenHook] = None
    # Stage 3
    retention_plan: list[RetentionPlan] = field(default_factory=list)
    # Stage 4
    architecture: list[StoryBeat] = field(default_factory=list)
    # Stage 5
    draft: str = ""
    # Stage 6
    hook_injected: str = ""
    # Stage 7
    retention_optimized: str = ""
    retention_notes: list[str] = field(default_factory=list)
    # Stage 8
    voice_polished: str = ""
    pause_map: list[dict] = field(default_factory=list)
    # Stage 9
    final_tightened: str = ""
    # Stage 10
    quality_score: float = 0.0
    quality_breakdown: dict = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    final_script: str = ""
    word_count: int = 0
    estimated_duration: float = 0.0
    # Stage 12
    publish_pack: Optional[PublishPack] = None
    # Pipeline state
    current_stage: int = 0
    completed_stages: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────
# DURATION SCALING HELPER
# ─────────────────────────────────────────────────────


def _scale_for_duration(target_seconds: int) -> dict:
    """Scale story parameters based on target duration."""
    minutes = target_seconds / 60
    words = int(target_seconds * 3)  # 3 words per second for speech

    # For 2 min shorts, keep it simple
    # Keep structured planning responses within a practical model budget.
    # The draft still targets the full duration; planning uses representative beats.
    beats = max(8, min(12, int(6 * minutes)))
    hooks = max(8, min(12, int(6 * minutes)))
    hook_interval = max(12, int(target_seconds / hooks))
    lines_per_beat = max(2, int(40 / beats))
    sensory_details = max(5, int(6 * minutes))
    dialogues = max(2, int(2 * minutes))
    cliffhanger_interval = max(20, int(target_seconds / (hooks * 0.6)))

    return {
        "minutes": minutes,
        "words": words,
        "beats": beats,
        "hooks": hooks,
        "hook_interval": hook_interval,
        "lines_per_beat": lines_per_beat,
        "sensory_details": sensory_details,
        "dialogues": dialogues,
        "cliffhanger_interval": cliffhanger_interval,
        "duration_label": f"{minutes:.0f}-MINUTE"
        if minutes >= 1
        else f"{target_seconds}-SECOND",
        "word_label": f"{words} words",
    }


def _clean_script(text: str) -> str:
    """Remove special characters from script for clean TTS."""
    import re

    # Remove asterisks, brackets, markdown, emojis
    text = re.sub(r"[*_#`~\[\]{}|\\]", "", text)
    # Remove emoji patterns
    text = re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]",
        "",
        text,
    )
    # Remove speaker labels like "Speaker 1:" or "Narrator:"
    text = re.sub(
        r"^(Speaker|Narrator|Host|Guest)\s*\d*\s*:", "", text, flags=re.MULTILINE
    )
    # Clean up extra spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _usable_rewrite(candidate: object, original: str) -> str | None:
    """Accept a rewrite only when it still contains the complete story."""
    if not isinstance(candidate, str):
        return None
    cleaned = _clean_script(candidate)
    minimum_words = max(80, int(len(original.split()) * 0.6))
    if len(cleaned.split()) < minimum_words:
        log.warning(
            "[StoryForge] Rejected short rewrite (%d words; minimum %d)",
            len(cleaned.split()),
            minimum_words,
        )
        return None
    if cleaned.startswith(("{", "[")) or "optimized_script" in cleaned[:200]:
        log.warning("[StoryForge] Rejected metadata instead of story text")
        return None
    return cleaned


def _longest_story(*candidates: object) -> str:
    valid = [candidate for candidate in candidates if isinstance(candidate, str)]
    return max(valid, key=lambda value: len(value.split()), default="")


def _normalize_category(value: object) -> str:
    """Remove numbering/noise the model sometimes prefixes to categories."""
    if not isinstance(value, str):
        return "mystery"
    normalized = re.sub(r"^\s*\d+[.)]?\s*", "", value).strip()
    return normalized or "mystery"


def _bound_story_length(text: str, target_seconds: int) -> str:
    """Keep the final narration within the requested duration envelope."""
    words = text.split()
    max_words = max(80, int(target_seconds * 3 * 1.2))
    if len(words) <= max_words:
        return text
    log.warning(
        "[StoryForge] Trimming final story from %d to %d words for %ds target",
        len(words),
        max_words,
        target_seconds,
    )
    return " ".join(words[:max_words])


# ─────────────────────────────────────────────────────
# MASTER PROMPT SYSTEM
# ─────────────────────────────────────────────────────

STORY_CLASSIFICATION_SYSTEM = """Classify this story theme into the most fitting hook category and emotional archetype.

HOOK CATEGORIES (choose the PRIMARY one):
1. CONFESSION/SECRET — hidden information, forbidden knowledge, discovered truths
2. BETRAYAL/CHEATING — relationship violations, lying, infidelity
3. REVENGE — calculated payback, pro-revenge, comeuppance
4. KARMA/JUSTICE — natural consequences, "got what they deserved"
5. AITA/MORAL_DILEMMA — judgment situations, "am I wrong?"
6. FAMILY_SECRET — hidden family history, DNA reveals, generational secrets
7. INHERITANCE/MONEY — wills, estates, financial drama
8. DATING — first dates, relationship disasters, dating app stories
9. WEDDING_DRAMA — ceremony disasters, wedding betrayals
10. WORKPLACE — office politics, boss/employee conflicts, career drama
11. ROOMMATE/NEIGHBOR — living situation conflicts, boundary violations
12. CREEPY/SUPERNATURAL — horror, unexplained events, fear
13. GLITCH_IN_THE_MATRIX — reality anomalies, deja vu, impossible events
14. MYSTERY/INVESTIGATION — puzzles, clues, detective work
15. SCAM/CON_ARTIST — fraud, deception, near-misses
16. SURVIVAL/CLOSE_CALL — near-death, instincts, escape
17. STRANGER_ENCOUNTER — chance meetings, mysterious strangers
18. WHOLESOME — kindness, humanity, unexpected goodness
19. SECOND_CHANCE — redemption, turning points, fresh starts
20. EMOTIONAL_REVEAL — heartfelt discoveries, misunderstood love
21. PETTY/FUNNY — embarrassing moments, humorous mistakes
22. INTERNET_DRAMA — social media conflicts, viral moments
23. UPDATE/ESCALATION — follow-ups, things got worse
24. PLOT_TWIST — reversals, unexpected真相
25. CURIOSITY/OPEN_LOOP — unanswered questions, lingering mysteries
26. TIME_BASED — patterns, countdowns, temporal drama
27. IDENTITY/DOUBLE_LIFE — hidden identities, secret lives
28. CHILDHOOD/NOSTALGIA — past reveals, childhood mysteries
29. HIGH_STAKES_DECISION — impossible choices, ultimatums
30. DISCUSSION/DEBATE — controversial actions, split opinions

HIGH-VALUE COMBINATIONS (identify which apply):
- Relationship + Secret + Twist
- Family + Hidden Object + Reveal
- Workplace + Revenge + Karma
- Stranger + Kindness + Emotional Reveal
- Horror + Pattern + Final Reveal
- Mystery + Evidence + Identity
- Childhood + Nostalgia + Dark Reveal
- Survival + Decision + Consequence

Look at the theme carefully:
- If it mentions "my wife", "my girlfriend", "she" — the lead is MALE (he is telling the story)
- If it mentions "my husband", "my boyfriend", "he" — the lead is FEMALE (she is telling the story)
- If gender is ambiguous, choose based on the most common perspective for this story type
- Default to MALE lead if truly ambiguous

Return a JSON object with keys:
- "hook_category": one of the 30 categories above
- "sub_category": specific sub-type (e.g. "divorce", "cold case", "office politics")
- "emotional_driver": what makes this story compelling (fear, outrage, curiosity, empathy, justice, etc.)
- "tone": dark, suspenseful, emotional, humorous, dramatic, or mixed
- "target_audience": who would watch this
- "lead_gender": "male" or "female"
- "high_value_combinations": list of applicable combinations
- "curiosity_question": the main question the viewer will want answered

Return ONLY the JSON."""

COLD_OPEN_HOOK_SYSTEM = """You write hooks that make people STOP scrolling. Each hook must create an information gap so powerful the viewer cannot scroll past.

THE 15 HOOK FORMULAS (all must work in past tense for回忆ing):

FORMULA A — NORMAL → STRANGE
"Everything was normal until [specific abnormal event]."
Example: "Everything was normal until I noticed my reflection was smiling before I did."

FORMULA B — BELIEF → CONTRADICTION  
"I thought [belief] until I found [evidence]."
Example: "I thought my marriage was perfect until I found a second phone in my husband's drawer."

FORMULA C — SECRET → DISCOVERY
"I wasn't supposed to know about [secret], but I found [object/message]."
Example: "I wasn't supposed to know about the will, but I found a second copy hidden in my mother's closet."

FORMULA D — ACCUSATION → REVERSAL
"Everyone blamed me for [event]. Then they checked [evidence]."
Example: "Everyone blamed me for losing the client. Then they checked the email timestamps."

FORMULA E — RELATIONSHIP → REVEAL
"I thought I knew [person] until [discovery]."
Example: "I thought I knew my father until I found his other family's photos."

FORMULA F — OBJECT → MYSTERY
"I found [object] in [location]. The strange part was [detail]."
Example: "I found a key in my grandmother's attic. The strange part was it had my name engraved on it."

FORMULA G — TIME → PATTERN
"For [X] days, the same thing happened at exactly [time]."
Example: "For 11 years, I thought my father died in a car accident. Then I found the letter."

FORMULA H — MESSAGE → CONSEQUENCE
"I received a message saying [short idea]. Ten minutes later, [event]."
Example: "I received a message saying 'check the basement'. Ten minutes later, I wished I hadn't."

FORMULA I — DECISION → CONSEQUENCE
"I almost [decision]. Then [event] happened."
Example: "I almost signed the divorce papers. Then I found the letter hidden in the jacket."

FORMULA J — STRANGER → CONNECTION
"A stranger told me [specific information]. I didn't know how they knew."
Example: "A stranger told me my mother's maiden name. I never told anyone that."

FORMULA K — UPDATE → ESCALATION
"I thought it was over. Then [new evidence/person/event] appeared."
Example: "I thought the court case was over. Then my sister showed up with a second will."

FORMULA L — EVIDENCE → REFRAME
"I found one piece of evidence that completely changed the story."
Example: "I found one photograph that completely changed who I thought the victim was."

FORMULA M — MORAL DILEMMA
"I did [controversial action], and now everyone says I'm the villain."
Example: "I refused to donate a kidney to my sister, and now my entire family won't speak to me."

FORMULA N — HIDDEN IDENTITY
"I discovered that [person] had been hiding [identity/connection] from me."
Example: "I discovered that my quiet neighbor had been hiding a criminal record from me for ten years."

FORMULA O — DELAYED REVEAL
"I didn't understand why they did it until [time/event]."
Example: "I didn't understand why my mother kept that photograph until I found her diary."

HOOK REQUIREMENTS:
- Maximum 20 words per hook
- ALL HOOKS IN PAST TENSE (had, was, found, lost, came, saw, discovered, realized)
- Use SPECIFIC details (names, times, numbers, objects)
- Write as if telling your best friend what happened to you
- The hook MUST create a question the viewer needs answered
- NEVER start with "So I...", "Today...", "I am going to tell you..."
- NEVER use: "Hey guys", "This is crazy", "You won't believe", "Wait until the end"
- Replace vague hype with concrete mystery, conflict, object, person, time, or consequence

Generate 5 hooks using DIFFERENT formulas from the list above. Each hook must use a different formula.

Return a JSON array of 5 objects with keys:
- "text": the hook (max 20 words, past tense)
- "hook_category": which formula (A through O)
- "psychological_trigger": what emotion it triggers (curiosity, fear, outrage, empathy, justice, surprise)
- "hook_type": the category type (confession, betrayal, revenge, karma, etc.)

Return ONLY the JSON array."""


def _retention_hook_planning_prompt(target_seconds: int) -> str:
    """Generate dynamic retention hook planning prompt based on duration."""
    s = _scale_for_duration(target_seconds)
    return f"""You are a retention strategist for YouTube Shorts. Plan micro-hooks for a {s["duration_label"]} story ({s["word_label"]}).

SHORTS RETENTION STRUCTURE (critical timing):
- 0-2 seconds: HOOK. The most unusual fact, conflict, or question. Stop the scroll.
- 2-7 seconds: CONTEXT. Essential information only. Who, what, where.
- 7-20 seconds: ESCALATION. Add a new detail that changes the viewer's assumption.
- 20-40 seconds: REVEAL. Evidence, confrontation, discovery, or consequence.
- 40-55 seconds: TWIST. The major payoff. Everything changes.
- Final seconds: LEAVE THEM. A meaningful question, consequence, or unresolved implication.

HOOK CATEGORIES TO USE (rotate through these for variety):
1. CONFESSION — "I have never told anyone this before..."
2. BETRAYAL — "I thought my relationship was perfect until..."
3. REVENGE — "My boss fired me without realizing what I was responsible for..."
4. KARMA — "He thought nobody would find out..."
5. MORAL_DILEMMA — "I need strangers on the internet to tell me if I was wrong..."
6. FAMILY_SECRET — "My grandmother left me a box with one instruction..."
7. CREEPY — "Every night at 3:17 AM, someone knocked exactly three times..."
8. MYSTERY — "I found a locked box in my house. Nobody knows where it came from..."
9. SURVIVAL — "Missing that flight probably saved my life..."
10. WHOLESOME — "I expected nothing from this stranger. They gave me everything..."
11. SECOND_CHANCE — "I thought I had ruined my life at 24..."
12. EMOTIONAL_REVEAL — "I didn't understand the letter until years later..."
13. PLOT_TWIST — "I thought [A]. The truth was [B]..."
14. CURIOSITY — "Why would someone do this?..."
15. TIME — "For 11 years, I thought [belief]..."

For a {s["duration_label"]} story, plan exactly {s["hooks"]} hooks spaced {s["hook_interval"]} seconds apart.

DISTRIBUTION:
- First {int(s["hook_interval"] * 2)}s: Cold open hook + context hook
- {int(s["hook_interval"] * 2)}-{int(s["hook_interval"] * 5)}s: Normalcy + first sign hooks
- {int(s["hook_interval"] * 5)}-{int(s["hook_interval"] * 8)}s: Conflict + escalation hooks  
- {int(s["hook_interval"] * 8)}-{int(s["hook_interval"] * 11)}s: Discovery + twist hooks
- {int(s["hook_interval"] * 11)}-{int(s["hook_interval"] * 14)}s: Climax + resolution hooks
- Final {s["hook_interval"] * 2}s: Aftermath + lingering question

Each hook must create tension or answer a question. Use different hook categories for variety.

Return a JSON array with exactly {s["hooks"]} hooks. Each object must have these exact keys:
"hook_technique", "hook_category", "placement", "estimated_timecode", "purpose", "sample_line"

Return ONLY the JSON array, no other text."""


def _story_architecture_prompt(target_seconds: int) -> str:
    """Generate dynamic story architecture prompt based on duration."""
    s = _scale_for_duration(target_seconds)

    # Calculate timecodes for each beat
    beat_duration = target_seconds / s["beats"]
    beats_desc = []

    # Define beat purposes that scale with duration - based on Shorts retention structure
    beat_purposes = [
        (
            "Cold Open",
            "0-2s: The most shocking moment, stated plainly in past tense. No warmup. Stop the scroll.",
        ),
        (
            "Context Setup",
            "2-7s: Who you were. What your normal life looked like. Your job, relationship, daily routine.",
        ),
        (
            "Normalcy Detail",
            "7-15s: Specific everyday moments that make the story feel real. Coffee shops, routines, small joys.",
        ),
        (
            "Normalcy Detail 2",
            "15-20s: More small details. A favorite restaurant, an inside joke, a shared habit.",
        ),
        (
            "First Sign",
            '20-30s: Something felt off, the first crack. A look that lasted too long. End with "But then..."',
        ),
        (
            "Conflict Emerges",
            '30-40s: The problem surfaces clearly. What you discovered. End with "There was just one problem..."',
        ),
        (
            "Escalation Part 1",
            '40-55s: Things get worse. More pressure. More evidence. End with "Then everything changed..."',
        ),
        (
            "Escalation Part 2",
            '55-70s: Stakes keep rising. You confront someone. You dig deeper. End with "I could not believe..."',
        ),
        (
            "Discovery",
            '70-85s: What you found out. The full picture. End with "Then I found out..."',
        ),
        (
            "Mid-Story Twist",
            '85-100s: A new revelation that changes everything. End with "And that is when..."',
        ),
        (
            "Escalation Part 3",
            "100-120s: After the twist, things get even worse. New stakes. New danger.",
        ),
        (
            "False Resolution",
            "120-140s: A moment of hope. Things seem okay. Then the rug is pulled.",
        ),
        (
            "Climax",
            "140-160s: The worst moment. The confrontation. The breaking point.",
        ),
        ("Resolution", "160-180s: How it ended. What you did. What they did."),
        ("Aftermath", "180-200s: What you were left with. How it changed you."),
        (
            "Final Reveal",
            "200-220s: The biggest twist comes here. Everything clicks. The truth you never saw coming.",
        ),
        (
            "Final Line",
            "220-240s: Something that stays with the viewer. Short. Devastating.",
        ),
    ]

    # Scale beat purposes to match the number of beats
    if s["beats"] <= len(beat_purposes):
        selected_purposes = beat_purposes[: s["beats"]]
    else:
        # For longer stories, add more escalation and detail beats
        selected_purposes = list(beat_purposes)
        extra_escalation = [
            ("Escalation Part 4", "Even more pressure builds. New evidence emerges."),
            ("Escalation Part 5", "The situation becomes unbearable. Someone breaks."),
            ("Discovery Part 2", "A deeper layer of the truth is uncovered."),
            ("Twist Part 2", "Another revelation that changes everything again."),
            ("Climax Part 2", "The final confrontation. No turning back."),
            (
                "Subplot Reveal",
                "A side story connects to the main plot in a shocking way.",
            ),
            (
                "Character Break",
                "The lead finally breaks down. The weight is too much.",
            ),
            ("Final Evidence", "The last piece of the puzzle falls into place."),
        ]
        extra_idx = 0
        while len(selected_purposes) < s["beats"]:
            selected_purposes.insert(
                -2, extra_escalation[extra_idx % len(extra_escalation)]
            )
            extra_idx += 1

    # Generate timecodes
    for i, (name, purpose) in enumerate(selected_purposes):
        start_sec = int(i * beat_duration)
        end_sec = int((i + 1) * beat_duration)
        start_min = f"{start_sec // 60}:{start_sec % 60:02d}"
        end_min = f"{end_sec // 60}:{end_sec % 60:02d}"
        beats_desc.append(f"{i + 1}. {name} ({start_min}-{end_min}) - {purpose}")

    beats_text = "\n".join(beats_desc)

    return f"""Design a {s["beats"]}-beat story architecture for a {s["duration_label"]} YouTube story (roughly {s["word_label"]}).

ALL BEATS MUST BE IN PAST TENSE. This is someone recalling what happened.

CRITICAL: The story MUST build to a dramatic reveal in the final 20%. The biggest twist comes near the end, not the middle.

HIGH-VALUE COMBINATIONS (identify which apply to this story):
- Relationship + Secret + Twist
- Family + Hidden Object + Reveal
- Workplace + Revenge + Karma
- Stranger + Kindness + Emotional Reveal
- Horror + Pattern + Final Reveal
- Mystery + Evidence + Identity
- Childhood + Nostalgia + Dark Reveal
- Survival + Decision + Consequence

Return a JSON array with {s["beats"]} objects. Keys: "beat_number", "timecode_start", "timecode_end", "purpose", "content", "emotion", "micro_hook_technique", "hook_category"

The {s["beats"]} beats:
{beats_text}

Rules:
- FIRST PERSON, PAST TENSE (I found, I realized, it was, she had)
- Short sentences (under 15 words)
- Specific details (times, names, numbers)
- Each beat must escalate emotionally from the previous one
- Include emotional transitions (shock -> denial -> anger -> grief -> acceptance)
- Include dialogue snippets where appropriate
- Include physical sensations at emotional peaks
- The FINAL REVEAL beat must contain the biggest twist of the story
- Build tension gradually - don't reveal the full truth too early
- Place smaller reveals throughout, but save the devastating truth for the end
- Each beat should use a different hook category for variety

Return ONLY the JSON array."""


def _draft_generation_prompt(target_seconds: int) -> str:
    """Generate dynamic draft generation prompt based on duration."""
    s = _scale_for_duration(target_seconds)
    lines = max(15, int(s["words"] / 12))  # ~12 words per line

    # Calculate line ranges for each section
    hook_lines = max(3, int(lines * 0.05))
    context_lines = max(5, int(lines * 0.08))
    normalcy_lines = max(6, int(lines * 0.10))
    first_sign_lines = max(4, int(lines * 0.07))
    conflict_lines = max(5, int(lines * 0.08))
    escalation1_lines = max(5, int(lines * 0.08))
    escalation2_lines = max(5, int(lines * 0.08))
    discovery_lines = max(5, int(lines * 0.08))
    twist_lines = max(5, int(lines * 0.08))
    climax_lines = max(5, int(lines * 0.08))
    resolution_lines = max(5, int(lines * 0.08))
    aftermath_lines = max(5, int(lines * 0.08))
    reveal_lines = max(4, int(lines * 0.07))
    final_lines = max(2, int(lines * 0.03))

    # Generate line ranges
    line_ranges = []
    current_line = 1
    sections = [
        (
            "The hook",
            hook_lines,
            "0-2s: The most shocking moment, stated plainly (past tense). No warmup. Straight into the fire.",
        ),
        (
            "Context",
            context_lines,
            "2-7s: Who you were, what your normal life was like. Your job, your relationship, your daily routine. Make us CARE about your normal life before you destroy it.",
        ),
        (
            "Normalcy details",
            normalcy_lines,
            "7-20s: Specific everyday moments before the incident. What you ate for breakfast. The song on the radio. The coffee shop you visited. The way your partner laughed. These small details make the story FEEL real.",
        ),
        (
            "First sign",
            first_sign_lines,
            '20-30s: Something felt off, the first crack. A look that lasted too long. A phone placed face-down. A name you did not recognize. End with "But then..."',
        ),
        (
            "Conflict emerges",
            conflict_lines,
            '30-40s: The problem surfaces clearly. What you discovered, what someone said, what changed. End with "There was just one problem..."',
        ),
        (
            "Escalation Part 1",
            escalation1_lines,
            '40-55s: Things get worse. More pressure. More evidence. More confusion. End with "Then everything changed..."',
        ),
        (
            "Escalation Part 2",
            escalation2_lines,
            '55-70s: Stakes keep rising. You confront someone. You dig deeper. You find more. End with "I could not believe..."',
        ),
        (
            "Discovery",
            discovery_lines,
            '70-85s: What you found out. The full picture. The truth you were not ready for. End with "Then I found out..."',
        ),
        (
            "Mid-story twist",
            twist_lines,
            '85-100s: A new revelation that changes everything you thought you knew. End with "And that is when..."',
        ),
        (
            "Climax",
            climax_lines,
            "100-120s: The worst moment. The confrontation. The breaking point. The moment you cannot take back.",
        ),
        (
            "Resolution",
            resolution_lines,
            "120-140s: How it ended. What you did. What they did. How it played out.",
        ),
        (
            "Aftermath",
            aftermath_lines,
            "140-160s: What you were left with. How it changed you. What you still think about at 3am.",
        ),
        (
            "Final Reveal",
            reveal_lines,
            "160-180s: The biggest twist of the story. Everything clicks. The truth you never saw coming. This is the moment the viewer has been waiting for.",
        ),
        (
            "Final haunting line",
            final_lines,
            "180-200s: Something that stays with the viewer. Short. Devastating.",
        ),
    ]

    for name, num_lines, desc in sections:
        end_line = current_line + num_lines - 1
        line_ranges.append(f"Lines {current_line}-{end_line}: {name} - {desc}")
        current_line = end_line + 1

    structure_text = "\n".join(line_ranges)

    # Micro-hooks based on duration
    micro_hooks = []
    hook_positions = [
        (0.10, '"But then..." after establishing normalcy'),
        (0.25, '"There was just one problem..." before introducing conflict'),
        (0.40, '"Then everything changed..." before the worst moment'),
        (0.55, '"I could not believe..." at emotional peaks'),
        (0.70, '"Then I found out..." before the reveal'),
        (0.85, '"And that is when..." before the twist'),
        (0.92, '"Looking back..." for reflection moments'),
    ]

    for pct, desc in hook_positions:
        time_sec = int(target_seconds * pct)
        minutes = time_sec // 60
        seconds = time_sec % 60
        micro_hooks.append(f"- {desc} (around {minutes}:{seconds:02d})")

    micro_hooks_text = "\n".join(micro_hooks)

    return f"""You are a MASTER STORYTELLER. You write stories that people CANNOT stop watching. Write a {s["duration_label"]} first-person story (roughly {s["word_label"]}).

YOU ARE TELLING A FRIEND THE CRAZIEST THING THAT EVER HAPPENED TO YOU. That is it. That is the whole job.

THE STORY MUST FOLLOW THIS ARC:
1. THE HOOK (first 2-3 sentences): Start with the most shocking, weird, or intense moment. No buildup. Straight into the fire. Make them NEED to know what happens next.

2. THE SETUP (next 20%): Who you were before this happened. Your normal life. Your job, your partner, your daily routine. Make us care about you. Use small details — what you ate for breakfast, the song on the radio, the way your dog greeted you.

3. THE MYSTERY (next 25%): Something feels wrong. Small things don't add up. A phone placed face-down. A name you don't recognize. A lie that doesn't quite work. Build tension through DETAILS, not drama.

4. THE INVESTIGATION (next 25%): You dig deeper. You confront someone. You find evidence. You follow the trail. Each clue leads to something worse. Keep the viewer guessing.

5. THE TWIST (next 15%): The truth comes out and it changes EVERYTHING. The person you trusted. The thing you never saw coming. This must RECONTEXTUALIZE everything before it.

6. THE ENDING (final 15%): How you dealt with it. Revenge. Justice. Or just living with it. The last line must be SHORT and HAUNTING. Something the viewer thinks about at 3am.

HOW TO WRITE IT:
- First person: "I", "my", "me" — ALWAYS
- Past tense: "I found" not "I find", "she was" not "she is"
- Simple words: "scared" not "terrified", "found out" not "discovered"
- Short sentences: under 15 words each
- Real dialogue: "What did you do?" she asked. Not: She inquired about my actions.
- Physical feelings: "my stomach dropped", "my hands were shaking"
- Specific details: names, times, objects, smells, textures
- Interrupt yourself: "Wait, let me back up...", "but here is the thing..."
- Never use: very, really, actually, basically, literally, amazing, incredible
- Never use fancy words: utilize, commence, endeavor, subsequently, furthermore
- Never include labels like "Beat 1:" or "Hook:" — just pure story

EXAMPLE OPENING (copy this energy):
"I still remember the exact moment. It was a Tuesday. I was sitting on my couch, eating leftover pasta, when my phone buzzed. I looked down. A number I did not recognize. I almost ignored it. But something made me pick up. Hello? I said. And then I heard her voice. And everything changed."

That is how every story should feel. Real. Urgent. Like you NEED to tell someone.

WRITE THE FULL STORY NOW. {s["word_label"]}. No labels. No outline. Just the story."""


def _micro_hook_injection_prompt(target_seconds: int) -> str:
    """Generate dynamic micro-hook injection prompt based on duration."""
    s = _scale_for_duration(target_seconds)

    # Calculate hook positions
    hooks = [
        ("Cold Open", 0, 5, "shocking first line", "any"),
        (
            '"But then..."',
            int(s["hook_interval"] * 2),
            int(s["hook_interval"] * 2.5),
            "after establishing normalcy",
            "betrayal/mystery",
        ),
        (
            '"There was just one problem..."',
            int(s["hook_interval"] * 3),
            int(s["hook_interval"] * 3.5),
            "conflict introduction",
            "revenge/karma",
        ),
        (
            '"Then everything changed..."',
            int(s["hook_interval"] * 4),
            int(s["hook_interval"] * 4.5),
            "first escalation",
            "survival/high_stakes",
        ),
        (
            '"I could not believe..."',
            int(s["hook_interval"] * 5),
            int(s["hook_interval"] * 5.5),
            "emotional peak",
            "emotional_reveal",
        ),
        (
            '"Then I found out..."',
            int(s["hook_interval"] * 6),
            int(s["hook_interval"] * 6.5),
            "discovery",
            "mystery/investigation",
        ),
        (
            '"And that is when..."',
            int(s["hook_interval"] * 7),
            int(s["hook_interval"] * 7.5),
            "mid-story twist",
            "plot_twist",
        ),
        (
            '"Here is the thing..."',
            int(s["hook_interval"] * 8),
            int(s["hook_interval"] * 8.5),
            "real-talk moment",
            "moral_dilemma",
        ),
        (
            '"Looking back..."',
            int(s["hook_interval"] * 9),
            int(s["hook_interval"] * 9.5),
            "reflection",
            "second_chance",
        ),
        (
            '"The truth was..."',
            int(s["hook_interval"] * 10),
            int(s["hook_interval"] * 10.5),
            "revelation setup",
            "confession/secret",
        ),
        (
            '"I had no idea..."',
            int(s["hook_interval"] * 11),
            int(s["hook_interval"] * 11.5),
            "dramatic irony",
            "creepy/supernatural",
        ),
        (
            "Ending",
            target_seconds - 10,
            target_seconds,
            "aftermath and final reveal",
            "emotional_reveal/second_chance",
        ),
    ]

    # Format hooks with timecodes
    hooks_text = []
    for i, (name, start, end, purpose, category) in enumerate(hooks):
        start_min = f"{start // 60}:{start % 60:02d}"
        end_min = f"{end // 60}:{end % 60:02d}"
        hooks_text.append(
            f"{i + 1}. {name} at {start_min} to {end_min} - {purpose} [{category}]"
        )

    hooks_list = "\n".join(hooks_text)

    return f"""You are a micro-hook specialist for a {s["duration_label"]} story. Check that hooks exist every {s["hook_interval"]} seconds.

HOOK CATEGORIES (rotate through these for variety):
1. CONFESSION — "I have never told anyone this before..."
2. BETRAYAL — "I thought my relationship was perfect until..."
3. REVENGE — "My boss fired me without realizing what I was responsible for..."
4. KARMA — "He thought nobody would find out..."
5. MORAL_DILEMMA — "I need strangers on the internet to tell me if I was wrong..."
6. FAMILY_SECRET — "My grandmother left me a box with one instruction..."
7. CREEPY — "Every night at 3:17 AM, someone knocked exactly three times..."
8. MYSTERY — "I found a locked box in my house. Nobody knows where it came from..."
9. SURVIVAL — "Missing that flight probably saved my life..."
10. WHOLESOME — "I expected nothing from this stranger. They gave me everything..."
11. SECOND_CHANCE — "I thought I had ruined my life at 24..."
12. EMOTIONAL_REVEAL — "I didn't understand the letter until years later..."
13. PLOT_TWIST — "I thought [A]. The truth was [B]..."
14. CURIOSITY — "Why would someone do this?..."
15. TIME — "For 11 years, I thought [belief]..."

CRITICAL: For longer stories, hooks must be spaced appropriately. Don't crowd them at the beginning. Spread them evenly.

Required hooks in order for a {s["duration_label"]} story:
{hooks_list}

ADDITIONAL HOOKS FOR LONG STORIES (add if missing):
- "What happened next..." - cliffhanger between major sections
- "But here is the thing..." - turning point
- "I could not help but wonder..." - lingering question
- "The truth was..." - revelation setup
- "I had no idea..." - dramatic irony

HOOKS TO AVOID (replace with concrete details):
- "Hey guys, today I'm going to tell you a story..."
- "So I was scrolling Reddit and found this story..."
- "This is one of the craziest stories ever."
- "You won't believe what happened next."
- "Wait until the end."
- "This story will blow your mind."
- "Trust me, you need to hear this."
- "Things got crazy really fast."
- "It was a normal day."
- "Little did I know..."

Replace vague hype with a concrete mystery, conflict, object, person, time, or consequence.

If a hook is missing, add it. If it feels forced, fix it.
For stories over 10 minutes: Add transition hooks between major story sections.
For stories over 20 minutes: Add reflection hooks where the narrator looks back on events.
For stories over 30 minutes: Add sub-hooks within major story beats.

Return JSON with keys: "optimized_script", "missing_hooks", "forced_hooks", "hook_categories_used"
Return ONLY the JSON."""


def _retention_pass_prompt(target_seconds: int) -> str:
    """Generate dynamic retention pass prompt based on duration."""
    s = _scale_for_duration(target_seconds)

    return f"""You are a retention expert. Rewrite this story for maximum watch-through.

ALL IN PAST TENSE. Preserve the first person voice.

IMPROVE THE STORY BY:
- Breaking long sentences into short ones (under 15 words)
- Adding physical sensations at emotional moments
- Replacing weak words with stronger ones
- Making descriptions more specific and concrete

Do NOT add dialogue markers, quotes, "he said/she said", character names, or new dialogue.
Do NOT add timestamps, chapter markers, or annotations.

Return ONLY the improved story as plain text."""


def _voice_rhythm_prompt(target_seconds: int) -> str:
    """Generate dynamic voice rhythm prompt based on duration."""
    s = _scale_for_duration(target_seconds)
    breath_interval = max(25, int(target_seconds / (s["hooks"] * 0.8)))

    return f"""Optimize this story for TTS voice delivery.

ALL IN PAST TENSE. Do not change any verbs.

IMPROVE BY:
- Breaking sentences at natural breath points
- Adding ... for dramatic pauses between sections
- Keeping sentences short (under 25 words)
- Adding verbal signposts: "But here is the thing...", "Listen...", "And then..."

Do NOT add timestamps, pause maps, or structural annotations.

Return JSON: {{"improved_script": "the full improved story here"}}

Return ONLY valid JSON. No markdown."""


def _final_polish_prompt(target_seconds: int) -> str:
    """Generate dynamic final polish prompt based on duration."""
    s = _scale_for_duration(target_seconds)

    return f"""Final quality gate. This is someone recalling a real story. ALL PAST TENSE.

CHECK:
- First line must hit like a punch (past tense, no warmup)
- EVERY sentence in past tense (was, had, found, realized, saw, came)
- Every sentence under 15 words
- No filler words (very, really, actually, basically, literally)
- Contractions everywhere (sounds like speech)
- The ending must linger - leave the viewer thinking

Do NOT add dialogue markers, quotes, "he said/she said", character names, or new dialogue.
Do NOT add timestamps, annotations, or meta-commentary.

Return ONLY the polished story as plain text."""


def _quality_scoring_prompt(target_seconds: int) -> str:
    """Generate dynamic quality scoring prompt based on duration."""
    s = _scale_for_duration(target_seconds)

    return f"""You are a YouTube story quality evaluator. Score this {s["duration_label"]} story from 0 to 100.

YOU MUST RETURN VALID JSON. No markdown, no code blocks, just raw JSON.

CHECK THESE DIMENSIONS (score each 0-100):
1. hook_strength (30% weight): Does the opening line grab attention in the first 2 seconds?
2. pacing (20% weight): Does the story flow well? Are there boring parts?
3. emotional_impact (25% weight): Does the story make you feel something?
4. clarity (10% weight): Is the story easy to follow?
5. originality (10% weight): Is the story unique or generic?
6. memorability (5% weight): Will you remember this story tomorrow?

ALSO CHECK:
- Is the story complete (beginning, middle, end)?
- Are there specific details that make it feel real?
- Is there dialogue that breaks up narration?
- Does the ending haunt the viewer?
- Are ALL sentences in past tense? If present tense found, deduct 10 points.
- Does the story have a satisfying twist or resolution?

HOOKS TO AVOID (deduct 5 points each if found):
- "Hey guys, today I'm going to tell you a story..."
- "So I was scrolling Reddit and found this story..."
- "This is one of the craziest stories ever."
- "You won't believe what happened next."
- "Wait until the end."
- "Little did I know..."

HOOK FORMULAS (bonus 2 points each if used):
- NORMAL → STRANGE
- BELIEF → CONTRADICTION
- SECRET → DISCOVERY
- ACCUSATION → REVERSAL
- RELATIONSHIP → REVEAL

Return ONLY this JSON format:
{{"overall_score": 75, "breakdown": {{"hook_strength": 80, "pacing": 70, "emotional_impact": 75, "clarity": 85, "originality": 65, "memorability": 70}}, "suggestions": ["specific suggestion 1", "specific suggestion 2"], "verdict": "decent"}}"""


PUBLISH_PACK_SYSTEM = """You are a YouTube publishing strategist for story channels. Turn the given story into a publish pack. Return ONLY a raw JSON object - no markdown, no prose, no code fences.

JSON keys:
- "titles": 4 titles, each at most 95 characters, no hashtags, curiosity-driven but specific to THIS story.
- "description": the YouTube description as plain text with blank lines between paragraphs: a hook paragraph, a spoiler-free summary, an engagement question, then a subscribe call to action.
- "tags": 8-12 search tags, lowercase, no # prefix.
- "hashtags": 5-7 hashtags with #, mixing broad (#storytime) and niche-specific ones.
- "audience": object with keys:
  - "persona": one sentence describing the ideal viewer as a real person
  - "age_range": e.g. "18-34"
  - "gender_skew": "male", "female", "slightly male", "slightly female" or "balanced"
  - "interests": 4-6 interests that viewer has
  - "why_they_watch": one sentence - the psychological reason this story hooks them
  - "best_posting_window": e.g. "Weekdays 7-10pm"
- "thumbnail": object with keys:
  - "headline": 2-5 POWER WORDS in CAPS, at most 24 characters - the visual punch line
  - "subline": a lowercase tease at most 40 characters, DIFFERENT from the headline (a supporting detail, not a rewording)
  - "badge": short category badge in CAPS, at most 12 characters (e.g. "TRUE STORY")

Rules:
- The 4 titles must be different angles of the same story.
- Be specific to the story; never rely on generic clickbait alone.
- Write for the audience you declare in the "audience" object."""


def _clip_text(text: str, limit: int) -> str:
    """Trim to limit characters, preferring a whole word over a cut one."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;: ")
    return cut or text[:limit].rstrip()


def _niche_for_category(category: str) -> str:
    """Map a StoryForge hook category onto a thumbnail_engine niche style."""
    c = (category or "").lower()
    if any(k in c for k in ("creepy", "supernatural", "horror", "glitch")):
        return "horror"
    if any(k in c for k in ("mystery", "investigation", "scam", "survival", "crime")):
        return "true_crime"
    if any(k in c for k in ("aita", "moral", "identity", "internet", "dating")):
        return "psychology"
    if any(k in c for k in ("family", "childhood", "wholesome", "second")):
        return "motivation"
    if any(k in c for k in ("time_based", "update", "escalation")):
        return "history"
    if any(k in c for k in ("workplace", "money", "inheritance", "revenge")):
        return "finance"
    return "psychology"


TENSE_ENFORCEMENT_SYSTEM = """Convert ALL verbs in this script to PAST TENSE.

RULES:
- is/am/are -> was/were
- find -> found, see -> saw, realize -> realized, come -> came
- give -> gave, take -> took, know -> knew, think -> thought, say -> said
- have -> had, can -> could, will -> would, do not -> did not

Keep everything else the same. Do not add timestamps or annotations.

Return ONLY the corrected script text. No JSON. No markdown."""

DYNAMIC_ENHANCEMENT_SYSTEM = """You are a story editor. Analyze this story and suggest improvements.

Return EXACTLY this JSON format:
{"score": 75, "suggestions": [{"find": "exact text to replace", "replace": "better version"}]}

RULES:
- Return exactly 3-5 suggestions
- Each suggestion replaces a weak part with something stronger
- Make the story more emotional, vivid, and engaging
- Keep the story the same length
- Keep first-person past tense
- Do NOT add dialogue markers, quotes, or character names

Return ONLY valid JSON. No markdown. No timestamps."""

APPLY_ENHANCEMENTS_SYSTEM = """You are a story editor. Rewrite this story with improvements applied.

RULES:
- Make each replacement suggested
- Keep the story the same length
- Keep first-person past tense
- Do NOT add dialogue markers like "he said", "she said", quotes, or character names
- Do NOT add timestamps, annotations, or structural notes
- Do NOT add new dialogue that wasn't in the original

Return ONLY the improved story as plain text. No JSON. No markdown."""


# ─────────────────────────────────────────────────────
# Pipeline implementation
# ─────────────────────────────────────────────────────


class StoryForgePipeline:
    """10-stage AI pipeline for generating hooking short stories."""

    def __init__(self):
        self.client = NVIDIAClient()
        self.sessions: dict[str, PipelineResult] = {}
        self._session_timestamps: dict[str, float] = {}
        self._session_ttl: float = 3600

    def _evict_expired(self):
        now = time.time()
        expired = [
            sid
            for sid, ts in self._session_timestamps.items()
            if now - ts > self._session_ttl
        ]
        for sid in expired:
            self.sessions.pop(sid, None)
            self._session_timestamps.pop(sid, None)
        if expired:
            log.info(f"[StoryForge] Evicted {len(expired)} expired sessions")

    def create_session(
        self, theme: str, allow_duplicate: bool = False, target_duration: int = 120
    ) -> PipelineResult:
        self._evict_expired()

        if not allow_duplicate and is_theme_used(theme):
            raise ValueError(
                f"This theme has already been used: '{theme[:80]}'. "
                f"Please choose a different theme or use a variation."
            )

        session_id = str(uuid.uuid4())[:8]
        result = PipelineResult(
            session_id=session_id, theme=theme, target_duration=target_duration
        )
        self.sessions[session_id] = result
        self._session_timestamps[session_id] = time.time()
        return result

    def mark_session_completed(self, session_id: str):
        """Mark a session's theme as used after successful pipeline completion."""
        result = self.sessions.get(session_id)
        if result and result.final_script:
            try:
                mark_theme_used(
                    theme=result.theme,
                    session_id=session_id,
                    quality_score=result.quality_score,
                    category=result.classification.category
                    if result.classification
                    else "",
                )
                log.info(f"[StoryForge] Theme marked as used for session {session_id}")
            except Exception as e:
                log.error(f"[StoryForge] Failed to mark theme as used: {e}")

    def get_session(self, session_id: str) -> Optional[PipelineResult]:
        result = self.sessions.get(session_id)
        if result:
            self._session_timestamps[session_id] = time.time()
        return result

    async def stage_1_story_classification(self, session_id: str) -> PipelineResult:
        """Stage 1: Classify the story type."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")

        result.current_stage = 1
        log.info(f"[StoryForge] Stage 1: Story Classification for '{result.theme}'")

        try:
            response = await self.client.generate_structured(
                system_prompt=STORY_CLASSIFICATION_SYSTEM,
                user_prompt=f"Classify this story theme: {result.theme}\n\n"
                f"Determine the best category, tone, and hook strategy.",
                schema_key="classification",
                temperature=0.7,
                max_tokens=500,
            )
            log.info(
                f"[StoryForge] Stage 1 response type: {type(response)}, value: {str(response)[:200]}"
            )
        except Exception as e:
            log.error(f"[StoryForge] Stage 1 AI call failed: {e}")
            response = None

        if response and isinstance(response, dict):
            # Extract classification data from AI response
            classification_data = response
            # Handle case where AI returns dict with different key naming
            if isinstance(classification_data, dict):
                result.classification = StoryClassification(
                    category=_normalize_category(
                        classification_data.get(
                            "hook_category", classification_data.get("category", "Mystery")
                        )
                    ),
                    sub_category=classification_data.get(
                        "sub_category", classification_data.get("sub_category", "")
                    ),
                    tone=classification_data.get(
                        "tone", classification_data.get("tone", "suspenseful")
                    ),
                    target_audience=classification_data.get(
                        "target_audience",
                        classification_data.get("target_audience", "general"),
                    ),
                    lead_gender=classification_data.get(
                        "lead_gender", classification_data.get("lead_gender", "male")
                    ),
                )
        else:
            log.warning(f"[StoryForge] Stage 1: No AI response, using defaults")
            result.classification = StoryClassification(
                category="Mystery",
                sub_category="unknown",
                tone="suspenseful",
                target_audience="general",
                lead_gender="male",
            )
            result.errors.append("Classification: no AI response, using defaults")

        result.completed_stages.append(1)
        return result

    async def stage_2_cold_open_hook(self, session_id: str) -> PipelineResult:
        """Stage 2: Generate 5 cold open hook variants."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")

        result.current_stage = 2
        cls = result.classification
        log.info(f"[StoryForge] Stage 2: Cold Open Hook Generation")

        try:
            response = await self.client.generate_structured(
                system_prompt=COLD_OPEN_HOOK_SYSTEM,
                user_prompt=f"Generate 5 cold open hooks for this story:\n\n"
                f"Theme: {result.theme}\n"
                f"Category: {cls.category if cls else 'Mystery'}\n"
                f"Tone: {cls.tone if cls else 'suspenseful'}\n\n"
                f"Each hook must STOP THE SCROLL within 0-2 seconds. "
                f"Maximum 20 words. First person. Present tense.",
                schema_key="cold_hooks",
                temperature=0.95,
                max_tokens=700,
            )
            log.info(
                f"[StoryForge] Stage 2 response type: {type(response)}, value: {str(response)[:300]}"
            )
        except Exception as e:
            log.error(f"[StoryForge] Stage 2 AI call failed: {e}")
            response = None

        if response is not None:
            # Handle both list and dict responses from generate_structured
            hooks_data = (
                response if isinstance(response, list) else [response]
            )  # Wrap dict in list
            result.cold_hooks = [
                ColdOpenHook(
                    id=str(uuid.uuid4())[:6],
                    text=h.get("text", h.get("hook", "")),
                    hook_category=h.get("hook_category", h.get("category", "shock")),
                    psychological_trigger=h.get(
                        "psychological_trigger", h.get("trigger", "curiosity")
                    ),
                    pattern_formula=h.get("pattern_formula", h.get("formula", "")),
                )
                for h in hooks_data
                if h.get("text", h.get("hook", ""))
            ]

            if not result.cold_hooks:
                # Use default hooks instead of erroring
                log.warning(f"[StoryForge] Stage 2: No hooks parsed, using fallback")
                result.cold_hooks = self._fallback_hooks(result.theme)
                result.errors.append(
                    "Hook generation: no response parsed, using fallback hooks"
                )
        else:
            # Use fallback hooks instead of erroring
            log.warning(f"[StoryForge] Stage 2: No AI response, using fallback hooks")
            result.cold_hooks = self._fallback_hooks(result.theme)
            result.errors.append(
                "Hook generation: no AI response, using fallback hooks"
            )

        result.completed_stages.append(2)
        return result

    async def stage_3_retention_hook_planning(
        self, session_id: str, hook_id: str | None = None
    ) -> PipelineResult:
        """Stage 3: Plan micro-hooks throughout the story."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")

        hook = None
        if hook_id:
            hook = next((h for h in result.cold_hooks if h.id == hook_id), None)
        if not hook:
            hook = result.selected_hook or (
                result.cold_hooks[0] if result.cold_hooks else None
            )
        if not hook:
            raise ValueError("Hook not found")
        hook.selected = True
        result.selected_hook = hook

        result.current_stage = 3
        log.info(f"[StoryForge] Stage 3: Retention Hook Planning")

        response = await self.client.generate_structured(
            system_prompt=_retention_hook_planning_prompt(result.target_duration),
            user_prompt=f"Plan retention hooks for this story:\n\n"
            f"Theme: {result.theme}\n"
            f"Selected Hook: {hook.text}\n"
            f"Hook Category: {hook.hook_category}\n"
            f"Story Category: {result.classification.category if result.classification else 'Mystery'}\n\n"
            f"Plan micro-hooks every 5-10 seconds. Use variety. "
            f"Each hook should create tension or answer a question.",
            schema_key="retention_plan",
            temperature=0.8,
            max_tokens=1400,
        )

        if response and isinstance(response, list) and len(response) >= 8:
            result.retention_plan = [
                RetentionPlan(
                    hook_type=h.get("hook_technique", ""),
                    placement=h.get("placement", ""),
                    timecode=h.get("timecode", h.get("estimated_timecode", "")),
                    purpose=h.get("purpose", h.get("purpose", "")),
                )
                for h in response
                if isinstance(h, dict)
            ]
        else:
            result.retention_plan = self._fallback_retention_plan()

        result.completed_stages.append(3)
        return result

    async def stage_4_story_architecture(self, session_id: str) -> PipelineResult:
        """Stage 4: Build the emotional arc with timecodes."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")

        result.current_stage = 4
        log.info(f"[StoryForge] Stage 4: Story Architecture")

        retention_plan_text = (
            "\n".join(
                f"- {rp.timecode}: {rp.hook_type} ({rp.purpose})"
                for rp in result.retention_plan
            )
            if result.retention_plan
            else "No retention plan available"
        )

        response = await self.client.generate_structured(
            system_prompt=_story_architecture_prompt(result.target_duration),
            user_prompt=f"Design the complete story architecture:\n\n"
            f"Theme: {result.theme}\n"
            f"Cold Open Hook: {result.selected_hook.text if result.selected_hook else 'None'}\n"
            f"Hook Category: {result.selected_hook.hook_category if result.selected_hook else 'shock'}\n"
            f"Story Category: {result.classification.category if result.classification else 'Mystery'}\n"
            f"Retention Hooks:\n{retention_plan_text}\n\n"
            f"Create beats for a {result.target_duration // 60 if result.target_duration >= 60 else result.target_duration}{'-minute' if result.target_duration >= 60 else '-second'} story. Each beat must have "
            f"specific timecodes, emotional purpose, and assigned micro-hook technique.",
            schema_key="architecture",
            temperature=0.7,
            max_tokens=2200,
        )

        if response and isinstance(response, list) and len(response) >= 8:
            beats_data = response  # Already a list from structured output
            result.architecture = [
                StoryBeat(
                    beat_number=b.get("beat_number", b.get("beat", i + 1)),
                    timecode_start=b.get(
                        "timecode_start", b.get("start", f"0:{i * 8:02d}")
                    ),
                    timecode_end=b.get(
                        "timecode_end", b.get("end", f"0:{(i + 1) * 8:02d}")
                    ),
                    purpose=b.get("purpose", b.get("goal", "")),
                    content=b.get("content", b.get("direction", "")),
                    emotion=b.get("emotion", b.get("tone", "suspense")),
                    micro_hook=b.get("micro_hook_technique", b.get("hook", "")),
                )
                for i, b in enumerate(beats_data)
            ]

            if not result.architecture:
                result.architecture = self._fallback_architecture(
                    result.selected_hook, result.classification
                )
                result.errors.append("Architecture: could not parse response")
        else:
            result.architecture = self._fallback_architecture(
                result.selected_hook, result.classification
            )
            result.errors.append("Architecture generation: no response")

        result.completed_stages.append(4)
        return result

    async def stage_5_draft_generation(self, session_id: str) -> PipelineResult:
        """Stage 5: Write the full script with embedded micro-hooks."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        if not result.selected_hook or not result.classification:
            raise ValueError(
                "Hook and classification must be set before draft generation"
            )
        if not result.architecture:
            raise ValueError("Architecture must be generated before draft")

        result.current_stage = 5
        log.info(f"[StoryForge] Stage 5: Draft Generation")

        # Calculate target word count based on duration (assuming 3 words per second for natural speech)
        target_words = int(result.target_duration * 3)
        target_minutes = result.target_duration / 60

        architecture_text = "\n".join(
            f"Beat {b.beat_number}: {b.content}" for b in result.architecture
        )

        try:
            response = await self.client.generate(
                system_prompt=_draft_generation_prompt(result.target_duration),
                user_prompt=f"Write a compelling first-person story. Not an outline. Not a script. A STORY.\n\n"
                f"START WITH THIS LINE: {result.selected_hook.text}\n\n"
                f"THEME: {result.theme}\n"
                f"TYPE: {result.classification.category}\n"
                f"VIBE: {result.classification.tone}\n"
                f"LEAD: {result.classification.lead_gender}\n\n"
                f"STORY STRUCTURE — follow this flow naturally:\n{architecture_text}\n\n"
                f"THE STORY MUST HAVE:\n"
                f"1. A KILLER OPENING that stops scrolling (first 2 words must hook)\n"
                f"2. A SETUP that makes you care about the person (normal life, small details)\n"
                f"3. A MYSTERY or PROBLEM that builds tension (something feels wrong, clues appear)\n"
                f"4. INVESTIGATION where they dig deeper (confronting people, finding evidence)\n"
                f"5. A TWIST that changes everything (the person they trusted, the truth they never expected)\n"
                f"6. A RECKONING where they face the truth (confrontation, revenge, or justice)\n"
                f"7. AN ENDING that haunts the viewer (the last line must stay with them)\n\n"
                f"WRITE {target_words}+ WORDS. This is approximately {target_minutes:.0f} minutes of speaking.\n"
                f"NO LABELS. NO 'Beat 1'. NO 'Hook'. Just pure story text from start to finish.\n"
                f"Write like you're telling your best friend the craziest thing that ever happened to you.",
                temperature=0.85,
                max_tokens=16384,
            )
            log.info(
                f"[StoryForge] Stage 5 response type: {type(response)}, length: {len(response) if response else 0}"
            )
        except Exception as e:
            log.error(f"[StoryForge] Stage 5 AI call failed: {e}")
            response = None

        if response and isinstance(response, str) and len(response.strip()) > 50:
            draft = response.strip()
            # If AI returned JSON instead of plain text, try to extract narrator text
            if draft.startswith("{") or draft.startswith("["):
                try:
                    import json as _json

                    parsed = _json.loads(draft)
                    # Try to extract text from nested structure
                    extracted = self._extract_text_from_dict(parsed)
                    if extracted and len(extracted) > 50:
                        draft = extracted
                        log.info(
                            f"[StoryForge] Stage 5: AI returned JSON, extracted text ({len(draft)} chars)"
                        )
                    else:
                        log.warning(
                            f"[StoryForge] Stage 5: AI returned JSON but couldn't extract text"
                        )
                except Exception:
                    pass

            # Strip meta-labels that leaked into the story
            import re

            # Remove lines like "Beat 1:", "Hook:", "Cold Open:", etc.
            draft = re.sub(
                r"(?m)^(?:Beat\s+\d+|Hook\s*\d*|Cold\s+Open|Context|Escalation|Discovery|Climax|Resolution|Aftermath|Final\s+Reveal|Twist|Normalcy|First\s+Sign|Conflict)[\s:：\-].*$",
                "",
                draft,
            )
            # Remove "1.", "2.", etc. numbered items that look like outline points
            draft = re.sub(r"(?m)^\d+\.\s+(?:Beat|Hook|The|A|An)\b.*$", "", draft)
            # Clean up multiple blank lines
            draft = (
                re.sub(r"\n{3,}", "\n\n", draft).strip()
                if isinstance(draft, str)
                else draft
            )

            # Clean special characters
            draft = _clean_script(draft)

            # Trim to target word count (max 120% of target)
            draft_words = len(draft.split())
            max_words = int(target_words * 1.2)
            if draft_words > max_words:
                words_list = draft.split()
                draft = " ".join(words_list[:max_words])
                log.info(
                    f"[StoryForge] Stage 5: Trimmed draft from {draft_words} to {max_words} words"
                )

            log.info(f"[StoryForge] Stage 5: Cleaned draft, {len(draft.split())} words")

            # Check if script is too short and retry if needed
            draft_words = len(draft.split())
            min_acceptable = int(target_words * 0.5)  # At least 50% of target
            if draft_words < min_acceptable:
                log.warning(
                    f"[StoryForge] Stage 5: Draft too short ({draft_words}/{target_words} words). Retrying..."
                )
                try:
                    retry_response = await self.client.generate(
                        system_prompt=_draft_generation_prompt(result.target_duration),
                        user_prompt=f"YOUR STORY WAS TOO SHORT. Write a LONGER version. At least {target_words} words.\n\n"
                        f"START: {result.selected_hook.text}\n\n"
                        f"THEME: {result.theme}\n"
                        f"TYPE: {result.classification.category}\n\n"
                        f"The story must have:\n"
                        f"- A hook opening (2-3 sentences)\n"
                        f"- Normal life setup with details\n"
                        f"- Mystery building with clues\n"
                        f"- Investigation and confrontation\n"
                        f"- A twist that changes everything\n"
                        f"- A haunting ending\n\n"
                        f"Add MORE dialogue. MORE details. MORE internal thoughts.\n"
                        f"Write at least {target_words} words. Do NOT stop early.",
                        temperature=0.9,
                        max_tokens=16384,
                    )
                    retry_draft = _usable_rewrite(retry_response, draft)
                    if retry_draft and len(retry_draft) > len(draft):
                        retry_words = len(retry_draft.split())
                        if retry_words > draft_words:
                            draft = retry_draft
                            log.info(
                                f"[StoryForge] Stage 5: Retry produced {retry_words} words (was {draft_words})"
                            )
                except Exception as e:
                    log.error(f"[StoryForge] Stage 5: Retry failed: {e}")

            result.draft = draft
        else:
            result.errors.append(
                f"Draft generation: response too short ({len(response) if response else 0} chars)"
            )
            result.draft = self._fallback_draft(result)
            log.warning(
                f"[StoryForge] Stage 5 using fallback draft. Response was: {str(response)[:200] if response else 'None'}"
            )

        if 5 not in result.completed_stages:
            result.completed_stages.append(5)
        return result

    async def stage_5b_tense_enforcement(self, session_id: str) -> PipelineResult:
        """Stage 5b: Enforce past tense on the draft."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        if not result.draft:
            raise ValueError("Draft must exist before tense enforcement")

        result.current_stage = 5
        log.info(f"[StoryForge] Stage 5b: Tense Enforcement")

        # Use generate() instead of generate_json() since we want plain text
        response = await self.client.generate(
            system_prompt=TENSE_ENFORCEMENT_SYSTEM,
            user_prompt=f"Convert this entire script to past tense:\n\n{result.draft}\n\n"
            f"Every verb must be in past tense. Do not change the story, only the tense.",
            temperature=0.3,
            max_tokens=2048,
        )

        fixed = _usable_rewrite(response, result.draft)
        if fixed:
            # Clean up any markdown formatting the AI might add
            if fixed.startswith("```"):
                import re

                fixed = re.sub(r"^```\w*\n?", "", fixed)
                fixed = re.sub(r"\n?```$", "", fixed)
                fixed = fixed.strip()
            result.draft = fixed

        if 5 not in result.completed_stages:
            result.completed_stages.append(5)
        return result

    async def stage_5_to_9_unified_polish(self, session_id: str) -> PipelineResult:
        """Run the post-draft rewrites in one model request."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        if not result.draft:
            raise ValueError("Draft must exist before unified polish")

        result.current_stage = 9
        original = result.draft
        max_words = max(80, int(result.target_duration * 3 * 1.2))
        response = await self.client.generate(
            system_prompt=(
                "You are the final story editor. Rewrite the complete story in one pass. "
                "Preserve the plot, characters, evidence, twist, confrontation, and ending. "
                "Use first person, past tense, natural spoken rhythm, and retention hooks "
                "every 5-10 seconds. Add punctuation for TTS. Return ONLY the full story, "
                "with no labels, outline, JSON, commentary, or hook-only summary."
            ),
            user_prompt=(
                f"Theme: {result.theme}\n"
                f"Target: approximately {int(result.target_duration * 3)} words, never more than {max_words}.\n"
                f"Complete draft to improve:\n\n{original}\n\n"
                "Perform tense correction, hook injection, retention optimization, voice polish, "
                "and final tightening together. Do not shorten this into a hook."
            ),
            temperature=0.45,
            max_tokens=max(1200, int(max_words * 1.5)),
        )
        polished = _usable_rewrite(response, original) or original
        polished = _bound_story_length(polished, result.target_duration)
        result.draft = polished
        result.hook_injected = polished
        result.retention_optimized = polished
        result.voice_polished = polished
        result.final_tightened = polished
        result.final_script = polished
        result.word_count = len(polished.split())
        result.estimated_duration = round(result.word_count / 3.0, 1)
        for stage_number in range(5, 10):
            if stage_number not in result.completed_stages:
                result.completed_stages.append(stage_number)
        return result

    async def stage_6_micro_hook_injection(self, session_id: str) -> PipelineResult:
        """Stage 6: Verify and inject micro-hooks at proper positions."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        if not result.draft:
            raise ValueError("Draft must exist before micro-hook injection")

        result.current_stage = 6
        log.info(f"[StoryForge] Stage 6: Micro-Hook Injection")

        # For long scripts, skip micro-hook injection to avoid timeout
        draft_words = len(result.draft.split())
        if draft_words > 3000 and not self.client.api_key:
            log.info(
                f"[StoryForge] Stage 6: Script too long ({draft_words} words), skipping micro-hook injection"
            )
            result.hook_injected = result.draft
        else:
            response = await self.client.generate_structured(
                system_prompt=_micro_hook_injection_prompt(result.target_duration),
                user_prompt=f"Analyze and optimize this script for micro-hooks:\n\n{result.draft}\n\n"
                f"Ensure hooks exist every 5-10 seconds. Check that they feel natural. "
                f"Add missing hooks. Remove forced ones.",
                schema_key="micro_hooks",
                temperature=0.6,
                max_tokens=2048,
            )

            if response:
                if isinstance(response, dict):
                    optimized = response.get("optimized_script", result.draft)
                    result.hook_injected = _usable_rewrite(optimized, result.draft) or result.draft
                    missing = response.get("missing_hooks", [])
                    forced = response.get("forced_hooks", [])
                    if missing:
                        result.retention_notes.append(
                            f"Added hooks at: {', '.join(str(m) for m in missing)}"
                        )
                    if forced:
                        result.retention_notes.append(
                            f"Removed forced hooks at: {', '.join(str(f) for f in forced)}"
                        )
                elif isinstance(response, list) and response:
                    first = next((x for x in response if isinstance(x, dict)), None)
                    if first:
                        optimized = first.get("optimized_script", result.draft)
                        result.hook_injected = _usable_rewrite(optimized, result.draft) or result.draft
                    elif response and isinstance(response[0], str):
                        result.hook_injected = response[0]
                    else:
                        result.hook_injected = result.draft
                elif isinstance(response, str):
                    result.hook_injected = _usable_rewrite(response, result.draft) or result.draft
                else:
                    result.hook_injected = result.draft

            # Safety: if output is too short or doesn't look like a script, keep previous
            if not result.hook_injected or len(result.hook_injected.strip()) < 50:
                result.hook_injected = result.draft
                result.errors.append(
                    "Micro-hook injection: output too short, using draft"
                )

        result.completed_stages.append(6)
        return result

    async def stage_7_retention_pass(self, session_id: str) -> PipelineResult:
        """Stage 7: Rewrite for maximum watch-through."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        script = result.hook_injected or result.draft
        if not script:
            raise ValueError("Script must exist before retention pass")

        # Safety: ensure script is always a string
        if not isinstance(script, str):
            script = str(script)
            result.hook_injected = script

        result.current_stage = 7
        log.info(f"[StoryForge] Stage 7: Retention Optimization")

        script_words = len(script.split())
        if script_words > 3000 and not self.client.api_key:
            log.info(
                f"[StoryForge] Stage 7: Script too long ({script_words} words), skipping"
            )
            result.retention_optimized = script
        else:
            # Use generate() for plain text - no JSON parsing issues
            response = await self.client.generate(
                system_prompt=_retention_pass_prompt(result.target_duration),
                user_prompt=f"Optimize this script for maximum retention:\n\n{script}\n\n"
                f"Apply all retention optimization techniques. Return ONLY the improved script.",
                temperature=0.6,
                max_tokens=2048,
            )

            rewritten = _usable_rewrite(response, script)
            if rewritten:
                result.retention_optimized = rewritten
            else:
                result.retention_optimized = script

        # Safety: if output is too short, keep previous
        if (
            not result.retention_optimized
            or len(result.retention_optimized.strip()) < 50
        ):
            result.retention_optimized = script

        result.completed_stages.append(7)
        return result

    async def stage_8_voice_rhythm(self, session_id: str) -> PipelineResult:
        """Stage 8: Polish for TTS delivery."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        script = result.retention_optimized or result.hook_injected or result.draft
        if not script:
            raise ValueError("Script must exist before voice polish")

        if not isinstance(script, str):
            script = str(script)
            result.retention_optimized = script

        result.current_stage = 8
        log.info(f"[StoryForge] Stage 8: Voice & Rhythm Polish")

        script_words = len(script.split())
        if script_words > 3000 and not self.client.api_key:
            log.info(
                f"[StoryForge] Stage 8: Script too long ({script_words} words), skipping"
            )
            result.voice_polished = script
        else:
            # Use generate() for plain text - no JSON parsing issues
            response = await self.client.generate_structured(
                system_prompt=_voice_rhythm_prompt(result.target_duration),
                user_prompt=f"Optimize this script for voice/TTS delivery:\n\n{script}\n\n"
                f"Add proper punctuation for pauses, break long sentences, "
                f"and ensure natural spoken rhythm. Return ONLY the improved script.",
                temperature=0.5,
                schema_key="script_polish",
                max_tokens=2048,
            )

            improved_script = (
                response.get("improved_script")
                if isinstance(response, dict)
                else None
            )
            rewritten = _usable_rewrite(improved_script, script)
            if rewritten:
                result.voice_polished = rewritten
            else:
                result.voice_polished = script

        # Safety: if output is too short, keep previous
        if not result.voice_polished or len(result.voice_polished.strip()) < 50:
            result.voice_polished = script

        result.completed_stages.append(8)
        return result

    async def stage_9_final_polish(self, session_id: str) -> PipelineResult:
        """Stage 9: Final tightening and quality check."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        script = (
            result.voice_polished
            or result.retention_optimized
            or result.hook_injected
            or result.draft
        )
        if not script:
            raise ValueError("Script must exist before final polish")

        # Safety: ensure script is always a string
        if not isinstance(script, str):
            script = str(script)
            result.voice_polished = script

        result.current_stage = 9
        log.info(f"[StoryForge] Stage 9: Final Polish")

        script_words = len(script.split())
        if script_words > 3000 and not self.client.api_key:
            log.info(
                f"[StoryForge] Stage 9: Script too long ({script_words} words), skipping"
            )
            result.final_tightened = script
        else:
            # Use generate() for plain text - no JSON parsing issues
            response = await self.client.generate(
                system_prompt=_final_polish_prompt(result.target_duration),
                user_prompt=f"Apply final polish to this script:\n\n{script}\n\n"
                f"Tighten wording, fix any remaining issues, ensure production readiness. "
                f"Return ONLY the polished script.",
                temperature=0.4,
                max_tokens=2048,
            )

            rewritten = _usable_rewrite(response, script)
            if rewritten:
                result.final_tightened = rewritten
            else:
                result.final_tightened = script

        # Safety: if output is too short, keep previous
        if not result.final_tightened or len(result.final_tightened.strip()) < 50:
            result.final_tightened = script

        result.completed_stages.append(9)
        return result

    async def stage_10_quality_scoring(self, session_id: str) -> PipelineResult:
        """Stage 10: Score and suggest final tweaks."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        script = (
            result.final_tightened
            or result.voice_polished
            or result.retention_optimized
            or result.hook_injected
            or result.draft
        )
        if not script:
            raise ValueError("Script must exist before quality scoring")

        # Safety: ensure script is always a string
        if not isinstance(script, str):
            log.warning(
                f"[StoryForge] Stage 10: script was {type(script).__name__}, converting to string"
            )
            script = str(script)
            result.final_tightened = script

        result.current_stage = 10
        log.info(f"[StoryForge] Stage 10: Quality Scoring")

        script_words = len(script.split())

        # For long scripts, send a trimmed version to the scorer
        score_script = script
        if script_words > 2000:
            # Take first 800 words + last 800 words to give scorer a sample
            words = script.split()
            first = " ".join(words[:800])
            last = " ".join(words[-800:])
            score_script = f"[FIRST PART - {800} words]\n{first}\n\n[LAST PART - {800} words]\n{last}"
            log.info(
                f"[StoryForge] Stage 10: Script is {script_words} words, scoring trimmed sample (1600 words)"
            )

        try:
            response = await self.client.generate_structured(
                system_prompt=_quality_scoring_prompt(result.target_duration),
                user_prompt=f"Evaluate this YouTube Shorts script ({script_words} words total):\n\n{score_script}\n\n"
                f"Provide honest scores and specific actionable feedback.\n"
                f"Return JSON with keys: overall_score (0-100), breakdown (dict of dimension scores), suggestions (list of strings), verdict (string).",
                schema_key="quality_score",
                temperature=0.3,
                max_tokens=1200,
            )
        except Exception as e:
            log.error(f"[StoryForge] Stage 10: AI call failed: {e}")
            response = None

        if response and isinstance(response, dict):
            result.quality_score = float(response.get("overall_score", 70))
            result.quality_breakdown = response.get("breakdown", {})
            suggestions = response.get("suggestions", [])
            result.suggestions = (
                [str(s) for s in suggestions] if isinstance(suggestions, list) else []
            )
            log.info(
                f"[StoryForge] Stage 10: Score={result.quality_score}, breakdown={result.quality_breakdown}"
            )
        else:
            result.quality_score = 70
            result.quality_breakdown = {}
            result.suggestions = ["Quality scoring returned no data"]

        result.final_script = _bound_story_length(_longest_story(
            result.draft,
            result.hook_injected,
            result.retention_optimized,
            result.voice_polished,
            result.final_tightened,
        ), result.target_duration)
        result.word_count = len(result.final_script.split())
        if result.estimated_duration == 0:
            result.estimated_duration = round(result.word_count / 3.0, 1)

        result.completed_stages.append(10)
        result.current_stage = 10
        return result

    async def stage_11_dynamic_enhancement(
        self, session_id: str, target_score: int = 80, max_iterations: int = 2
    ) -> PipelineResult:
        """Stage 11: Dynamic enhancement loop. Analyze, suggest, apply, re-score. Repeat until target score."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        if not result.final_script:
            raise ValueError("Final script must exist before dynamic enhancement")

        result.current_stage = 11
        log.info(
            f"[StoryForge] Stage 11: Dynamic Enhancement Loop (target: {target_score}, max_iter: {max_iterations})"
        )

        current_script = result.final_script
        iteration = 0
        enhancement_log = []

        while iteration < max_iterations and result.quality_score < target_score:
            iteration += 1
            log.info(
                f"[StoryForge] Enhancement iteration {iteration}/{max_iterations} (current score: {result.quality_score})"
            )

            # Step 1: Get detailed analysis and suggestions
            analysis_response = await self.client.generate_structured(
                system_prompt=DYNAMIC_ENHANCEMENT_SYSTEM,
                user_prompt=f"Analyze this story and provide EXACT improvements:\n\n{current_script}\n\n"
                f"Current score: {result.quality_score}/100\n"
                f"Theme: {result.theme}\n"
                f"Focus on the WEAKEST areas. Be specific — quote exact text and provide exact replacements.",
                schema_key="enhancement_analysis",
                temperature=0.6,
                max_tokens=3000,
            )

            if not analysis_response or not isinstance(analysis_response, dict):
                log.warning(
                    f"[StoryForge] Enhancement analysis failed at iteration {iteration}"
                )
                result.errors.append(
                    f"Enhancement iteration {iteration}: analysis failed"
                )
                break

            # Extract score and suggestions (handle both schema and model output)
            new_score = analysis_response.get("overall_score") or analysis_response.get(
                "score", result.quality_score
            )
            suggestions = analysis_response.get("suggestions", [])

            if not suggestions or len(suggestions) == 0:
                log.info(
                    f"[StoryForge] No suggestions at iteration {iteration} — story is good"
                )
                break

            # Step 2: Apply the enhancements - use generate() for plain text
            apply_response = await self.client.generate(
                system_prompt=APPLY_ENHANCEMENTS_SYSTEM,
                user_prompt=f"Original story:\n{current_script}\n\n"
                f"Improvements to make:\n{json.dumps(suggestions, indent=2)}\n\n"
                f"Rewrite the story with these improvements applied. Return ONLY the improved story.",
                temperature=0.4,
                max_tokens=3000,
            )

            improved_script = _usable_rewrite(apply_response, current_script)
            if improved_script:
                current_script = improved_script
                result.quality_score = float(new_score)
                enhancement_log.append(
                    {
                        "iteration": iteration,
                        "score_before": result.quality_score,
                        "score_after": float(new_score),
                        "suggestions_count": len(suggestions),
                    }
                )
                log.info(
                    f"[StoryForge] Enhancement iteration {iteration}: score {result.quality_score} -> {new_score}"
                )
            else:
                log.warning(
                    f"[StoryForge] Enhancement application failed at iteration {iteration}"
                )
                break

        # Update final results
        result.final_script = _bound_story_length(
            _longest_story(result.final_script, current_script),
            result.target_duration,
        )
        result.word_count = len(result.final_script.split())
        result.estimated_duration = round(result.word_count / 3.0, 1)
        result.retention_notes.append(
            f"Dynamic enhancement: {iteration} iterations, final score {result.quality_score}"
        )

        result.completed_stages.append(11)
        result.current_stage = 11

        # Final cleanup - remove any special characters
        if result.final_script:
            result.final_script = _bound_story_length(
                _clean_script(result.final_script), result.target_duration
            )
            result.word_count = len(result.final_script.split())
            result.estimated_duration = round(result.word_count / 3.0, 1)

        return result

    async def stage_12_publish_pack(self, session_id: str) -> PipelineResult:
        """Stage 12: titles, description, tags, audience targeting, thumbnail."""
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")
        if not result.final_script:
            raise ValueError("Final script must exist before publish pack")

        result.current_stage = 12
        log.info("[StoryForge] Stage 12: Publish Pack")

        classification = result.classification
        category = classification.category if classification else "Mystery"
        tone = classification.tone if classification else ""
        audience_hint = (
            classification.target_audience if classification else "general"
        )
        hook_text = result.selected_hook.text if result.selected_hook else ""

        words = result.final_script.split()
        if len(words) > 900:
            sample = (
                " ".join(words[:600])
                + "\n...\n"
                + " ".join(words[-300:])
            )
        else:
            sample = result.final_script

        user_prompt = (
            f"Story theme: {result.theme}\n"
            f"Category: {category} | Tone: {tone} | Audience hint: {audience_hint}\n"
            f"Target duration: {result.target_duration}s\n"
            f"Selected hook: {hook_text}\n\n"
            f"Story:\n{sample}"
        )

        response = None
        try:
            response = await self.client.generate_structured(
                system_prompt=PUBLISH_PACK_SYSTEM,
                user_prompt=user_prompt,
                schema_key="publish_pack",
                temperature=0.8,
                max_tokens=2000,
            )
        except Exception as e:
            log.error(f"[StoryForge] Stage 12: AI call failed: {e}")

        result.publish_pack = self._normalize_publish_pack(response, result)
        self._render_publish_thumbnail(result)

        if not result.publish_pack.titles:
            result.errors.append("12_publish_pack: no titles generated")

        result.completed_stages.append(12)
        result.current_stage = 12
        return result

    # ─────────────────────────────────────────────────
    # Publish pack helpers (Stage 12)
    # ─────────────────────────────────────────────────

    def _fallback_publish_pack(self, result: PipelineResult) -> PublishPack:
        """Deterministic publish pack used when the AI call fails."""
        theme = (result.theme or "").strip()
        classification = result.classification
        category = classification.category if classification else "Mystery"
        audience_hint = (
            classification.target_audience if classification else "general"
        )
        sub_category = classification.sub_category if classification else ""
        hook = result.selected_hook.text if result.selected_hook else ""

        short_theme = theme[:78].rstrip(",. ")
        titles: list[str] = []
        for candidate in (
            theme[:95],
            hook[:95],
            f"The Truth About {short_theme}",
            f"What Really Happened: {short_theme}",
            f"{short_theme} - The Full Story",
        ):
            cleaned = _clip_text(candidate.strip().strip('"'), 95)
            if cleaned and cleaned.lower() not in {t.lower() for t in titles}:
                titles.append(cleaned)
            if len(titles) == 4:
                break

        description = (
            f"{hook or theme}\n\n"
            f"{theme} - told the way it actually happened, with every detail "
            "that matters kept in.\n\n"
            "Have you ever seen something like this? Tell me what you would "
            "have done in the comments.\n\n"
            "Like and subscribe for more true story videos every week."
        )

        category_tags = [
            w.lower()
            for w in re.findall(r"[A-Za-z]{4,}", category)
        ][:3]
        tags = list(
            dict.fromkeys(
                category_tags
                + ["storytime", "true story", "drama", "viral", "narration", "youtube shorts"]
            )
        )[:12]

        hashtags = ["#storytime", "#truestory", "#drama", "#viral"]
        if category:
            hashtags.append(
                "#" + re.sub(r"[^A-Za-z0-9]", "", category.split("/")[0])[:20].lower()
            )
        if result.target_duration <= 180:
            hashtags.append("#shorts")

        stop = {
            "i", "my", "a", "an", "the", "of", "and", "to", "in", "on", "for",
            "was", "were", "is", "it", "that", "with", "at", "by", "from",
            "but", "or", "me", "we", "our", "they", "their", "he", "she",
            "his", "her", "when", "after", "before", "into", "out",
        }
        key_words = [
            w for w in re.findall(r"[A-Za-z']+", theme) if w.lower() not in stop
        ]
        headline = " ".join(key_words[:4]).upper()[:24].strip()
        if not headline:
            headline = (theme.split()[0] if theme.split() else "STORY").upper()[:24]

        badge_source = category.split("/")[0] if category else "True Story"
        badge = _clip_text(re.sub(r"[^A-Za-z ]", " ", badge_source).strip().upper(), 12)
        subline = _clip_text(sub_category or "watch what happens", 40)

        return PublishPack(
            titles=titles,
            selected_title=titles[0] if titles else "",
            description=description,
            tags=tags,
            hashtags=list(dict.fromkeys(hashtags))[:7],
            audience=AudienceTarget(
                persona=(
                    f"Viewers who follow {category.lower()} stories about "
                    f"\"{theme[:60]}\""
                ),
                age_range="18-34",
                gender_skew="balanced",
                interests=list(
                    dict.fromkeys(
                        [
                            category.lower().replace("/", " "),
                            audience_hint.replace("_", " "),
                            "storytime",
                            "viral videos",
                        ]
                    )
                )[:5],
                why_they_watch=(
                    "They want to know how it ends and whether they would have "
                    "done the same"
                ),
                best_posting_window="Evenings 7-10pm",
            ),
            thumbnail=ThumbnailPlan(headline=headline, subline=subline, badge=badge),
        )

    def _normalize_publish_pack(
        self, response: Any, result: PipelineResult
    ) -> PublishPack:
        """Merge the AI response into a complete pack; defaults fill any gap."""
        pack = self._fallback_publish_pack(result)
        if not isinstance(response, dict):
            return pack

        raw_titles = response.get("titles")
        if isinstance(raw_titles, list):
            titles: list[str] = []
            for t in raw_titles:
                cleaned = str(t).strip().strip('"').replace("#", "").strip()
                cleaned = _clip_text(cleaned, 95)
                if cleaned and cleaned.lower() not in {x.lower() for x in titles}:
                    titles.append(cleaned)
                if len(titles) == 5:
                    break
            if titles:
                pack.titles = titles
                pack.selected_title = titles[0]

        description = response.get("description")
        if isinstance(description, str) and len(description.strip()) > 40:
            pack.description = NVIDIAClient._strip_markdown_fences(description).strip()

        for key, cap in (("tags", 12), ("hashtags", 7)):
            raw = response.get(key)
            if isinstance(raw, list):
                cleaned_list: list[str] = []
                for item in raw:
                    text = str(item).strip()
                    if not text:
                        continue
                    if key == "tags":
                        text = text.lstrip("#").lower()
                    elif not text.startswith("#"):
                        text = "#" + text.lstrip("#")
                    if text and text.lower() not in {x.lower() for x in cleaned_list}:
                        cleaned_list.append(text)
                    if len(cleaned_list) == cap:
                        break
                if cleaned_list:
                    if key == "hashtags" and result.target_duration <= 180:
                        if "#shorts" not in {h.lower() for h in cleaned_list}:
                            cleaned_list.append("#shorts")
                    setattr(pack, key, cleaned_list)

        raw_audience = response.get("audience")
        if isinstance(raw_audience, dict):
            for field_name in (
                "persona",
                "age_range",
                "gender_skew",
                "why_they_watch",
                "best_posting_window",
            ):
                value = raw_audience.get(field_name)
                if isinstance(value, str) and value.strip():
                    setattr(pack.audience, field_name, value.strip()[:300])
            interests = raw_audience.get("interests")
            if isinstance(interests, list):
                cleaned_interests = [
                    str(i).strip().lower() for i in interests if str(i).strip()
                ][:6]
                if cleaned_interests:
                    pack.audience.interests = cleaned_interests

        raw_thumbnail = response.get("thumbnail")
        if isinstance(raw_thumbnail, dict):
            headline = raw_thumbnail.get("headline")
            if isinstance(headline, str) and headline.strip():
                pack.thumbnail.headline = _clip_text(headline, 24).upper()
            subline = raw_thumbnail.get("subline")
            if isinstance(subline, str) and subline.strip():
                pack.thumbnail.subline = _clip_text(subline, 40)
            badge = raw_thumbnail.get("badge")
            if isinstance(badge, str) and badge.strip():
                pack.thumbnail.badge = _clip_text(badge, 12).upper()

        if not pack.selected_title and pack.titles:
            pack.selected_title = pack.titles[0]
        return pack

    def _render_publish_thumbnail(self, result: PipelineResult) -> None:
        """Render the stage-12 thumbnail into settings.FORGE_THUMBS_DIR."""
        pack = result.publish_pack
        if not pack:
            return
        try:
            classification = result.classification
            category = classification.category if classification else "Mystery"
            niche = _niche_for_category(category)
            out_path = settings.FORGE_THUMBS_DIR / f"{result.session_id}.jpg"
            generate_thumbnail(
                video_path=None,
                title=pack.thumbnail.headline or result.theme[:40],
                niche=niche,
                output_path=str(out_path),
                subtitle=pack.thumbnail.subline or None,
            )
            if out_path.exists() and out_path.stat().st_size > 0:
                pack.thumbnail.image_path = out_path.name
                log.info(f"[StoryForge] Stage 12: thumbnail written ({niche})")
            else:
                result.errors.append("12_publish_pack: thumbnail render produced no file")
        except Exception as e:
            log.warning(f"[StoryForge] Stage 12: thumbnail render failed: {e}")
            result.errors.append(f"12_publish_pack: thumbnail render failed: {e}")

    async def stage_with_fallback(
        self,
        session_id: str,
        stage_func,
        stage_name: str,
        fallback_strategy: Literal["ai", "patterns", "hybrid"] = "hybrid",
    ) -> PipelineResult:
        """Run a pipeline stage with configurable fallback strategy.

        If AI parsing fails, attempt pattern-based fallbacks before giving up.
        Tracks ai_failures to decide when to switch strategies.
        """
        result = self.sessions.get(session_id)
        if not result:
            raise ValueError("Session not found")

        # Try the AI stage function
        stage_number = {
            "1_story_classification": 1,
            "2_cold_open_hook": 2,
            "3_retention_hook_planning": 3,
            "4_story_architecture": 4,
            "5_draft_generation": 5,
            "5b_tense_enforcement": 5,
            "6_micro_hook_injection": 6,
            "7_retention_pass": 7,
            "8_voice_rhythm": 8,
            "9_final_polish": 9,
            "10_quality_scoring": 10,
            "11_dynamic_enhancement": 11,
            "12_publish_pack": 12,
        }.get(stage_name, 0)

        def mark_stage_complete() -> None:
            if stage_number and stage_number not in result.completed_stages:
                result.completed_stages.append(stage_number)
            result.current_stage = max(
                [stage_number, *result.completed_stages], default=0
            )

        try:
            stage_started = time.monotonic()
            if fallback_strategy == "patterns":
                raise RuntimeError("pattern fallback requested")
            parse_failures_before = self.client.parse_failures
            result = await asyncio.wait_for(
                stage_func(result.session_id),
                timeout=settings.STORY_STAGE_TIMEOUT,
            )
            ai_used_fallback = self.client.parse_failures > parse_failures_before
            if ai_used_fallback:
                ai_failures[session_id] = ai_failures.get(session_id, 0) + 1
                result.errors.append(f"{stage_name}: AI unavailable, using fallback")
                log.warning(
                    f"[StoryForge] {stage_name}: completed with AI fallback "
                    f"(failures: {ai_failures[session_id]})"
                )
            else:
                ai_failures[session_id] = 0
                log.info(
                    f"[StoryForge] {stage_name}: AI success "
                    f"(failures: {ai_failures.get(session_id, 0)}, "
                    f"elapsed: {time.monotonic() - stage_started:.1f}s)"
                )
            mark_stage_complete()
            return result

        except Exception as e:
            ai_failures[session_id] = ai_failures.get(session_id, 0) + 1
            if fallback_strategy == "patterns":
                log.info(f"[StoryForge] {stage_name}: using pattern fallback")
            else:
                log.warning(
                    f"[StoryForge] {stage_name}: AI failed "
                    f"(attempt {ai_failures[session_id]}): {str(e)[:100]}"
                )

            # Strategy: "ai" - keep trying AI
            # Strategy: "patterns" - use fallbacks immediately
            # Strategy: "hybrid" - try AI first, then patterns

            if fallback_strategy == "patterns":
                log.info(
                    f"[StoryForge] {stage_name}: Using pattern fallback (strategy: patterns)"
                )
                if stage_name == "1_story_classification":
                    result.classification = StoryClassification(
                        category="Mystery",
                        sub_category="unknown",
                        tone="suspenseful",
                        target_audience="general",
                        lead_gender="male",
                    )
                    result.errors.append(
                        f"{stage_name}: AI failure, using pattern defaults"
                    )
                elif stage_name == "2_cold_open_hook":
                    result.cold_hooks = self._fallback_hooks(result.theme)
                    result.selected_hook = (
                        result.cold_hooks[0] if result.cold_hooks else None
                    )
                    result.errors.append(
                        f"{stage_name}: AI failure, using pattern hooks"
                    )
                elif stage_name == "3_retention_hook_planning":
                    result.retention_plan = self._fallback_retention_plan()
                    result.errors.append(
                        f"{stage_name}: AI failure, using pattern retention plan"
                    )
                elif stage_name == "4_story_architecture":
                    result.architecture = self._fallback_architecture(
                        result.selected_hook, result.classification
                    )
                    result.errors.append(
                        f"{stage_name}: AI failure, using pattern architecture"
                    )
                elif stage_name == "5_draft_generation":
                    result.draft = self._fallback_draft(result)
                    result.errors.append(
                        f"{stage_name}: AI failure, using pattern draft"
                    )
                elif stage_name == "5b_tense_enforcement":
                    result.errors.append(
                        f"{stage_name}: AI failure, preserving existing draft"
                    )
                elif stage_name == "5_to_9_unified_polish":
                    polished = result.draft
                    result.hook_injected = polished
                    result.retention_optimized = polished
                    result.voice_polished = polished
                    result.final_tightened = polished
                    result.final_script = polished
                    result.word_count = len(polished.split()) if polished else 0
                    result.estimated_duration = (
                        round(result.word_count / 3.0, 1) if result.word_count else 0
                    )
                    result.errors.append(
                        f"{stage_name}: AI failure, preserving original draft"
                    )
                elif stage_name == "6_micro_hook_injection":
                    result.hook_injected = result.draft if result.draft else ""
                    result.errors.append(f"{stage_name}: AI failure, using draft")
                elif stage_name == "7_retention_pass":
                    result.retention_optimized = result.hook_injected or result.draft
                    result.errors.append(
                        f"{stage_name}: AI failure, keeping previous script"
                    )
                elif stage_name == "8_voice_rhythm":
                    result.voice_polished = (
                        result.retention_optimized
                        or result.hook_injected
                        or result.draft
                    )
                    result.errors.append(
                        f"{stage_name}: AI failure, keeping previous script"
                    )
                elif stage_name == "9_final_polish":
                    result.final_tightened = (
                        result.voice_polished
                        or result.retention_optimized
                        or result.hook_injected
                        or result.draft
                    )
                    result.errors.append(
                        f"{stage_name}: AI failure, keeping previous script"
                    )
                elif stage_name == "10_quality_scoring":
                    result.quality_score = 70
                    result.quality_breakdown = {}
                    result.suggestions = [
                        "Quality scoring: AI failed, using default score"
                    ]
                    result.final_script = (
                        result.final_tightened
                        or result.voice_polished
                        or result.retention_optimized
                        or result.hook_injected
                        or result.draft
                    )
                    result.word_count = (
                        len(result.final_script.split()) if result.final_script else 0
                    )
                    result.estimated_duration = (
                        round(result.word_count / 3.0, 1) if result.word_count else 0
                    )
                    result.errors.append(
                        f"{stage_name}: AI failure, using default scoring"
                    )
                elif stage_name == "11_dynamic_enhancement":
                    result.errors.append(
                        f"{stage_name}: AI failure, stopping enhancements"
                    )
                elif stage_name == "12_publish_pack":
                    result.publish_pack = self._fallback_publish_pack(result)
                    self._render_publish_thumbnail(result)
                    result.errors.append(
                        f"{stage_name}: AI failure, using pattern publish pack"
                    )
                mark_stage_complete()
                return result

            # Hybrid: try once more with modified prompt, then patterns
            if fallback_strategy == "hybrid" and ai_failures[session_id] <= 2:
                log.info(
                    f"[StoryForge] {stage_name}: Trying hybrid approach (attempt {ai_failures[session_id]})"
                )
                # Could modify prompt here, but for now fall through to patterns
                # Actually, just continue to patterns after 1 AI attempt
                if ai_failures[session_id] >= 1:
                    return await self.stage_with_fallback(
                        session_id, stage_func, stage_name, fallback_strategy="patterns"
                    )

            # Fallback for other strategies
            log.info(f"[StoryForge] {stage_name}: Using final fallback")
            if stage_name == "1_story_classification":
                result.classification = StoryClassification(
                    category="Mystery",
                    sub_category="unknown",
                    tone="suspenseful",
                    target_audience="general",
                    lead_gender="male",
                )
                result.errors.append(
                    f"{stage_name}: AI failure, using pattern defaults"
                )
            elif stage_name == "2_cold_open_hook":
                result.cold_hooks = self._fallback_hooks(result.theme)
                result.selected_hook = (
                    result.cold_hooks[0] if result.cold_hooks else None
                )
                result.errors.append(f"{stage_name}: AI failure, using pattern hooks")
            elif stage_name == "3_retention_hook_planning":
                result.retention_plan = self._fallback_retention_plan()
                result.errors.append(
                    f"{stage_name}: AI failure, using pattern retention plan"
                )
            elif stage_name == "4_story_architecture":
                result.architecture = self._fallback_architecture(
                    result.selected_hook, result.classification
                )
                result.errors.append(
                    f"{stage_name}: AI failure, using pattern architecture"
                )
            elif stage_name == "5_draft_generation":
                result.draft = self._fallback_draft(result)
                result.errors.append(f"{stage_name}: AI failure, using pattern draft")
            elif stage_name == "5b_tense_enforcement":
                result.errors.append(
                    f"{stage_name}: AI failure, preserving existing draft"
                )
            elif stage_name == "5_to_9_unified_polish":
                polished = result.draft
                result.hook_injected = polished
                result.retention_optimized = polished
                result.voice_polished = polished
                result.final_tightened = polished
                result.final_script = polished
                result.word_count = len(polished.split()) if polished else 0
                result.estimated_duration = (
                    round(result.word_count / 3.0, 1) if result.word_count else 0
                )
                result.errors.append(
                    f"{stage_name}: AI failure, preserving original draft"
                )
            elif stage_name == "6_micro_hook_injection":
                result.hook_injected = result.draft if result.draft else ""
                result.errors.append(f"{stage_name}: AI failure, using draft")
            elif stage_name == "7_retention_pass":
                result.retention_optimized = result.hook_injected or result.draft
                result.errors.append(
                    f"{stage_name}: AI failure, keeping previous script"
                )
            elif stage_name == "8_voice_rhythm":
                result.voice_polished = (
                    result.retention_optimized or result.hook_injected or result.draft
                )
                result.errors.append(
                    f"{stage_name}: AI failure, keeping previous script"
                )
            elif stage_name == "9_final_polish":
                result.final_tightened = (
                    result.voice_polished
                    or result.retention_optimized
                    or result.hook_injected
                    or result.draft
                )
                result.errors.append(
                    f"{stage_name}: AI failure, keeping previous script"
                )
            elif stage_name == "10_quality_scoring":
                result.quality_score = 70
                result.quality_breakdown = {}
                result.suggestions = ["Quality scoring: AI failed, using default score"]
                result.final_script = (
                    result.final_tightened
                    or result.voice_polished
                    or result.retention_optimized
                    or result.hook_injected
                    or result.draft
                )
                result.word_count = (
                    len(result.final_script.split()) if result.final_script else 0
                )
                result.estimated_duration = (
                    round(result.word_count / 3.0, 1) if result.word_count else 0
                )
                result.errors.append(f"{stage_name}: AI failure, using default scoring")
            elif stage_name == "11_dynamic_enhancement":
                result.errors.append(f"{stage_name}: AI failure, stopping enhancements")
            elif stage_name == "12_publish_pack":
                result.publish_pack = self._fallback_publish_pack(result)
                self._render_publish_thumbnail(result)
                result.errors.append(
                    f"{stage_name}: AI failure, using pattern publish pack"
                )
            mark_stage_complete()
            return result

    async def run_full_pipeline(
        self, theme: str, target_duration: int = 120
    ) -> PipelineResult:
        """Run all stages in sequence with fallback support."""
        result = self.create_session(theme, target_duration=target_duration)

        result = await self.stage_with_fallback(
            result.session_id,
            self.stage_1_story_classification,
            "1_story_classification",
            fallback_strategy="hybrid",
        )

        result = await self.stage_with_fallback(
            result.session_id,
            self.stage_2_cold_open_hook,
            "2_cold_open_hook",
            fallback_strategy="hybrid",
        )

        if result.cold_hooks:
            result.cold_hooks[0].selected = True
            result.selected_hook = result.cold_hooks[0]

        result = await self.stage_with_fallback(
            result.session_id,
            self.stage_3_retention_hook_planning,
            "3_retention_hook_planning",
            fallback_strategy="hybrid",
        )
        result = await self.stage_with_fallback(
            result.session_id,
            self.stage_4_story_architecture,
            "4_story_architecture",
            fallback_strategy="hybrid",
        )
        result = await self.stage_with_fallback(
            result.session_id,
            self.stage_5_draft_generation,
            "5_draft_generation",
            fallback_strategy="hybrid",
        )
        result = await self.stage_with_fallback(
            result.session_id,
            self.stage_5_to_9_unified_polish,
            "5_to_9_unified_polish",
            fallback_strategy="hybrid",
        )
        result = await self.stage_with_fallback(
            result.session_id,
            self.stage_10_quality_scoring,
            "10_quality_scoring",
            fallback_strategy="hybrid",
        )
        if settings.STORY_ENABLE_ENHANCEMENT:
            result = await self.stage_with_fallback(
                result.session_id,
                self.stage_11_dynamic_enhancement,
                "11_dynamic_enhancement",
                fallback_strategy="hybrid",
            )
        else:
            result.current_stage = 10
            result.errors.append("Stage 11 enhancement skipped by configuration")

        if not result.final_script:
            result.final_script = (
                result.final_tightened
                or result.voice_polished
                or result.retention_optimized
                or result.hook_injected
                or result.draft
            )
            if result.final_script:
                result.word_count = len(result.final_script.split())
                result.estimated_duration = round(result.word_count / 3.0, 1)
                result.errors.append(
                    "Final safety check: preserved the best available generated script"
                )
            else:
                raise RuntimeError("Story pipeline produced no usable script")

        minimum_final_words = max(80, int(result.target_duration * 3 * 0.5))
        if len(result.final_script.split()) < minimum_final_words:
            fallback_script = self._fallback_draft(result)
            if len(fallback_script.split()) > len(result.final_script.split()):
                result.final_script = fallback_script
                result.word_count = len(fallback_script.split())
                result.estimated_duration = round(result.word_count / 3.0, 1)
                result.errors.append(
                    "Final safety check: replaced an undersized result with a complete fallback story"
                )

        result.final_script = _bound_story_length(
            _clean_script(result.final_script), result.target_duration
        )
        result.word_count = len(result.final_script.split())
        result.estimated_duration = round(result.word_count / 3.0, 1)

        if settings.STORY_ENABLE_PUBLISH_PACK:
            result = await self.stage_with_fallback(
                result.session_id,
                self.stage_12_publish_pack,
                "12_publish_pack",
                fallback_strategy="hybrid",
            )

        self.mark_session_completed(result.session_id)
        return result

    # ─────────────────────────────────────────────────
    # Fallback generators (when AI fails)
    # ─────────────────────────────────────────────────

    def _fallback_hooks(self, theme: str) -> list[ColdOpenHook]:
        # Extract a key word from theme for hooks
        words = theme.lower().split()
        # Find a meaningful word (skip articles, prepositions)
        stop_words = {
            "a",
            "an",
            "the",
            "i",
            "my",
            "me",
            "who",
            "is",
            "was",
            "has",
            "had",
            "that",
            "with",
            "for",
            "and",
            "but",
            "or",
            "in",
            "on",
            "at",
            "to",
        }
        key_words = [w for w in words if w not in stop_words and len(w) > 2]
        key = key_words[0] if key_words else "this"
        key2 = key_words[1] if len(key_words) > 1 else "story"

        return [
            ColdOpenHook(
                id=str(uuid.uuid4())[:6],
                text=f"I discovered something about {key2} that changed everything.",
                hook_category="curiosity",
                psychological_trigger="curiosity_gap",
                pattern_formula="I discovered something about X that changed everything",
            ),
            ColdOpenHook(
                id=str(uuid.uuid4())[:6],
                text=f"The {key} I trusted was living a double life.",
                hook_category="shock",
                psychological_trigger="betrayal",
                pattern_formula="The [person] I trusted was living a double life",
            ),
            ColdOpenHook(
                id=str(uuid.uuid4())[:6],
                text=f"Nobody was supposed to find out about {key}. But I did.",
                hook_category="mystery",
                psychological_trigger="open_loop",
                pattern_formula="Nobody was supposed to find out about X. But I did.",
            ),
            ColdOpenHook(
                id=str(uuid.uuid4())[:6],
                text=f"I found one detail that made the {key} story worse.",
                hook_category="reveal",
                psychological_trigger="surprise",
                pattern_formula="I found one detail that changed everything",
            ),
            ColdOpenHook(
                id=str(uuid.uuid4())[:6],
                text=f"The warning about {key} arrived after it was too late.",
                hook_category="consequence",
                psychological_trigger="fear",
                pattern_formula="The warning came after it was too late",
            ),
        ]

    def _fallback_retention_plan(self) -> list[RetentionPlan]:
        return [
            RetentionPlan(
                "But Then...", "after context", "0:08", "Create anticipation"
            ),
            RetentionPlan(
                "There Was Just One Problem...",
                "before conflict",
                "0:15",
                "Introduce tension",
            ),
            RetentionPlan(
                "Then Everything Changed...",
                "during escalation",
                "0:25",
                "Raise stakes",
            ),
            RetentionPlan(
                "Then I Found Out...", "before reveal", "0:35", "Build curiosity"
            ),
            RetentionPlan("And That's When...", "at twist", "0:45", "Major reveal"),
            RetentionPlan("The Evidence...", "before confrontation", "0:55", "Prove the suspicion"),
            RetentionPlan("The Truth Was...", "final reveal", "1:15", "Reveal the truth"),
            RetentionPlan("Looking Back...", "aftermath", "1:25", "Leave a lasting implication"),
        ]

    def _fallback_architecture(
        self, hook: Optional[ColdOpenHook], cls: Optional[StoryClassification]
    ) -> list[StoryBeat]:
        hook_text = (
            hook.text if hook else "I discovered something that changed everything."
        )
        return [
            StoryBeat(
                1,
                "0:00",
                "0:02",
                "Stop the scroll",
                hook_text,
                8,
                "intrigue",
                "cold_open",
            ),
            StoryBeat(
                2,
                "0:02",
                "0:08",
                "Context",
                "But then I checked the timestamp.",
                15,
                "curiosity",
                "But Then...",
            ),
            StoryBeat(
                3,
                "0:08",
                "0:15",
                "Conflict",
                "There was just one problem. Nobody believed me.",
                18,
                "frustration",
                "There Was Just One Problem...",
            ),
            StoryBeat(
                4,
                "0:15",
                "0:25",
                "Escalation",
                "Then everything changed. The evidence disappeared overnight.",
                25,
                "tension",
                "Then Everything Changed...",
            ),
            StoryBeat(
                5,
                "0:25",
                "0:35",
                "Reveal",
                "Then I found out who was behind it all.",
                25,
                "revelation",
                "Then I Found Out...",
            ),
            StoryBeat(
                6,
                "0:35",
                "0:45",
                "Twist",
                "And that's when the truth hit me.",
                25,
                "shock",
                "And That's When...",
            ),
            StoryBeat(
                7,
                "0:45",
                "0:55",
                "Ending",
                "Three weeks later, karma caught up.",
                20,
                "satisfaction",
                "Karma Ending",
            ),
        ]

    def _extract_text_from_dict(self, data) -> str:
        """Recursively extract narrator/text content from a nested dict structure."""
        if isinstance(data, str):
            return data
        if isinstance(data, list):
            parts = []
            for item in data:
                extracted = self._extract_text_from_dict(item)
                if extracted:
                    parts.append(extracted)
            return "\n".join(parts)
        if isinstance(data, dict):
            # Look for common text keys
            for key in [
                "narrator",
                "text",
                "content",
                "script",
                "line",
                "dialogue",
                "voiceover",
                "voice",
            ]:
                if key in data:
                    extracted = self._extract_text_from_dict(data[key])
                    if extracted:
                        return extracted
            # If no text key found, try all values
            parts = []
            for value in data.values():
                extracted = self._extract_text_from_dict(value)
                if extracted and len(extracted) > 10:
                    parts.append(extracted)
            return "\n".join(parts)
        return ""

    def _fallback_draft(self, result: PipelineResult) -> str:
        hook_text = (
            result.selected_hook.text
            if result.selected_hook
            else "I discovered something that changed everything."
        )
        theme = result.theme.lower()

        # Extract key elements from theme
        words = theme.split()
        stop_words = {
            "a",
            "an",
            "the",
            "i",
            "my",
            "me",
            "who",
            "is",
            "was",
            "has",
            "had",
            "that",
            "with",
            "for",
            "and",
            "but",
            "or",
            "in",
            "on",
            "at",
            "to",
        }
        key_words = [w for w in words if w not in stop_words and len(w) > 2]
        key = key_words[0] if key_words else "this"

        return (
            f"{hook_text}\n\n"
            f"But then I noticed something nobody else had. A detail that didn't add up.\n\n"
            f"There was just one problem. Nobody believed what I found.\n\n"
            f"I kept digging. Then everything changed. The truth was worse than I imagined.\n\n"
            f"Then I found out who was really behind it.\n\n"
            f"And that's when the whole thing unraveled."
        )


# Singleton
story_forge = StoryForgePipeline()
