"""
Metadata Generator
LLM-powered title, description, and tag generation for YouTube uploads.
STORY-SPECIFIC: Generates metadata based on the actual story content.
"""
import json
import logging
import re
import random
from dataclasses import dataclass, field

from .nvidia_client import NVIDIAClient

# Module-level instance for convenient access
nvidia_client = NVIDIAClient()

log = logging.getLogger(__name__)


@dataclass
class GeneratedMetadata:
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]
    title_options: list[str] = field(default_factory=list)
    category_id: str = "22"


CATEGORY_MAP = {
    "relationship": "22",
    "betrayal": "22",
    "family": "22",
    "mystery": "22",
    "workplace": "22",
    "revenge": "22",
    "money": "22",
    "crime": "24",
    "wholesome": "22",
    "horror": "22",
    "true_crime": "24",
    "psychology": "22",
    "motivation": "22",
    "storytime": "22",
    "drama": "22",
}


NICHE_CONTEXT = {
    "relationship": "emotional, personal, relatable. Focus on love, heartbreak, trust, and betrayal.",
    "betrayal": "shocking, dark, suspenseful. Someone broke trust in the worst way.",
    "family": "warm, emotional, sometimes dark. Family secrets, dynamics, and unexpected turns.",
    "mystery": "suspenseful, investigative, unanswered questions. Something doesn't add up.",
    "workplace": "frustrating, relatable, dramatic. Office politics, bad bosses, career drama.",
    "revenge": "satisfying, dramatic, justice-seeking. Someone got what they deserved.",
    "money": "tension, high stakes, life-changing. Financial decisions that altered everything.",
    "crime": "dark, serious, real. Criminal activity and its consequences.",
    "wholesome": "heartwarming, positive, uplifting. Good people doing good things.",
    "horror": "creepy, unsettling, fear-inducing. Things that haunt you.",
    "true_crime": "dark, suspenseful, investigative. Real crimes, real people, real stakes.",
    "psychology": "insightful, thought-provoking, scientific. Hidden truths about behavior.",
    "motivation": "energetic, empowering, transformative. Lessons that change lives.",
    "storytime": "personal, engaging, conversational. Real stories from real people.",
    "drama": "intense, emotional, gripping. High-stakes situations and dramatic reveals.",
}


# ─────────────────────────────────────────────────────
# STORY-SPECIFIC TITLE PATTERNS (from StoryForge categories)
# ─────────────────────────────────────────────────────

STORY_TITLE_PATTERNS = {
    "relationship": [
        "My {person} Had Been {action} Behind My Back",
        "I Found {object} And Now My Relationship Is Over",
        "The {timeframe} That Destroyed My Relationship",
        "My {person} Chose {person2} Over Me",
        "I Never Expected {person} Would Do This",
        "The Secret {person} Kept From Me For {timeframe}",
        "My {person} Lied About {something} And I Have Proof",
        "I Lost Everything Because Of {person}",
        "My {person} Was Living A Double Life",
        "The {event} That Changed Everything Between Us",
    ],
    "betrayal": [
        "My {person} Had Been {action} With {person2}",
        "I Found Out My {person} Was {action} The Whole Time",
        "The {person} I Trusted Most {action}",
        "My {person} Betrayed Me In The Worst Way",
        "I Discovered {person} Secret {timeframe} Ago",
        "My {person} {action} Behind My Back For {timeframe}",
        "The {person} I Loved Was Never Who They Seemed",
        "I Found {object} And The Truth Came Out",
        "My {person} {action} And I Have The Proof",
        "The {event} That Exposed {person} Lies",
    ],
    "family": [
        "My {person} Kept A Secret For {timeframe}",
        "I Found Out {person} Was Not Who I Thought",
        "The {event} That Tore My Family Apart",
        "My {person} Did Something I Never Expected",
        "The {timeframe} Secret That Changed Everything",
        "My {person} {action} And Now Nothing Is The Same",
        "I Discovered {person} Hidden {something}",
        "The {event} That Brought My Family Together",
        "My {person} Made A Choice I Cannot Forget",
        "The Truth About {person} Finally Came Out",
    ],
    "mystery": [
        "I Found {object} And Now I Cannot Sleep",
        "The {event} That Nobody Can Explain",
        "Something Was Wrong From The Start",
        "The {person} Who Disappeared Without A Trace",
        "I Discovered {something} And Now I Am Scared",
        "The {event} That Still Haunts Me",
        "Nobody Believed Me Until I Found {object}",
        "The {timeframe} That Changed Everything",
        "I Found Out {something} And It Changed Everything",
        "The {person} Who Was Never Who They Seemed",
    ],
    "workplace": [
        "My {person} Made Me Do Something I Regret",
        "The {event} That Almost Got Me Fired",
        "My {person} Stole My Idea And Got Promoted",
        "I Discovered {person} Secret Plan",
        "The {event} That Ruined My Career",
        "My {person} {action} And I Have The Proof",
        "I Lost My Job Because Of {person}",
        "The {timeframe} That Changed My Career Forever",
        "My {person} Was {action} Behind Everyone Back",
        "The {event} That Exposed Everything",
    ],
    "revenge": [
        "My {person} {action} So I Got Even",
        "The {timeframe} Plan That Worked Perfectly",
        "My {person} Thought They Got Away With {something}",
        "I Got Revenge On {person} And It Was Worth It",
        "The {event} That Made Me Take Action",
        "My {person} {action} And Now They Regret It",
        "I Waited {timeframe} Then Got My Payback",
        "The {person} Who Got Exactly What They Deserved",
        "My {person} {action} So I Made Sure They Paid",
        "The {event} That Changed Everything For {person}",
    ],
    "money": [
        "I Lost ${amount} Because Of {person}",
        "The {event} That Cost Me Everything",
        "My {person} Stole My ${amount}",
        "I Found {object} And It Changed My Life",
        "The {timeframe} Decision That Changed Everything",
        "My {person} {action} And Now I Have Nothing",
        "I Discovered {person} Secret About My Money",
        "The {timeframe} That Changed My Financial Life",
        "My {person} {action} With My Money And I Found Out",
        "The {timeframe} That Made Me A Different Person",
    ],
    "crime": [
        "The {event} That Shook Everyone",
        "I Found {object} And Now The Truth Is Out",
        "The {person} Who Got Away With {something}",
        "My {person} Was {action} And Nobody Knew",
        "The {timeframe} Investigation That Changed Everything",
        "I Found {object} And Now The Police Are Involved",
        "The {event} That Changed Everything",
        "My {person} {action} And Now They Are Gone",
        "The {person} Who Was Not Who They Seemed",
        "I Found {object} And Now The Case Is Open",
    ],
    "wholesome": [
        "My {person} Did Something That Made Me Cry",
        "The {event} That Restored My Faith In Humanity",
        "My {person} Did Something Beautiful",
        "The {timeframe} That Changed My Life Forever",
        "My {person} Surprised Me With Something Special",
        "The {event} That Brought Us All Together",
        "My {person} Did Something I Will Never Forget",
        "The {timeframe} That Changed Everything For The Better",
        "My {person} Did Something Perfect",
        "The {event} That Made Everything Worth It",
    ],
    "horror": [
        "I Saw Something And Now I Cannot Sleep",
        "The {event} That Still Haunts Me",
        "My {person} Did Something That Scared Me",
        "The {timeframe} That Changed Everything",
        "I Found {object} And Now I Wish I Had Not",
        "The {person} Who Was Never Who They Seemed",
        "My {person} Did Something I Cannot Forget",
        "The {event} That Happened One Night",
        "I Discovered Something And Now I Am Not Safe",
        "The {person} Who Still Comes To Me In Dreams",
    ],
    "true_crime": [
        "The {event} That Shook Everyone",
        "I Found {object} And Now The Truth Is Out",
        "The {person} Who Got Away With {something}",
        "My {person} Was {action} And Nobody Knew",
        "The {timeframe} Investigation That Changed Everything",
        "I Discovered Something And Now I Cannot Rest",
        "The {event} That Changed Everything",
        "My {person} {action} And Now They Are Gone",
        "The {person} Who Was Not Who They Seemed",
        "I Found {object} And Now The Case Is Open",
    ],
    "psychology": [
        "The {timeframe} That Changed How I Think",
        "I Discovered Something About My Mind",
        "The {event} That Changed My Perspective",
        "My {person} Did Something That Changed How I See Things",
        "The {timeframe} That Changed Everything",
        "I Found {object} And Now I Understand",
        "The {person} Who Taught Me Something Important",
        "My {person} Did Something And Now I Know Better",
        "The {event} That Changed How I See The World",
        "I Discovered Something About Human Nature",
    ],
    "motivation": [
        "The {timeframe} That Changed My Life",
        "My {person} Did Something And Now I Am Different",
        "The {event} That Changed Everything",
        "I Found {object} And Now I Know Better",
        "The {person} Who Changed My Life Forever",
        "My {person} Did Something And Now I Am Stronger",
        "The {timeframe} That Changed My Path",
        "I Discovered Something About Myself",
        "The {event} That Made Me Who I Am",
        "My {person} Did Something And Now I Understand",
    ],
    "storytime": [
        "This Is The Story Of {event}",
        "My {person} Did Something I Cannot Believe",
        "The {timeframe} That Changed Everything",
        "I Found {object} And Now I Need To Tell You",
        "My {person} Did Something I Never Expected",
        "The {event} That Happened To Me",
        "I Discovered Something And It Changed Everything",
        "The {person} Who Changed My Life",
        "My {person} Did Something And Now I Am Sharing It",
        "The {timeframe} I Will Never Forget",
    ],
    "drama": [
        "My {person} Did Something And Now Everything Is Different",
        "The {event} That Changed Everything",
        "I Found {object} And Now I Cannot Go Back",
        "My {person} Was {action} And I Have The Proof",
        "The {timeframe} That Changed My Life",
        "I Discovered Something And Now I Am Not The Same",
        "The {person} Who Changed My Path",
        "My {person} Did Something And Now I Must Act",
        "The {event} That Changed Everything Forever",
        "I Found {object} And Now I Cannot Forget",
    ],
}


# ─────────────────────────────────────────────────────
# PROMPT TEMPLATES (FORCE JSON-ONLY OUTPUT)
# ─────────────────────────────────────────────────────

PROMPT_TEMPLATES = {
    "title_generation": (
        "You are the #1 YouTube Shorts title copywriter for STORYTIME content. "
        "CRITICAL INSTRUCTION: Output ONLY a valid JSON object. "
        "Do NOT include any 'thinking process', 'analysis', or reasoning text. "
        "The FIRST character of your response MUST be '{'. "
        "Do NOT include any text before or after the JSON. "
        "Return ONLY: {{\"titles\": [\"title1 #shorts\", \"title2 #shorts\", \"title3 #shorts\"]}}"
    ),
    "metadata": (
        "You are a YouTube SEO and algorithm expert for STORYTIME content. "
        "Output ONLY valid JSON with fields: description, tags, hashtags. "
        "Do NOT include any reasoning, explanation, or 'thinking process' text. "
        "The FIRST character MUST be '{'. No additional text after the JSON. "
        "Output format: {{\"description\": \"...\", \"tags\": [...], \"hashtags\": [... ]}}"
    ),
    "tags_hashtags": (
        "You are a YouTube SEO specialist for STORY content. "
        "Output ONLY valid JSON with fields: tags, hashtags. "
        "Do NOT include any reasoning text. The FIRST character MUST be '{'. "
        "No text after the JSON object. Output format: {{\"tags\": [\"tag1\", \"tag2\"], \"hashtags\": [\"#tag1\", \"#tag2\"]}}"
    ),
}


# ─────────────────────────────────────────────────────
# STORY-SPECIFIC TITLE PATTERNS (from StoryForge categories)
# ─────────────────────────────────────────────────────

STORY_TITLE_PATTERNS = {
    "relationship": [
        "My {person} Had Been {action} Behind My Back",
        "I Found {object} And Now My Relationship Is Over",
        "The {timeframe} That Destroyed My Relationship",
        "My {person} Chose {person2} Over Me",
        "I Never Expected {person} Would Do This",
        "The Secret {person} Kept From Me For {timeframe}",
        "My {person} Lied About {something} And I Have Proof",
        "I Lost Everything Because Of {person}",
        "My {person} Was Living A Double Life",
        "The {event} That Changed Everything Between Us",
    ],
    "betrayal": [
        "My {person} Had Been {action} With {person2}",
        "I Found Out My {person} Was {action} The Whole Time",
        "The {person} I Trusted Most {action}",
        "My {person} Betrayed Me In The Worst Way",
        "I Discovered {person} Secret {timeframe} Ago",
        "My {person} {action} Behind My Back For {timeframe}",
        "The {person} I Loved Was Never Who They Seemed",
        "I Found {object} And The Truth Came Out",
        "My {person} {action} And I Have The Proof",
        "The {event} That Exposed {person} Lies",
    ],
    "family": [
        "My {person} Kept A Secret For {timeframe}",
        "I Found Out {person} Was Not Who I Thought",
        "The {event} That Tore My Family Apart",
        "My {person} Did Something I Never Expected",
        "The {timeframe} Secret That Changed Everything",
        "My {person} {action} And Now Nothing Is The Same",
        "I Discovered {person} Hidden {something}",
        "The {event} That Brought My Family Together",
        "My {person} Made A Choice I Cannot Forget",
        "The Truth About {person} Finally Came Out",
    ],
    "mystery": [
        "I Found {object} And Now I Cannot Sleep",
        "The {event} That Nobody Can Explain",
        "Something Was Wrong From The Start",
        "The {person} Who Disappeared Without A Trace",
        "I Discovered {something} And Now I Am Scared",
        "The {event} That Still Haunts Me",
        "Nobody Believed Me Until I Found {object}",
        "The {timeframe} That Changed Everything",
        "I Found Out {something} And It Changed Everything",
        "The {person} Who Was Never Who They Seemed",
    ],
    "workplace": [
        "My {person} Made Me Do Something I Regret",
        "The {event} That Almost Got Me Fired",
        "My {person} Stole My Idea And Got Promoted",
        "I Discovered {person} Secret Plan",
        "The {event} That Ruined My Career",
        "My {person} {action} And I Have The Proof",
        "I Lost My Job Because Of {person}",
        "The {timeframe} That Changed My Career Forever",
        "My {person} Was {action} Behind Everyone Back",
        "The {event} That Exposed Everything",
    ],
    "revenge": [
        "My {person} {action} So I Got Even",
        "The {timeframe} Plan That Worked Perfectly",
        "My {person} Thought They Got Away With {something}",
        "I Got Revenge On {person} And It Was Worth It",
        "The {event} That Made Me Take Action",
        "My {person} {action} And Now They Regret It",
        "I Waited {timeframe} Then Got My Payback",
        "The {person} Who Got Exactly What They Deserved",
        "My {person} {action} So I Made Sure They Paid",
        "The {event} That Changed Everything For {person}",
    ],
    "money": [
        "I Lost ${amount} Because Of {person}",
        "The {event} That Cost Me Everything",
        "My {person} Stole My ${amount}",
        "I Found {object} And It Changed My Life",
        "The {timeframe} Decision That Changed Everything",
        "My {person} {action} And Now I Have Nothing",
        "I Discovered {person} Secret About My Money",
        "The {timeframe} That Changed My Financial Life",
        "My {person} {action} With My Money And I Found Out",
        "The {timeframe} That Made Me A Different Person",
    ],
    "crime": [
        "The {event} That Shook Everyone",
        "I Found {object} And Now The Truth Is Out",
        "The {person} Who Got Away With {something}",
        "My {person} Was {action} And Nobody Knew",
        "The {timeframe} Investigation That Changed Everything",
        "I Found {object} And Now The Police Are Involved",
        "The {event} That Changed Everything",
        "My {person} {action} And Now They Are Gone",
        "The {person} Who Was Not Who They Seemed",
        "I Found {object} And Now The Case Is Open",
    ],
    "wholesome": [
        "My {person} Did Something That Made Me Cry",
        "The {event} That Restored My Faith In Humanity",
        "My {person} Did Something Beautiful",
        "The {timeframe} That Changed My Life Forever",
        "My {person} Surprised Me With Something Special",
        "The {event} That Brought Us All Together",
        "My {person} Did Something I Will Never Forget",
        "The {timeframe} That Changed Everything For The Better",
        "My {person} Did Something Perfect",
        "The {event} That Made Everything Worth It",
    ],
    "horror": [
        "I Saw Something And Now I Cannot Sleep",
        "The {event} That Still Haunts Me",
        "My {person} Did Something That Scared Me",
        "The {timeframe} That Changed Everything",
        "I Found {object} And Now I Wish I Had Not",
        "The {person} Who Was Never Who They Seemed",
        "My {person} Did Something I Cannot Forget",
        "The {event} That Happened One Night",
        "I Discovered Something And Now I Am Not Safe",
        "The {person} Who Still Comes To Me In Dreams",
    ],
    "true_crime": [
        "The {event} That Shook Everyone",
        "I Found {object} And Now The Truth Is Out",
        "The {person} Who Got Away With {something}",
        "My {person} Was {action} And Nobody Knew",
        "The {timeframe} Investigation That Changed Everything",
        "I Discovered Something And Now I Cannot Rest",
        "The {event} That Changed Everything",
        "My {person} {action} And Now They Are Gone",
        "The {person} Who Was Not Who They Seemed",
        "I Found {object} And Now The Case Is Open",
    ],
    "psychology": [
        "The {timeframe} That Changed How I Think",
        "I Discovered Something About My Mind",
        "The {event} That Changed My Perspective",
        "My {person} Did Something That Changed How I See Things",
        "The {timeframe} That Changed Everything",
        "I Found {object} And Now I Understand",
        "The {person} Who Taught Me Something Important",
        "My {person} Did Something And Now I Know Better",
        "The {event} That Changed How I See The World",
        "I Discovered Something About Human Nature",
    ],
    "motivation": [
        "The {timeframe} That Changed My Life",
        "My {person} Did Something And Now I Am Different",
        "The {event} That Changed Everything",
        "I Found {object} And Now I Know Better",
        "The {person} Who Changed My Life Forever",
        "My {person} Did Something And Now I Am Stronger",
        "The {timeframe} That Changed My Path",
        "I Discovered Something About Myself",
        "The {event} That Made Me Who I Am",
        "My {person} Did Something And Now I Understand",
    ],
    "storytime": [
        "This Is The Story Of {event}",
        "My {person} Did Something I Cannot Believe",
        "The {timeframe} That Changed Everything",
        "I Found {object} And Now I Need To Tell You",
        "My {person} Did Something I Never Expected",
        "The {event} That Happened To Me",
        "I Discovered Something And It Changed Everything",
        "The {person} Who Changed My Life",
        "My {person} Did Something And Now I Am Sharing It",
        "The {timeframe} I Will Never Forget",
    ],
    "drama": [
        "My {person} Did Something And Now Everything Is Different",
        "The {event} That Changed Everything",
        "I Found {object} And Now I Cannot Go Back",
        "My {person} Was {action} And I Have The Proof",
        "The {timeframe} That Changed My Life",
        "I Discovered Something And Now I Am Not The Same",
        "The {person} Who Changed My Path",
        "My {person} Did Something And Now I Must Act",
        "The {event} That Changed Everything Forever",
        "I Found {object} And Now I Cannot Forget",
    ],
}


# ─────────────────────────────────────────────────────
# PROMPT-BASED TITLE GENERATION
# ─────────────────────────────────────────────────────

async def _llm_generate_titles(system_prompt: str, user_prompt: str) -> tuple[str, list[str]]:
    """Use LLM to generate 3 YouTube-optimized title options for story content."""
    
    # Use LLM for story-specific title generation
    system = (
        PROMPT_TEMPLATES["title_generation"]
    )
    
    user = (
        f"Generate 3 KILLER titles for this story-based YouTube Short:\n\n"
        f"TOPIC: {user_prompt}\n"
    )
    
    result = await nvidia_client.generate_structured(system, user, schema_key="draft")
    
    if result and isinstance(result, dict) and "titles" in result:
        titles = [t.strip() for t in result["titles"] if isinstance(t, str)][:3]
        if titles:
            return titles[0], titles[1:]
    
    # Fallback: use story-specific patterns
    patterns = STORY_TITLE_PATTERNS.get("storytime", STORY_TITLE_PATTERNS["storytime"])
    selected = random.sample(patterns, min(3, len(patterns)))
    titles = [random.choice(patterns) for _ in range(3)]
    return titles[0], titles[1:]


async def _llm_generate_description(system_prompt: str, user_prompt: str) -> str:
    """Use LLM to generate a rich YouTube description optimized for story content."""
    
    # Use the forced JSON prompt
    system = PROMPT_TEMPLATES["metadata"]
    
    user = (
        f"Write a HIGH-CONVERTING YouTube Shorts description for this STORY:\n\n"
        f"TITLE: {user_prompt}\n"
        f"NICHE: storytime\n"
        f"STORYTIME: personal, engaging, conversational. Real stories from real people.\n\n"
    )
    
    result = await nvidia_client.generate_structured(system, user, schema_key="draft")
    
    if result and isinstance(result, dict):
        desc = result.get("description", "")
        if desc and len(desc.strip()) > 50:
            return desc.strip()
    
    # Fallback: story-specific description
    return (
        f"Wait... what?! {user_prompt}\n\n"
        f"This story will leave you speechless. "
        f"What it reveals about human nature is shocking.\n\n"
        f"Would you have done the same thing? Drop a comment below!\n\n"
        f"Like & Subscribe for more incredible stories!\n\n"
        f"#storytime #shorts #viral #facts"
    )


async def _llm_generate_tags_and_hashtags(system_prompt: str, user_prompt: str) -> tuple[list[str], list[str]]:
    """Use LLM to generate SEO-optimized tags and hashtags for story content."""
    
    system = PROMPT_TEMPLATES["tags_hashtags"]
    
    user = (
        f"Generate tags and hashtags for this STORYTIME YouTube Short:\n\n"
        f"TITLE: {user_prompt}\n"
        f"NICHE: storytime\n\n"
    )
    
    result = await nvidia_client.generate_structured(system, user, schema_key="draft")
    
    tags = []
    hashtags = []
    
    if result:
        if isinstance(result, dict):
            tags = [t.lower().strip() for t in result.get("tags", []) if isinstance(t, str)][:20]
            hashtags = [h.lower().strip("# ") for h in result.get("hashtags", []) if isinstance(h, str)][:8]
        elif isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    if "tags" in item:
                        tags = [t.lower().strip() for t in item["tags"] if isinstance(t, str)][:20]
                    if "hashtags" in item:
                        hashtags = [h.lower().strip("# ") for h in item["hashtags"] if isinstance(h, str)][:8]
                    break
    
    # Ensure minimum tags
    if len(tags) < 5:
        tags = ["story", "drama", "viral", "shorts", "facts"]
    
    # Ensure hashtags
    if len(hashtags) < 3:
        hashtags = ["#storytime", "#shorts", "#viral"]
    
    return tags, hashtags


async def generate_metadata(
    topic: str,
    niche: str,
    title_override: str | None = None,
    timestamps: dict[str, str] | None = None,
    script_text: str | None = None,
) -> GeneratedMetadata:
    """Generate AI-powered YouTube metadata for a story-based video."""
    
    niche_style = NICHE_CONTEXT.get(niche, NICHE_CONTEXT["storytime"])
    
    if title_override:
        title = title_override
        title_options = []
    else:
        title, title_options = await _llm_generate_titles(topic, niche)
    
    # Ensure title has #shorts for YouTube Shorts
    if "#shorts" not in title.lower():
        title = f"{title.rstrip()} #shorts"
    
    description = await _llm_generate_description(topic, niche)
    tags, hashtags = await _llm_generate_tags_and_hashtags(topic, niche)
    
    # Ensure tags include shorts-related tags
    if "shorts" not in [t.lower() for t in tags]:
        tags.append("shorts")
    if "#shorts" not in hashtags:
        hashtags.append("#shorts")
    
    return GeneratedMetadata(
        title=title,
        description=description,
        tags=tags,
        hashtags=hashtags,
        title_options=title_options,
        category_id=CATEGORY_MAP.get(niche, "22"),
    )