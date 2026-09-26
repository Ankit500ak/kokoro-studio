"""
Enhanced Prosody Engine
=======================
Advanced text-to-prosody mapping for super-realistic TTS output.

This engine analyzes text semantically and applies:
  - Context-aware pacing (speed variation within sentences)
  - Emotional emphasis mapping (which words to stress)
  - Pause insertion (micro-pauses for breathing and dramatic effect)
  - Intonation shaping (via punctuation and caps modulation)
  - Phrase-level rhythm control
"""

import re
import logging
from typing import Optional

log = logging.getLogger(__name__)


# ============================================================================
# EMPHASIS WORD DATABASE
# ============================================================================

# Words that should be emphasized in different emotional contexts
EMPHASIS_DB = {
    'high_energy': {
        'words': [
            'never', 'always', 'everyone', 'nothing', 'everything',
            'impossible', 'suddenly', 'finally', 'unexpected', 'discovered',
            'realized', 'unbelievable', 'incredible', 'shocking', 'stunning',
            'amazing', 'insane', 'wild', 'crazy', 'epic', 'legendary',
            'mind-blowing', 'unreal', 'phenomenal', 'extraordinary',
        ],
        'intensity': 1.3,
    },
    'emotional': {
        'words': [
            'love', 'hate', 'fear', 'hope', 'trust', 'betrayal',
            'heart', 'soul', 'forever', 'never', 'always', 'gone',
            'lost', 'found', 'dream', 'nightmare', 'alive', 'dead',
            'beautiful', 'terrifying', 'haunting', 'mysterious',
        ],
        'intensity': 1.2,
    },
    'dramatic': {
        'words': [
            'secret', 'truth', 'mystery', 'danger', 'death', 'survive',
            'shadow', 'blood', 'cold', 'warm', 'dark', 'light',
            'silence', 'whisper', 'scream', 'running', 'alone', 'together',
            'disappeared', 'vanished', 'hidden', 'revealed',
        ],
        'intensity': 1.25,
    },
}

# Contextual emphasis patterns (phrases that should be emphasized together)
PHRASE_EMPHASIS = [
    (r'\bthe truth is\b', 'dramatic'),
    (r'\bhere\'s the thing\b', 'dramatic'),
    (r'\bnobody expected\b', 'high_energy'),
    (r'\byou won\'t believe\b', 'high_energy'),
    (r'\bwhat happened next\b', 'dramatic'),
    (r'\blittle did\b', 'dramatic'),
    (r'\bat the end of the day\b', 'emotional'),
    (r'\bwhen it comes down to\b', 'dramatic'),
]


# ============================================================================
# PAUSE MARKERS
# ============================================================================

# Micro-pause insertion rules — Short natural pauses
PAUSE_RULES = {
    'after_comma': 0.06,      # 60ms after commas
    'after_period': 0.10,     # 100ms after periods
    'after_question': 0.12,   # 120ms after questions
    'after_exclamation': 0.08,# 80ms after exclamations
    'after_ellipsis': 0.15,   # 150ms after ellipsis
    'before_emphasis': 0.04,  # 40ms before emphasized words
    'between_clauses': 0.08,  # 80ms between clauses
    'breath_pause': 0.12,     # 120ms for breath pauses
}


# ============================================================================
# INTONATION PATTERNS
# ============================================================================

INTONATION_SHAPES = {
    'statement': {
        'end_punct': '.',
        'contour': 'falling',
    },
    'question': {
        'end_punct': '?',
        'contour': 'rising',
    },
    'exclamation': {
        'end_punct': '!',
        'contour': 'high_fall',
    },
    'suspense': {
        'end_punct': '...',
        'contour': 'level',
    },
    'soft': {
        'end_punct': '.',
        'contour': 'gentle_fall',
    },
}


class ProsodyEngine:
    """Advanced prosody engine for natural speech synthesis."""

    def __init__(self):
        self.emphasis_db = EMPHASIS_DB
        self.phrase_emphasis = PHRASE_EMPHASIS
        self.max_words_per_sentence = 15

    def fragment_long_sentences(self, text: str) -> str:
        """
        Break up long sentences (>15 words) at natural pause points.
        Improves TTS flow and reduces robotic delivery.
        """
        if not text or not text.strip():
            return text

        sentences = self._split_sentences(text)
        fragmented = []

        for sentence in sentences:
            words = sentence.split()
            if len(words) <= self.max_words_per_sentence:
                fragmented.append(sentence)
                continue

            # Find break points: commas, semicolons, conjunctions
            fragments = self._find_break_points(sentence)
            fragmented.extend(fragments)

        return ' '.join(fragmented)

    def _find_break_points(self, sentence: str) -> list[str]:
        """Find natural break points in a long sentence."""
        words = sentence.split()
        fragments = []
        current_chunk = []

        for i, word in enumerate(words):
            current_chunk.append(word)

            # Check if we should break here
            should_break = False
            word_lower = word.lower().rstrip('.,;:!?')

            # Break at commas (if chunk is long enough)
            if word.endswith(',') and len(current_chunk) >= 5:
                should_break = True

            # Break at semicolons
            if word.endswith(';') and len(current_chunk) >= 4:
                should_break = True

            # Break at conjunctions if chunk is getting long
            conjunctions = {'and', 'but', 'or', 'yet', 'so', 'because', 'although', 'while', 'when', 'after', 'before', 'if', 'unless', 'since', 'though', 'however', 'therefore', 'moreover', 'furthermore'}
            if word_lower in conjunctions and len(current_chunk) >= 6:
                should_break = True

            # Force break if chunk exceeds max words
            if len(current_chunk) >= self.max_words_per_sentence:
                should_break = True

            if should_break and current_chunk:
                fragment = ' '.join(current_chunk).strip()
                # Ensure proper ending punctuation
                if fragment and fragment[-1] not in '.!?;':
                    # Check if next word exists and is lowercase (continuation)
                    if i + 1 < len(words) and words[i + 1][0].islower():
                        fragment += ','
                fragments.append(fragment)
                current_chunk = []

        # Don't forget remaining words
        if current_chunk:
            fragments.append(' '.join(current_chunk))

        return fragments

    def analyze_and_enhance(
        self,
        text: str,
        emotion: str = 'neutral',
        emotion_score: float = 0.0,
        preset: str = 'storytelling',
    ) -> str:
        """
        Analyze text and apply prosody enhancements.
        First fragments long sentences, then applies emphasis and punctuation.
        """
        if not text or not text.strip():
            return text

        # Step 1: Fragment long sentences
        text = self.fragment_long_sentences(text)

        # Step 2: Split into sentences
        sentences = self._split_sentences(text)
        enhanced_sentences = []

        for sentence in sentences:
            enhanced = self._enhance_sentence(sentence, emotion, emotion_score, preset)
            enhanced_sentences.append(enhanced)

        return ' '.join(enhanced_sentences)

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Split on sentence-ending punctuation followed by space
        parts = re.split(r'(?<=[.!?])\s+', text.strip())
        return [p.strip() for p in parts if p.strip()]

    def _enhance_sentence(
        self,
        sentence: str,
        emotion: str,
        emotion_score: float,
        preset: str,
    ) -> str:
        """Enhance a single sentence with prosody markers."""
        if not sentence:
            return sentence

        # 1. Apply emphasis to key words
        sentence = self._apply_emphasis(sentence, emotion, emotion_score)

        # 2. Apply phrase-level emphasis
        sentence = self._apply_phrase_emphasis(sentence)

        # 3. Apply emotional punctuation
        sentence = self._apply_emotional_punctuation(sentence, emotion, emotion_score)

        # 4. Ensure proper ending
        sentence = self._ensure_ending(sentence, emotion)

        return sentence

    def _apply_emphasis(self, sentence: str, emotion: str, score: float) -> str:
        """Apply word-level emphasis based on emotion and context."""
        if score < 1.0:
            return sentence

        # Determine which emphasis category to use
        emphasis_categories = {
            'excitement': 'high_energy',
            'joy': 'high_energy',
            'anger': 'emotional',
            'fear': 'dramatic',
            'sadness': 'emotional',
            'surprise': 'high_energy',
            'suspense': 'dramatic',
            'tension': 'dramatic',
            'romance': 'emotional',
            'wisdom': 'dramatic',
        }

        category = emphasis_categories.get(emotion, 'dramatic')
        emphasis_info = self.emphasis_db.get(category, {})
        words_to_emphasize = emphasis_info.get('words', [])
        intensity = emphasis_info.get('intensity', 1.0)

        if not words_to_emphasize:
            return sentence

        # Find and emphasize words (max 1-2 per sentence for naturalness)
        emphasized_count = 0
        max_emphasis = 1 if score < 2.5 else 2

        for word in words_to_emphasize:
            if emphasized_count >= max_emphasis:
                break

            pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
            match = pattern.search(sentence)
            if match:
                # Apply emphasis via caps (Kokoro reads caps with emphasis)
                if intensity >= 1.2:
                    replacement = word.upper()
                else:
                    replacement = word.capitalize()
                sentence = pattern.sub(replacement, sentence, count=1)
                emphasized_count += 1

        return sentence

    def _apply_phrase_emphasis(self, sentence: str) -> str:
        """Apply emphasis to known dramatic phrases."""
        for pattern, category in self.phrase_emphasis:
            match = re.search(pattern, sentence, re.IGNORECASE)
            if match:
                phrase = match.group(0)
                # Emphasize the phrase
                emphasized = phrase.upper() if len(phrase.split()) <= 3 else phrase
                sentence = sentence[:match.start()] + emphasized + sentence[match.end():]
                break  # Only one phrase emphasis per sentence

        return sentence

    def _apply_emotional_punctuation(self, sentence: str, emotion: str, score: float) -> str:
        """Apply emotion-appropriate punctuation."""
        if score < 1.5:
            return sentence

        # Remove existing ending punctuation
        s = sentence.rstrip()
        if s and s[-1] in '.!?…':
            s = s[:-1].rstrip()

        if not s:
            return sentence

        # Apply emotion-specific ending — NO ... for fear/tension (fast, breathless speech)
        emotion_endings = {
            'fear': ('.', 2.0),        # Period, not ... — no trailing pause
            'suspense': ('.', 2.0),    # Period — keep moving
            'tension': ('.', 2.0),     # Period — no pause
            'sadness': ('.', 2.0),     # Period
            'romance': ('.', 1.5),     # Period
            'joy': ('!', 1.5),
            'excitement': ('!', 2.0),
            'anger': ('!', 2.5),
            'surprise': ('!', 2.0),
            'wisdom': ('.', 1.5),
        }

        ending_info = emotion_endings.get(emotion)
        if ending_info:
            ending, min_score = ending_info
            if score >= min_score:
                s += ending
                return s

        # Default: ensure ending punctuation
        if s and s[-1] not in '.!?…':
            s += '.'

        return s

    def _ensure_ending(self, sentence: str, emotion: str) -> str:
        """Ensure sentence has proper ending punctuation."""
        s = sentence.rstrip()
        if not s:
            return s

        # If already has ending punctuation, keep it
        if s[-1] in '.!?…':
            return s

        # Add appropriate ending based on emotion — NO ... for fear/tension (breathless)
        if emotion in ('sadness', 'romance'):
            return s + '...'
        elif emotion in ('joy', 'excitement', 'anger', 'surprise'):
            return s + '!'
        else:
            return s + '.'

    def get_pause_duration(
        self,
        before_text: str,
        after_text: str,
        emotion: str = 'neutral',
        preset: str = 'storytelling',
    ) -> float:
        """
        Calculate appropriate pause duration between phrases.

        Returns pause duration in seconds.
        """
        # Base pause from punctuation
        pause = 0.0

        if before_text:
            last_char = before_text.rstrip()[-1] if before_text.rstrip() else ''

            if last_char == ',':
                pause = PAUSE_RULES['after_comma']
            elif last_char == '.':
                pause = PAUSE_RULES['after_period']
            elif last_char == '?':
                pause = PAUSE_RULES['after_question']
            elif last_char == '!':
                pause = PAUSE_RULES['after_exclamation']
            elif last_char == '…':
                pause = PAUSE_RULES['after_ellipsis']
            else:
                pause = PAUSE_RULES['between_clauses']

        # Emotion-based adjustment — TENSE = SHORT pauses (fast, breathless speech)
        emotion_pause_mult = {
            'fear': 0.4,        # Very short — panicked, breathless
            'suspense': 0.5,    # Short — keeping momentum
            'tension': 0.4,     # Very short — edge of seat
            'sadness': 1.3,     # Longer — heavy pauses
            'romance': 1.2,
            'joy': 0.7,
            'excitement': 0.6,
            'anger': 0.5,       # Short — sharp delivery
            'surprise': 0.6,
            'wisdom': 1.1,
        }

        mult = emotion_pause_mult.get(emotion, 1.0)
        pause *= mult

        # Preset adjustment
        preset_mult = {
            'horror': 1.3,
            'mystery': 1.2,
            'romantic': 1.1,
            'shorts': 0.7,
            'news': 0.8,
        }

        pause *= preset_mult.get(preset, 1.0)

        return pause

    def detect_prosody_style(self, text: str) -> str:
        """Auto-detect the best prosody style for a text."""
        text_lower = text.lower()
        word_count = len(text_lower.split())

        # Check for dramatic content
        dramatic_markers = ['secret', 'truth', 'mystery', 'suddenly', 'never expected']
        dramatic_count = sum(1 for m in dramatic_markers if m in text_lower)

        # Check for emotional content
        emotional_markers = ['love', 'hate', 'fear', 'hope', 'dream', 'nightmare']
        emotional_count = sum(1 for m in emotional_markers if m in text_lower)

        # Check for informational content
        info_markers = ['according to', 'research shows', 'study found', 'data indicates']
        info_count = sum(1 for m in info_markers if m in text_lower)

        # Determine style
        if dramatic_count >= 2:
            return 'dramatic'
        elif emotional_count >= 2:
            return 'emotional'
        elif info_count >= 1:
            return 'informational'
        elif word_count < 15:
            return 'punchy'
        else:
            return 'narrative'


# Singleton
prosody_engine = ProsodyEngine()
