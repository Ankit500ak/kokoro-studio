import logging
from kokoro import KPipeline
import soundfile as sf
import uuid
import json
import re
import torch
from pathlib import Path
from ..core.config import settings
from .audio_enhancer import audio_enhancer
from .prosody_engine import prosody_engine
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

log = logging.getLogger(__name__)


# ============================================================================
# AUDIO SMOOTHING - SIMPLE AND SAFE
# ============================================================================

def _crossfade_audio(chunks, fade_samples: int = 960) -> torch.Tensor:
    """Concatenate audio chunks with smooth crossfade to avoid clicks/pops."""
    if isinstance(chunks, torch.Tensor):
        return chunks
    
    if not isinstance(chunks, list) or len(chunks) == 0:
        return torch.tensor([])
    
    if len(chunks) == 1:
        return chunks[0] if isinstance(chunks[0], torch.Tensor) else torch.tensor([])
    
    result = chunks[0]
    for i in range(1, len(chunks)):
        chunk = chunks[i]
        if not isinstance(chunk, torch.Tensor) or not isinstance(result, torch.Tensor):
            continue
        
        overlap = min(fade_samples, len(result) // 4, len(chunk) // 4)
        
        if overlap <= 0:
            result = torch.cat([result, chunk])
            continue
        
        # Smooth crossfade using equal-power curve
        fade_out = torch.linspace(1.0, 0.0, overlap) ** 0.5
        fade_in = torch.linspace(0.0, 1.0, overlap) ** 0.5
        
        # Apply fades
        result[-overlap:] *= fade_out
        chunk[:overlap] *= fade_in
        
        # Concatenate with overlapped sum
        result = torch.cat([result[:-overlap], result[-overlap:] + chunk[:overlap], chunk[overlap:]])
    
    return result


def _safe_audio_output(audio: torch.Tensor) -> torch.Tensor:
    """Post-process audio for natural sound.
    
    1. Remove DC offset
    2. Soft clipping
    3. Normalize
    """
    if audio.numel() == 0:
        return audio
    
    # Remove DC offset
    audio = audio - audio.mean()
    
    # Soft clipping — tanh-based
    audio = torch.tanh(audio * 0.95) / torch.tanh(torch.tensor(0.95))
    
    # Normalize to -3dB peak
    peak = audio.abs().max()
    if peak > 0.01:
        audio = audio * (0.7 / peak)
    
    # Final safety clip
    audio = torch.clamp(audio, -1.0, 1.0)
    
    return audio


def _pitch_shift_up(audio: torch.Tensor, semitones: float = 0.5) -> torch.Tensor:
    """Disabled — pitch shifting distorts pronunciation and formants."""
    return audio


# ============================================================================
# ADVANCED TEXT NORMALIZATION - Numbers, Dates, Abbreviations, Special Chars
# ============================================================================

ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
        'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
        'seventeen', 'eighteen', 'nineteen']
TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
THOUSANDS = ['', 'thousand', 'million', 'billion', 'trillion']

ABBREVIATIONS = {
    'mr.': 'Mister', 'mrs.': 'Missus', 'ms.': 'Miss', 'dr.': 'Doctor',
    'prof.': 'Professor', 'sr.': 'Senior', 'jr.': 'Junior',
    'st.': 'Saint', 'ave.': 'Avenue', 'blvd.': 'Boulevard',
    'dept.': 'Department', 'est.': 'Established', 'approx.': 'approximately',
    'approx': 'approximately', 'govt.': 'government', 'govt': 'government',
    'inc.': 'incorporated', 'ltd.': 'limited', 'corp.': 'corporation',
    'vs.': 'versus', 'etc.': 'etcetera', 'i.e.': 'that is',
    'e.g.': 'for example', 'no.': 'number', 'nos.': 'numbers',
    'jan.': 'January', 'feb.': 'February', 'mar.': 'March',
    'apr.': 'April', 'jun.': 'June', 'jul.': 'July',
    'aug.': 'August', 'sep.': 'September', 'oct.': 'October',
    'nov.': 'November', 'dec.': 'December',
    'mon.': 'Monday', 'tue.': 'Tuesday', 'wed.': 'Wednesday',
    'thu.': 'Thursday', 'fri.': 'Friday', 'sat.': 'Saturday', 'sun.': 'Sunday',
    'ft.': 'feet', 'in.': 'inches', 'lb.': 'pounds', 'lbs.': 'pounds',
    'oz.': 'ounces', 'qt.': 'quarts', 'gal.': 'gallons',
    'mph': 'miles per hour', 'km/h': 'kilometers per hour',
    'kg': 'kilograms', 'cm': 'centimeters', 'mm': 'millimeters',
    # Tech abbreviations — spell out with periods for clear pronunciation
    'html': 'H.T.M.L.', 'css': 'C.S.S.', 'js': 'J.S.',
    'ai': 'A.I.', 'api': 'A.P.I.', 'url': 'U.R.L.',
    'usb': 'U.S.B.', 'gps': 'G.P.S.', 'tv': 'T.V.',
    'pc': 'P.C.', 'ok': 'okay', 'ok.': 'okay',
    'vs': 'versus', 'etc': 'etcetera',
    'dc': 'D.C.', 'la': 'L.A.', 'ny': 'N.Y.', 'sf': 'S.F.',
    'ios': 'I.O.S.', 'os': 'O.S.', 'vr': 'V.R.',
    'qr': 'Q.R.', 'pdf': 'P.D.F.', 'mp3': 'M.P.3.',
    'ceo': 'C.E.O.', 'cfo': 'C.F.O.', 'cta': 'C.T.A.',
    'rpm': 'R.P.M.', 'led': 'L.E.D.', 'ai': 'A.I.',
    'id': 'I.D.', 'app': 'app', 'apps': 'apps',
    'email': 'email', 'wifi': 'Wi-Fi', 'ai': 'A.I.',
}

MONTH_NAMES = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April',
    5: 'May', 6: 'June', 7: 'July', 8: 'August',
    9: 'September', 10: 'October', 11: 'November', 12: 'December'
}


def _number_to_words(n: int) -> str:
    if n == 0:
        return 'zero'
    if n < 0:
        return 'minus ' + _number_to_words(-n)
    
    chunks = []
    while n > 0:
        n, remainder = divmod(n, 1000)
        chunks.append(remainder)
    
    parts = []
    for i, remainder in enumerate(reversed(chunks)):
        idx = len(chunks) - 1 - i
        if remainder == 0:
            continue
        chunk_words = []
        if remainder >= 100:
            chunk_words.append(ONES[remainder // 100])
            chunk_words.append('hundred')
            remainder %= 100
        if remainder >= 20:
            chunk_words.append(TENS[remainder // 10])
            if remainder % 10:
                chunk_words.append(ONES[remainder % 10])
        elif remainder > 0:
            chunk_words.append(ONES[remainder])
        if idx > 0:
            chunk_words.append(THOUSANDS[idx])
        parts.extend(chunk_words)
    
    return ' '.join(parts)


def _normalize_numbers(text: str) -> str:
    """Convert numbers to spoken words for natural pronunciation."""
    
    def replace_ordinal(match):
        num = int(match.group(1))
        words = _number_to_words(num)
        if num % 100 in (11, 12, 13):
            return words + 'th'
        elif num % 10 == 1:
            return words + 'st'
        elif num % 10 == 2:
            return words + 'nd'
        elif num % 10 == 3:
            return words + 'rd'
        return words + 'th'
    
    def replace_cardinal(match):
        num = int(match.group(0).replace(',', ''))
        return _number_to_words(num)
    
    def replace_decimal(match):
        full = match.group(0)
        whole_str, decimal_part = full.split('.')
        whole = int(whole_str)
        whole_words = _number_to_words(whole) if whole != 0 else 'zero'
        decimal_words = ' '.join(ONES[int(d)] for d in decimal_part)
        return f'{whole_words} point {decimal_words}'
    
    def replace_percentage(match):
        num = float(match.group(1))
        if num == int(num):
            words = _number_to_words(int(num))
        else:
            words = str(num)
        return f'{words} percent'
    
    def replace_time(match):
        hour = int(match.group(1))
        minute = int(match.group(2))
        hour_word = _number_to_words(hour) if hour != 0 else 'twelve'
        if minute == 0:
            return f"{hour_word} o'clock"
        elif minute < 10:
            return f"{hour_word} oh {_number_to_words(minute)}"
        else:
            return f"{hour_word} {_number_to_words(minute)}"
    
    def replace_date_slash(match):
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        month_name = MONTH_NAMES.get(month, _number_to_words(month))
        if year > 100:
            year_str = _number_to_words(year)
        else:
            year_str = _number_to_words(2000 + year) if year < 100 else _number_to_words(year)
        return f"{month_name} {_number_to_words(day)}, {year_str}"
    
    def replace_date_dash(match):
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        month_name = MONTH_NAMES.get(month, _number_to_words(month))
        return f"{month_name} {_number_to_words(day)}, {_number_to_words(year)}"
    
    def replace_phone(match):
        parts = match.groups()
        if parts[2]:  # (XXX) XXX-XXXX
            return f"{_number_to_words(int(parts[0]))} {_number_to_words(int(parts[1]))} {_number_to_words(int(parts[2]))}"
        elif parts[4]:  # XXX-XXX-XXXX
            return f"{_number_to_words(int(parts[3]))} {_number_to_words(int(parts[4]))} {_number_to_words(int(parts[5]))}"
        return match.group(0)
    
    def replace_money(match):
        symbol = match.group(1) or ''
        amount = match.group(2)
        currency = 'dollars' if symbol == '$' else 'euros' if symbol == '€' else 'pounds' if symbol == '£' else symbol
        
        # Remove commas for parsing
        amount_clean = amount.replace(',', '')
        
        if '.' in amount_clean:
            parts = amount_clean.split('.')
            whole_str = parts[0]
            cents_str = parts[1] if len(parts) > 1 else '0'
            
            whole_num = int(whole_str) if whole_str else 0
            cents_num = int(cents_str) if cents_str else 0
            
            if cents_num == 0:
                return f"{_number_to_words(whole_num)} {currency}"
            return f"{_number_to_words(whole_num)} {currency} and {_number_to_words(cents_num)} cents"
        
        num = int(amount_clean) if amount_clean else 0
        return f"{_number_to_words(num)} {currency}"
    
    def replace_fraction(match):
        numerator = int(match.group(1))
        denominator = int(match.group(2))
        special = {2: 'half', 3: 'third', 4: 'quarter', 5: 'fifth',
                   6: 'sixth', 7: 'seventh', 8: 'eighth', 9: 'ninth', 10: 'tenth'}
        if denominator in special:
            den_word = special[denominator]
        else:
            den_word = _number_to_words(denominator) + 'ths'
        if numerator == 1:
            return f'a {den_word}'
        return f"{_number_to_words(numerator)} {den_word}s"
    
    def replace_range(match):
        start = int(match.group(1))
        end = int(match.group(2))
        return f"from {_number_to_words(start)} to {_number_to_words(end)}"
    
    def replace_year(match):
        year = int(match.group(0))
        if 1000 <= year <= 2099:
            if year % 100 == 0:
                return _number_to_words(year // 100) + ' hundred'
            elif year % 100 < 10:
                return f"{_number_to_words(year // 100)} oh {_number_to_words(year % 100)}"
            else:
                first_two = year // 100
                last_two = year % 100
                return f"{_number_to_words(first_two)} {_number_to_words(last_two)}"
        return _number_to_words(year)
    
    # Order matters - more specific patterns first
    text = re.sub(r'\b(\d{1,2}):(\d{2})\b', replace_time, text)
    text = re.sub(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', replace_date_slash, text)
    text = re.sub(r'(\d{4})-(\d{1,2})-(\d{1,2})', replace_date_dash, text)
    text = re.sub(r'(\(?\d{3}\)?)[\s.\-]?(\d{3})[\s.\-]?(\d{4})', replace_phone, text)
    text = re.sub(r'([$€£])(\d[\d,]*\.?\d*)', replace_money, text)
    text = re.sub(r'(\d+)\s*/\s*(\d+)', replace_fraction, text)
    text = re.sub(r'(\d+)\s*[-–]\s*(\d+)', replace_range, text)
    text = re.sub(r'(\d+(?:\.\d+)?)%', replace_percentage, text)
    text = re.sub(r'(\d+\.\d+)', replace_decimal, text)
    text = re.sub(r'\b(\d{1,2})(st|nd|rd|th)\b', replace_ordinal, text)
    text = re.sub(r'\b\d[\d,]*\b', replace_cardinal, text)
    
    return text


def _normalize_abbreviations(text: str) -> str:
    """Expand abbreviations for natural pronunciation."""
    words = text.split()
    result = []
    for i, word in enumerate(words):
        lower = word.lower().strip('.,!?;:')
        punctuation = ''
        if word and word[-1] in '.,!?;:':
            punctuation = word[-1]
            word = word[:-1]
            lower = word.lower()
        
        if lower in ABBREVIATIONS:
            result.append(ABBREVIATIONS[lower] + punctuation)
        else:
            result.append(word if punctuation == '' else word + punctuation)
    
    return ' '.join(result)


def _normalize_special_characters(text: str) -> str:
    """Convert special characters to spoken equivalents."""
    replacements = {
        '&': ' and ',
        '@': ' at ',
        '#': ' number ',
        '%': ' percent ',
        '+': ' plus ',
        '=': ' equals ',
        '<': ' less than ',
        '>': ' greater than ',
        '*': ' ',
        '~': ' ',
        '|': ' ',
        '\\': ' ',
        '/': ' ',
        '_': ' ',
        '`': ' ',
        '^': ' ',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _normalize_contractions(text: str) -> str:
    """Keep contractions natural — do NOT expand them.
    
    Contractions like "don't", "can't", "it's" sound far more natural
    in TTS than "do not", "cannot", "it is". Only expand when the
    contraction is ambiguous or mispronounced by the model.
    """
    # Only fix ambiguous cases that the model mispronounces
    fixes = {
        "gonna": "going to",
        "wanna": "want to",
        "gotta": "got to",
        "kinda": "kind of",
        "sorta": "sort of",
        "dunno": "don't know",
        "lemme": "let me",
        "gimme": "give me",
        "hafta": "have to",
        "woulda": "would have",
        "coulda": "could have",
        "shoulda": "should have",
        "mighta": "might have",
        "musta": "must have",
    }
    
    text_lower = text.lower()
    for slang, proper in fixes.items():
        text_lower = text_lower.replace(slang, proper)
    
    # Fix capitalization of 'i' to 'I', preserve other casing
    words = text_lower.split()
    original_words = text.split()
    result = []
    for i, word in enumerate(words):
        if word == 'i':
            result.append('I')
        elif i < len(original_words) and original_words[i][0:1].isupper():
            result.append(word.capitalize() if word else word)
        else:
            result.append(word)
    
    return ' '.join(result)


def _normalize_text_comprehensive(text: str) -> str:
    """Master normalization function that runs all text normalization steps."""
    text = _normalize_special_characters(text)
    text = _normalize_contractions(text)
    text = _normalize_abbreviations(text)
    text = _normalize_numbers(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============================================================================
# BREATH PAUSE SIMULATION
# ============================================================================

def _add_breath_pauses(text: str) -> str:
    """Leave text unchanged.
    
    KEY PRINCIPLE: Don't add '...' or split sentences.
    The model handles breathing naturally.
    """
    return text


# ============================================================================
# DIALOGUE AND QUOTE HANDLING
# ============================================================================

def _handle_dialogue(text: str) -> str:
    """Minimal dialogue processing - preserve original punctuation.
    
    KEY PRINCIPLE: Don't add markers, just clean up special characters.
    """
    # Normalize em-dash variations
    text = text.replace('—', ' - ')
    text = text.replace('–', ' - ')
    
    # Normalize ellipsis
    text = re.sub(r'\.{4,}', '...', text)
    
    return text


# ============================================================================
# ADVANCED PUNCTUATION-TO-PROSODY MAPPING
# ============================================================================

def _process_advanced_punctuation(text: str) -> str:
    """Minimal punctuation processing - just clean up, don't add markers.
    
    KEY PRINCIPLE: Preserve the original punctuation as much as possible.
    Only normalize multiple punctuation marks.
    """
    # Multiple exclamation marks -> single
    text = re.sub(r'!{2,}', '!', text)
    
    # Multiple question marks -> single
    text = re.sub(r'\?{2,}', '?', text)
    
    # Normalize ellipsis variations
    text = re.sub(r'…{2,}', '...', text)
    text = re.sub(r'\.{4,}', '...', text)
    
    return text


def _count_syllables(word: str) -> int:
    """Estimate syllable count for a word (used for pacing).
    
    Uses a heuristic approach based on vowel patterns.
    Good enough for pacing decisions without a dictionary.
    """
    word = word.lower().strip('.,!?;:')
    if not word:
        return 0
    
    # Special cases
    if len(word) <= 2:
        return 1
    
    # Count vowel groups
    vowels = 'aeiouy'
    count = 0
    prev_vowel = False
    
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    
    # Adjust for silent e
    if word.endswith('e') and not word.endswith('le') and count > 1:
        count -= 1
    
    # Adjust for -ed ending (usually one syllable)
    if word.endswith('ed') and not word.endswith('ted') and not word.endswith('ded') and count > 1:
        count -= 1
    
    return max(1, count)


def _sentence_syllable_count(sentence: str) -> int:
    """Count total syllables in a sentence."""
    words = sentence.split()
    return sum(_count_syllables(w) for w in words)


def _calculate_adaptive_speed(text: str, base_speed: float, emotion: str) -> float:
    """Calculate adaptive speed based on content complexity.
    
    Slows down for:
    - Complex sentences with many syllables
    - Technical or unfamiliar words
    - Emotionally heavy content
    
    Speeds up for:
    - Simple, familiar words
    - Excitement or urgency
    - Short, punchy sentences
    """
    words = text.split()
    word_count = len(words)
    syllable_count = _sentence_syllable_count(text)
    
    # Average syllables per word
    avg_syllables = syllable_count / max(word_count, 1)
    
    # Base adjustment from syllable density
    if avg_syllables > 2.0:
        # Complex words - slow down
        speed_adj = -0.05
    elif avg_syllables > 1.5:
        # Moderately complex
        speed_adj = -0.02
    elif avg_syllables < 1.2:
        # Simple words - can speed up slightly
        speed_adj = +0.02
    else:
        speed_adj = 0.0
    
    # Emotion-based adjustment — TENSE = FASTER (breathless, panicked speech)
    emotion_speed_mods = {
        'fear': +0.12,        # FAST — panicked, words tumble out
        'suspense': +0.06,    # Slightly faster — building momentum
        'tension': +0.10,     # FAST — edge of seat urgency
        'sadness': -0.03,     # Slightly slower
        'romance': -0.02,
        'anger': +0.08,       # Fast — sharp delivery
        'excitement': +0.08,
        'joy': +0.05,
        'humor': +0.06,
        'wisdom': -0.02,
        'surprise': +0.04,
        'neutral': 0.0,
    }
    speed_adj += emotion_speed_mods.get(emotion, 0.0)
    
    # Length-based adjustment (very long sentences slow down slightly)
    if word_count > 30:
        speed_adj -= 0.02
    elif word_count > 20:
        speed_adj -= 0.01
    
    final_speed = base_speed + speed_adj
    return max(settings.MIN_SPEED, min(settings.MAX_SPEED, final_speed))


EMPHASIS_WORDS = {
    'never', 'always', 'everyone', 'nothing', 'everything', 'impossible',
    'suddenly', 'finally', 'unexpected', 'discovered', 'realized',
    'dark', 'light', 'silence', 'whisper', 'scream', 'running',
    'alone', 'together', 'forever', 'gone', 'disappeared', 'truth',
    'secret', 'danger', 'fear', 'hope', 'love', 'hate', 'power',
    'death', 'life', 'survive', 'trust', 'betrayal', 'mystery',
    'shadow', 'blood', 'cold', 'warm', 'dead', 'alive', 'dangerous',
    'mysterious', 'strange', 'weird', 'terrifying', 'haunting',
}


# ============================================================================
# EMOTION UNDERSTANDING LAYER
# ============================================================================
# Each emotion has:
#   - keywords: words/phrases that signal this emotion (weighted by intensity)
#   - prosody: how to shape the sentence punctuation for this emotion
#   - speed: how fast to read sentences of this emotion (multiplier)
#   - pause_after: how much pause to add after (in seconds worth of "...")
#   - pitch_hint: subtle cue passed via text (Kokoro responds to ALL CAPS, !, ?)

EMOTION_LEXICON = {
    'fear': {
        'keywords': [
            ('terrified', 4), ('horror', 4), ('terror', 4), ('afraid', 3),
            ('scared', 3), ('fear', 3), ('scream', 4), ('screamed', 4),
            ('screaming', 4), ('panic', 4), ('panicked', 4), ('dread', 3),
            ('dreadful', 3), ('horrified', 4), ('nightmare', 3), ('haunted', 3),
            ('chilling', 3), ('chills', 3), ('creep', 3), ('creepy', 3),
            ('frozen', 3), ('trembling', 3), ('trembled', 3), ('shaking', 3),
            ('whimper', 3), ('cower', 3), ('cowered', 3), ('hide', 2),
            ('hidden', 2), ('darkness', 3), ('shadow', 2), ('shadows', 2),
            ('something was wrong', 4), ('never felt so', 3), ('heart pounding', 4),
            ('blood ran cold', 4), ('cold sweat', 3), ('paralyzed', 4),
            ('gasped', 3), ('breathless', 3), ('nightmare', 3), ('haunting', 3),
        ],
        'prosody': 'fragmented_trailing',
        'speed': 1.25,       # FAST — panicked, breathless
        'pause_after': 'very_short',  # No trailing pause
    },
    'suspense': {
        'keywords': [
            ('but then', 3), ('suddenly', 3), ('without warning', 4),
            ('nobody expected', 4), ('what happened next', 4), ('what they found', 4),
            ('the truth', 3), ('the secret', 3), ('the answer', 3),
            ('meanwhile', 2), ('however', 2), ('until now', 3), ('that night', 3),
            ('the moment', 3), ('right now', 2), ('little did', 3),
            ('strange', 2), ('strangely', 2), ('odd', 2), ('curious', 2),
            ('mysterious', 3), ('mystery', 3), ('unexplained', 3), ('clue', 2),
            ('discovered', 3), ('revealed', 3), ('realized', 3), ('noticed', 2),
            ('something', 2), ('someone', 2), ('someone was', 3), ('something was', 3),
            ('it was', 2), ('it turned out', 4), ('actually', 2), ('in fact', 2),
            ('to their surprise', 4), ('to his surprise', 4), ('to her surprise', 4),
            ('wait for it', 4), ('you won\'t believe', 4), ('plot twist', 4),
        ],
        'prosody': 'pause_before_reveal',
        'speed': 1.10,       # Slightly faster — building momentum
        'pause_after': 'very_short',  # Minimal pause
    },
    'sadness': {
        'keywords': [
            ('died', 4), ('death', 4), ('gone forever', 4), ('lost', 3),
            ('loss', 3), ('grief', 4), ('cried', 4), ('crying', 4), ('sobbed', 4),
            ('tears', 4), ('tear', 3), ('weep', 4), ('wept', 4), ('mourning', 4),
            ('funeral', 4), ('buried', 3), ('farewell', 4), ('goodbye', 3),
            ('miss', 3), ('missed', 3), ('miss him', 3), ('miss her', 3),
            ('lonely', 3), ('alone', 3), ('empty', 3), ('heartbreak', 4),
            ('broken', 3), ('broken heart', 4), ('hopeless', 4), ('never came back', 4),
            ('never returned', 4), ('disappeared', 3), ('vanished', 3),
            ('sorrow', 3), ('mourn', 3), ('grieving', 3), ('pain', 3),
        ],
        'prosody': 'soft_trailing',
        'speed': 0.78,
        'pause_after': 'long',
    },
    'joy': {
        'keywords': [
            ('laughed', 4), ('laughing', 4), ('laughter', 4), ('smile', 3),
            ('smiled', 3), ('smiling', 3), ('grin', 3), ('grinned', 3),
            ('beam', 3), ('beamed', 3), ('radiant', 3), ('joy', 3),
            ('joyful', 3), ('happy', 3), ('happiness', 3), ('delighted', 3),
            ('thrilled', 4), ('excited', 3), ('celebrate', 3), ('celebration', 3),
            ('wonderful', 3), ('amazing', 3), ('beautiful', 3), ('perfect', 2),
            ('love', 2), ('loved', 2), ('wonderful', 3), ('magical', 3),
            ('finally', 2), ('at last', 3), ('best day', 4), ('best moment', 4),
            ('hooray', 4), ('yay', 4), ('cheers', 3), ('celebrate', 3),
        ],
        'prosody': 'bright_emphatic',
        'speed': 1.15,
        'pause_after': 'short',
    },
    'anger': {
        'keywords': [
            ('furious', 4), ('rage', 4), ('raged', 4), ('angry', 3),
            ('anger', 3), ('hate', 3), ('hated', 3), ('hateful', 3),
            ('kill', 4), ('killed', 4), ('destroy', 3), ('destroyed', 3),
            ('fight', 3), ('fought', 3), ('attacked', 3), ('struck', 3),
            ('slammed', 3), ('screamed at', 4), ('yelled', 3), ('shouted', 3),
            ('how dare', 4), ('betrayed', 4), ('betrayal', 4), ('liar', 3),
            ('lied', 3), ('cheated', 3), ('fury', 4), ('enraged', 4),
            ('damn', 3), ('hell', 3), ('stupid', 3), ('idiot', 3),
        ],
        'prosody': 'sharp_punchy',
        'speed': 1.18,
        'pause_after': 'short',
    },
    'romance': {
        'keywords': [
            ('kiss', 4), ('kissed', 4), ('kissing', 4), ('embrace', 3),
            ('embraced', 3), ('held', 2), ('hold me', 4), ('in his arms', 4),
            ('in her arms', 4), ('whispered', 3), ('whisper', 3), ('beloved', 4),
            ('darling', 4), ('sweetheart', 4), ('my love', 4), ('i love you', 4),
            ('love you', 3), ('fall in love', 4), ('fell in love', 4),
            ('heart', 2), ('hearts', 2), ('soul', 2), ('souls', 2),
            ('tender', 3), ('tenderly', 3), ('gently', 2), ('softly', 2),
            ('beautiful', 2), ('gaze', 3), ('eyes met', 4), ('first time', 2),
            ('forever', 2), ('always', 2), ('meant to be', 4),
        ],
        'prosody': 'soft_intimate',
        'speed': 0.80,
        'pause_after': 'long',
    },
    'surprise': {
        'keywords': [
            ('shock', 3), ('shocked', 3), ('astonished', 4), ('stunned', 3),
            ('amazed', 3), ('incredible', 3), ('unbelievable', 3), ('wow', 3),
            ('what?!', 4), ('no way', 4), ('impossible', 4), ('never', 2),
            ('you won\'t believe', 4), ('guess what', 3), ('can you believe', 4),
            ('out of nowhere', 4), ('out of the blue', 4), ('unexpected', 3),
            ('plot twist', 4), ('turns out', 3), ('it turns out', 3),
            ('mind blown', 4), ('unreal', 4), ('unbelievable', 4),
        ],
        'prosody': 'emphatic_question',
        'speed': 1.10,
        'pause_after': 'medium',
    },
    'tension': {
        'keywords': [
            ('careful', 3), ('carefully', 2), ('slowly', 2), ('quiet', 3),
            ('quietly', 3), ('silence', 3), ('silent', 3), ('still', 2),
            ('don\'t move', 4), ('don\'t look', 4), ('don\'t make a sound', 4),
            ('waiting', 2), ('waited', 2), ('watched', 2), ('watching', 2),
            ('listening', 2), ('listened', 2), ('footsteps', 3), ('footstep', 3),
            ('door', 2), ('door creaked', 4), ('creak', 3), ('rustle', 3),
            ('approaching', 3), ('closer', 2), ('closer and closer', 4),
            ('any second', 3), ('on edge', 4), ('heartbeat', 3), ('pulse', 2),
            ('holding breath', 4), ('trembling', 3), ('shaking', 3),
        ],
        'prosody': 'urgent_fast',          # Fast, breathless delivery
        'speed': 1.20,       # FAST — urgency
        'pause_after': 'very_short',  # No trailing pause
    },
    'humor': {
        'keywords': [
            ('joke', 3), ('funny', 3), ('hilarious', 4), ('laugh', 3),
            ('ridiculous', 3), ('absurd', 3), ('crazy', 2), ('insane', 2),
            ('turns out he', 3), ('turns out she', 3), ('plot twist', 3),
            ('actually', 2), ('plot twist:', 4), ('spoiler alert', 4),
            ('lol', 3), ('lmao', 3), ('dying', 2), ('cracking up', 3),
        ],
        'prosody': 'playful',
        'speed': 1.12,
        'pause_after': 'short',
    },
    'excitement': {
        'keywords': [
            ('incredible', 3), ('amazing', 3), ('unbelievable', 3),
            ('you have to see', 4), ('you won\'t believe', 4), ('wait for it', 4),
            ('here it comes', 4), ('boom', 3), ('bam', 3), ('wow', 3),
            ('insane', 2), ('crazy', 2), ('epic', 3), ('legendary', 3),
            ('history', 2), ('historic', 3), ('never before', 4), ('first time ever', 4),
            ('mind blowing', 4), ('absolutely', 3), ('incredible', 4),
        ],
        'prosody': 'energetic_build',
        'speed': 1.22,
        'pause_after': 'short',
    },
    'wisdom': {
        'keywords': [
            ('remember', 2), ('lesson', 3), ('learned', 2), ('truth is', 4),
            ('the truth is', 4), ('here\'s why', 4), ('here\'s the thing', 4),
            ('here\'s what', 3), ('the key', 3), ('the secret', 3),
            ('think about it', 4), ('consider', 2), ('imagine', 2),
            ('the fact is', 4), ('in the end', 3), ('ultimately', 3),
            ('philosophy', 3), ('wisdom', 3), ('meaning', 2), ('purpose', 2),
            ('life lesson', 4), ('moral of the story', 4), ('deep thought', 4),
        ],
        'prosody': 'measured_authoritative',
        'speed': 0.85,
        'pause_after': 'medium',
    },
    'neutral': {
        'keywords': [],
        'prosody': 'plain',
        'speed': 1.0,
        'pause_after': 'normal',
    },
}


EMOTION_PRIORITY = ['fear', 'suspense', 'tension', 'romance', 'sadness',
                    'anger', 'surprise', 'excitement', 'joy', 'humor', 'wisdom', 'neutral']


def _score_emotion(sentence: str) -> tuple[str, float]:
    """Context-aware emotion scoring for sentences.
    
    Enhanced scoring considers:
    - Keyword density and intensity
    - Sentence structure (questions vs statements vs exclamations)
    - Punctuation patterns
    - Sentence length and complexity
    - Negation and modifiers
    - Dialogue context (quotes often indicate character emotion)
    """
    lower = sentence.lower()
    scores: dict[str, float] = {e: 0.0 for e in EMOTION_LEXICON}
    
    # 1. Keyword matching with context
    for emotion, config in EMOTION_LEXICON.items():
        for kw, weight in config['keywords']:
            if kw in lower:
                scores[emotion] += weight
                # Bonus for multiple keyword matches (emotion clustering)
                if scores[emotion] > weight:
                    scores[emotion] += 0.5
    
    # 2. Negation handling - stronger detection
    negation_patterns = [
        (r'\b(not|no|never|without|neither|nor|barely|hardly|scarcely)\s+(afraid|scared|terrified|angry|furious|sad|happy|excited)\b', ['fear', 'anger', 'sadness', 'joy']),
        (r'\b(don\'t|doesn\'t|didn\'t|won\'t|wouldn\'t|can\'t|couldn\'t|shouldn\'t)\s+\w+', ['fear', 'anger']),
        (r'\b(no|not|never)\s+(longer|more|again|once)\b', ['sadness']),
    ]
    for pattern, affected_emotions in negation_patterns:
        if re.search(pattern, lower):
            for emo in affected_emotions:
                scores[emo] = max(0, scores[emo] - 4)
    
    # 3. Punctuation signals with intensity
    bang_count = sentence.count('!')
    question_count = sentence.count('?')
    
    if bang_count >= 2:
        scores['excitement'] += 1.5
        scores['anger'] += 1.0
        scores['joy'] += 0.8
    elif bang_count == 1:
        scores['excitement'] += 0.7
        scores['anger'] += 0.5
        scores['joy'] += 0.3
    
    if question_count >= 2:
        scores['surprise'] += 1.0
        scores['suspense'] += 0.8
    elif question_count == 1:
        scores['suspense'] += 0.5
        scores['surprise'] += 0.5
    
    # Ellipsis indicates trailing off (suspense, sadness, tension, or romance)
    if sentence.endswith('...') or sentence.endswith('…'):
        scores['suspense'] += 0.8
        scores['sadness'] += 0.5
        scores['tension'] += 0.5
        scores['romance'] += 0.3
    
    # 4. Sentence structure analysis
    word_count = len(lower.split())
    
    # Long reflective sentences
    if word_count > 20 and sentence.count(',') >= 3:
        scores['wisdom'] += 1.5
        scores['romance'] += 0.8
    
    # Short punchy sentences
    if word_count < 6 and bang_count > 0:
        scores['excitement'] += 1.0
        scores['anger'] += 0.5
    
    # Questions about feelings/thoughts
    if '?' in sentence and any(w in lower for w in ['feel', 'think', 'believe', 'wonder', 'imagine']):
        scores['wisdom'] += 1.0
        scores['romance'] += 0.5
    
    # 5. Dialogue context - quotes often indicate character emotion
    if '"' in sentence or "'" in sentence:
        # Dialogue often has stronger emotion
        if any(w in lower for w in ['said', 'asked', 'replied', 'whispered', 'shouted']):
            scores['suspense'] += 0.3
    
    # 6. Temporal indicators
    temporal_words = ['suddenly', 'immediately', 'instantly', 'right now', 'at once']
    if any(w in lower for w in temporal_words):
        scores['suspense'] += 1.5
        scores['excitement'] += 0.5
    
    # Past tense indicators (often storytelling/narrative)
    past_indicators = ['was', 'were', 'had', 'did', 'went', 'came', 'said', 'thought', 'felt', 'knew']
    past_count = sum(1 for w in past_indicators if f' {w} ' in f' {lower} ')
    if past_count >= 2:
        scores['suspense'] += 0.5
    
    # 7. Rhetorical questions
    rhetorical_patterns = [
        r'^(what|how|why|who|where)\s+(if|about|would|could|should|did|do|does)',
        r'^(did|do|does)\s+you',
        r'(right\?|isn\'t it\?|aren\'t they\?)',
    ]
    for pattern in rhetorical_patterns:
        if re.search(pattern, lower):
            scores['wisdom'] += 1.0
            scores['suspense'] += 0.5
    
    # 8. Sort by priority then score (with tie-breaking)
    best_emo, best_score = 'neutral', 0.0
    for emo in EMOTION_PRIORITY:
        if scores[emo] > best_score:
            best_emo, best_score = emo, scores[emo]
    
    return best_emo, best_score


def _apply_emotion_prosody(sentence: str, emotion: str, score: float) -> str:
    """Apply natural emotion-based prosody to sentence.
    
    Uses punctuation, capitalization, and rhythm to convey emotion.
    Kokoro responds to: ALL CAPS, !, ?, ..., pauses via punctuation.
    """
    s = sentence.strip()
    if not s:
        return s

    # Only make changes for meaningful emotions
    if score < 1.5:
        # Ensure basic ending punctuation
        if s and s[-1] not in '.!?…':
            s += '.'
        return s

    has_bang = '!' in s
    has_question = '?' in s
    ends_punct = s and s[-1] in '.!?…'

    # FEAR: Slow, breathy, trailing off
    if emotion == 'fear' and score >= 2:
        if not ends_punct:
            s += '...'
        # Add pauses at natural break points
        s = s.replace(', ', '... ')
        return s

    # SUSPENSE: Dramatic pauses, question hooks
    if emotion == 'suspense' and score >= 2:
        if not ends_punct:
            s += '.'
        # Add dramatic pause before key words
        for word in ['suddenly', 'but then', 'however', 'unknown', 'secret', 'truth']:
            s = s.replace(f' {word} ', f'... {word} ', 1)
        return s

    # SADNESS: Soft, trailing, gentle
    if emotion == 'sadness' and score >= 2:
        if not ends_punct:
            s += '.'
        # Soften语气 - add gentle pauses
        s = s.replace(', ', '... ')
        return s

    # JOY: Bright, energetic, exclamatory
    if emotion == 'joy' and score >= 2:
        if not has_bang and not has_question:
            s = s.rstrip('.') + '!'
        elif not ends_punct:
            s += '!'
        return s

    # ANGER: Sharp, punchy, emphatic
    if emotion == 'anger' and score >= 3:
        if not has_bang:
            s = s.rstrip('.') + '!'
        # Emphasize key angry words with caps
        anger_words = ['never', 'always', 'nothing', 'everything', 'hate', 'furious', 'destroy']
        for word in anger_words:
            if word in s.lower():
                s = re.sub(rf'\b{word}\b', word.upper(), s, count=1, flags=re.IGNORECASE)
        return s

    # ROMANCE: Soft, intimate, flowing
    if emotion == 'romance' and score >= 2:
        if not ends_punct:
            s += '.'
        # Add gentle pauses for intimacy
        s = s.replace(', ', '... ')
        return s

    # SURPRISE: Sharp, questioning
    if emotion == 'surprise' and score >= 2:
        if not has_question and not has_bang:
            s = s.rstrip('.') + '!'
        elif not ends_punct:
            s += '!'
        return s

    # TENSION: Slow, measured, heavy pauses
    if emotion == 'tension' and score >= 2:
        if not ends_punct:
            s += '...'
        # Add heavy pauses
        s = s.replace(', ', '... ')
        s = s.replace('. ', '... ')
        return s

    # EXCITEMENT: Fast, punchy, exclamatory
    if emotion == 'excitement' and score >= 2:
        if not has_bang:
            s = s.rstrip('.') + '!'
        # Emphasize exciting words
        for word in ['amazing', 'incredible', 'unbelievable', 'insane', 'wow', 'boom']:
            if word in s.lower():
                s = re.sub(rf'\b{word}\b', word.upper(), s, count=1, flags=re.IGNORECASE)
        return s

    # WISDOM: Measured, thoughtful, paused
    if emotion == 'wisdom' and score >= 2:
        if not ends_punct:
            s += '.'
        # Add thoughtful pauses
        s = s.replace(', ', '... ')
        return s

    # Default: ensure ending punctuation
    if not ends_punct:
        s += '.'
    
    return s


def _emphasize_emotional_words(sentence: str, emotion: str) -> str:
    """Emphasize key emotion words by using ALL CAPS (Kokoro reads caps with emphasis).
    
    Only capitalizes 1 word per sentence for natural emphasis.
    """
    if not sentence or len(sentence) < 10:
        return sentence

    EMPHASIS_WORDS = {
        'anger': ['never', 'always', 'destroy', 'hate', 'furious', 'betrayed'],
        'fear': ['terrifying', 'horrifying', 'screaming', 'darkness', 'trapped', 'paralyzed'],
        'sadness': ['never', 'forever', 'lost', 'gone', 'empty', 'broken', 'tears'],
        'joy': ['amazing', 'incredible', 'beautiful', 'wonderful', 'perfect', 'love'],
        'excitement': ['unbelievable', 'insane', 'incredible', 'wild', 'crazy', 'epic'],
        'suspense': ['unknown', 'secret', 'hidden', 'truth', 'mystery', 'revealed', 'silence'],
        'romance': ['love', 'heart', 'kiss', 'tender', 'forever', 'soul', 'passion'],
        'surprise': ['suddenly', 'shocking', 'unexpected', 'impossible', 'stunned', 'gasped'],
        'tension': ['silence', 'waiting', 'danger', 'threat', 'fear', 'pressure'],
        'wisdom': ['truth', 'wisdom', 'understanding', 'meaning', 'purpose', 'journey'],
    }

    words_to_emphasize = EMPHASIS_WORDS.get(emotion, [])
    if not words_to_emphasize:
        return sentence

    emphasized = 0
    for word in words_to_emphasize:
        if emphasized >= 1:
            break
        pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
        match = pattern.search(sentence)
        if match:
            sentence = pattern.sub(word.upper(), sentence, count=1)
            emphasized += 1

    return sentence


# ============================================================================
# CHARACTER / GENRE DELIVERY PROFILES
# ============================================================================
# Each character/genre affects how emotions are delivered.

CHARACTER_PROFILES = {
    'storytelling': {
        'emotion_intensity': 1.2,
        'pause_scale': 1.0,
        'speed_scale': 1.0,
        'extra_fragments': False,
    },
    'mystery': {
        'emotion_intensity': 1.5,
        'pause_scale': 1.2,
        'speed_scale': 0.95,
        'extra_fragments': False,
    },
    'horror': {
        'emotion_intensity': 2.0,
        'pause_scale': 1.5,
        'speed_scale': 0.88,
        'extra_fragments': False,
    },
    'romantic': {
        'emotion_intensity': 1.6,
        'pause_scale': 1.2,
        'speed_scale': 0.92,
        'extra_fragments': False,
    },
    'documentary': {
        'emotion_intensity': 0.9,
        'pause_scale': 0.9,
        'speed_scale': 1.0,
        'extra_fragments': False,
    },
    'educational': {
        'emotion_intensity': 1.0,
        'pause_scale': 0.9,
        'speed_scale': 1.0,
        'extra_fragments': False,
    },
    'news': {
        'emotion_intensity': 0.8,
        'pause_scale': 0.8,
        'speed_scale': 1.02,
        'extra_fragments': False,
    },
    'shorts': {
        'emotion_intensity': 1.3,  # Natural emotion
        'pause_scale': 0.5,  # Slightly less pauses, not rushed
        'speed_scale': 1.04,  # Gentle pace — natural flow, not fast
        'extra_fragments': False,
    },
}

PAUSE_AFTER = {
    'but here', 'and then', 'what happened', 'the truth is',
    'the problem', 'nobody expected', 'what they found', 'the truth',
    'the moment', 'the day', 'that night', 'suddenly', 'meanwhile',
    'however', 'but then', 'and then', 'until now', 'right now',
    'the truth', 'what nobody', 'the secret', 'the answer',
}

# For shorts - minimal pauses
PAUSE_AFTER_SHORTS = {
    'the truth', 'the secret', 'what happened',
}

HOOK_PATTERNS = [
    r'^(Did you know|Here\'s the thing|Look|Listen|Think about it|You know what)',
    r'^(What if|Imagine|Picture this|Let me tell you)',
    r'^(Nobody talks about|The real story|The hidden truth)',
    r'^(This will|You won\'t believe|What happened next)',
]

TONE_SPEED_OFFSETS = {
    'natural': 0.0,
    'warm': -0.01,
    'deep': -0.03,
    'smooth': -0.01,
    'bright': +0.02,
    'gentle': -0.02,
    'crisp': +0.02,
    'resonant': -0.03,
    'dark': -0.04,
    'refined': -0.01,
    'hurried': +0.05,
}

TONE_PRESETS = {
    'natural': {'label': 'Natural', 'speed_offset': 0.0,  'description': 'Balanced, everyday tone'},
    'warm':     {'label': 'Warm',    'speed_offset': -0.01, 'description': 'Friendly, approachable'},
    'deep':     {'label': 'Deep',    'speed_offset': -0.03, 'description': 'Rich, authoritative'},
    'smooth':   {'label': 'Smooth',  'speed_offset': -0.01, 'description': 'Polished, professional'},
    'bright':   {'label': 'Bright',  'speed_offset': +0.02, 'description': 'Upbeat, energetic'},
    'gentle':   {'label': 'Gentle',  'speed_offset': -0.02, 'description': 'Soft, calming'},
    'crisp':    {'label': 'Crisp',   'speed_offset': +0.02, 'description': 'Sharp, broadcast-ready'},
    'resonant': {'label': 'Resonant','speed_offset': -0.03, 'description': 'Full, deep presence'},
    'dark':     {'label': 'Dark',    'speed_offset': -0.04, 'description': 'Brooding, cinematic shadow'},
    'refined':  {'label': 'Refined', 'speed_offset': -0.01, 'description': 'Polished British clarity'},
    'hurried':  {'label': 'Hurried', 'speed_offset': +0.05, 'description': 'Rushed, breathless delivery'},
}


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _ensure_ending(text: str) -> str:
    text = text.rstrip()
    if text and text[-1] not in '.!?…':
        text += '.'
    return text


def _split_into_sentences(text: str) -> list[str]:
    """Simple sentence splitting on terminal punctuation."""
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def _fragment_long_sentences(sentences: list[str], max_chars: int = 80) -> list[str]:
    """Leave sentences unchanged - don't split them."""
    return sentences


def _add_pause_before_reveals(sentences: list[str]) -> list[str]:
    """Leave sentences unchanged."""
    return sentences


def _slowdown_emphasis_words(sentences: list[str]) -> list[str]:
    """Leave sentences unchanged."""
    return sentences


def _add_rhythm_contrast(sentences: list[str]) -> list[str]:
    """Leave sentences unchanged."""
    return sentences


def _add_hook_opening(text: str) -> str:
    """Leave text unchanged."""
    return text


def _add_cliffhanger_ending(text: str) -> str:
    """Leave text unchanged."""
    return text

    last_char = text[-1]

    if last_char == '.':
        sentences = _split_into_sentences(text)
        if sentences:
            last = sentences[-1].lower()
            dramatic_endings = ['everything', 'nothing', 'forever', 'gone', 'dead', 'alive',
                              'truth', 'secret', 'mystery', 'unknown', 'unsolved', 'disappeared']
            is_dramatic = any(word in last for word in dramatic_endings)
            if is_dramatic:
                text = text[:-1] + '...'
            else:
                text = text[:-1] + '.'

    return text


def preprocess_text_storytelling(text: str) -> str:
    """Clean, natural text for storytelling.
    
    KEY PRINCIPLE: Minimal processing. Let the model handle prosody.
    """
    text = _normalize_whitespace(text)
    text = _ensure_ending(text)
    return text


def preprocess_text_shorts(text: str) -> str:
    """Optimized preprocessing for short-form content (YouTube Shorts, TikTok).
    
    Design principles for shorts:
    1. Fast, punchy delivery with natural rhythm
    2. Keep contractions and casual phrasing for authenticity
    3. Remove only truly unnecessary filler words
    4. Use commas for flow, periods for emphasis
    5. Hook-first structure with high energy
    """
    text = _normalize_whitespace(text)
    
    # Only remove truly meaningless fillers (keep natural ones like "you know", "like")
    meaningless_fillers = r'\b(basically|literally|sort of|kind of|I mean|um|uh|er|ah)\s*'
    text = re.sub(meaningless_fillers, '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Add natural pauses with commas for breathing room
    # Keep periods at sentence ends for proper cadence
    # Only collapse multiple punctuation
    text = re.sub(r'[.]{2,}', '.', text)
    text = re.sub(r'[,]{2,}', ',', text)
    text = re.sub(r'[!]{2,}', '!', text)
    text = re.sub(r'[?]{2,}', '?', text)
    
    # Ensure proper ending
    text = _ensure_ending(text)
    
    return text


def preprocess_text_mystery(text: str) -> str:
    """Mystery: clean text with natural pauses."""
    text = _normalize_whitespace(text)
    return text


def preprocess_text_horror(text: str) -> str:
    """Horror: clean text, let the model handle tension."""
    text = _normalize_whitespace(text)
    return text


def preprocess_text_romantic(text: str) -> str:
    """Romantic: clean text, gentle delivery."""
    text = _normalize_whitespace(text)
    return text


def preprocess_text_documentary(text: str) -> str:
    """Documentary: clean, measured text."""
    text = _normalize_whitespace(text)
    return text


def preprocess_text_educational(text: str) -> str:
    """Educational: clear, simple text."""
    text = _normalize_whitespace(text)
    return text


def preprocess_text_news(text: str) -> str:
    """News: professional, clean text."""
    text = _normalize_whitespace(text)
    # Remove filler words for cleaner delivery
    fillers = r'\b(very|really|quite|basically|actually|honestly|literally|sort of|kind of|I mean)\s*'
    text = re.sub(fillers, '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def preprocess_text_hurried(text: str) -> str:
    """Hurried: rushed, breathless delivery.
    
    Modifies text to create a "speaking in a hurry" feel:
    - Remove filler words (very, really, basically, etc.)
    - Replace periods between short clauses with commas (breathless flow)
    - Collapse multiple punctuation marks
    - Keep it natural - don't over-process
    """
    text = _normalize_whitespace(text)

    # Remove filler words for tighter delivery
    fillers = r'\b(very|really|quite|basically|actually|honestly|literally|sort of|kind of|I mean|you know)\s*'
    text = re.sub(fillers, '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()

    # Join short sentences: replace ". " between short clauses with ", "
    # This creates a breathless, connected flow (only for short segments <40 chars each)
    text = re.sub(
        r'([^.!?]{5,40})\.\s+([^.!?]{5,40})',
        r'\1, \2',
        text
    )

    # Collapse multiple punctuation
    text = re.sub(r'[.]{2,}', '.', text)
    text = re.sub(r'[!]{2,}', '!', text)
    text = re.sub(r'[?]{2,}', '?', text)

    # Ensure proper ending
    text = _ensure_ending(text)
    return text


def _apply_tone(text: str, tone: str) -> str:
    """Minimal tone adjustments - preserve original punctuation.
    
    KEY PRINCIPLE: Don't add '...' or modify punctuation excessively.
    Let the model handle tone naturally.
    """
    if not text or tone in ('natural', ''):
        return text
    
    # For all tones, just ensure sentences end with punctuation
    # Don't add dots, commas, or other markers
    return text


PREPROCESS_MAP = {
    'storytelling': preprocess_text_storytelling,
    'shorts': preprocess_text_shorts,
    'mystery': preprocess_text_mystery,
    'horror': preprocess_text_horror,
    'romantic': preprocess_text_romantic,
    'documentary': preprocess_text_documentary,
    'educational': preprocess_text_educational,
    'news': preprocess_text_news,
}


def preprocess_text(text: str, preset: str = 'storytelling', tone: str = 'natural') -> str:
    """Clean, minimal preprocessing for natural speech.
    
    KEY PRINCIPLE: Do as little as possible. The Kokoro model
    handles natural prosody, emotion, and pacing on its own.
    
    Pipeline:
      1. Normalize text (numbers, dates, abbreviations)
      2. Normalize whitespace
      3. Apply tone-specific text shaping (e.g. hurried)
      4. Ensure proper ending punctuation
    """
    # 1. Normalize text
    text = _normalize_text_comprehensive(text)
    
    # 2. Normalize whitespace
    text = _normalize_whitespace(text)
    
    # 3. Tone-specific text shaping (hurried modifies punctuation flow)
    if tone == 'hurried':
        text = preprocess_text_hurried(text)
        return text
    
    # 4. Ensure proper ending
    text = _ensure_ending(text)
    
    return text


def get_sentence_emotions(text: str, preset: str = 'storytelling') -> list[dict]:
    """Public API: analyze a script and return per-sentence emotions.
    Useful for UI display or debugging."""
    text = _normalize_whitespace(text)
    sentences = _split_into_sentences(text)
    result = []
    for i, sent in enumerate(sentences):
        emotion, score = _score_emotion(sent)
        result.append({
            'index': i,
            'text': sent,
            'emotion': emotion,
            'score': score,
            'prosody': EMOTION_LEXICON[emotion]['prosody'],
            'speed': EMOTION_LEXICON[emotion]['speed'],
            'pause_after': EMOTION_LEXICON[emotion]['pause_after'],
        })
    return result


VOICE_PROFILES = {
    "am_liam": {
        "blend": ["am_liam", "af_heart", "af_bella"],
        "blend_weights": [0.55, 0.25, 0.20],
        "storytelling": {
            "speed_offset": -0.05,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base - 0.03 if n < 10 else base + 0.02,
        },
        "shorts": {
            "speed_offset": -0.02,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base - 0.02 if n < 8 else base + 0.03,
        },
    },
    "am_adam": {
        "blend": ["am_adam", "af_heart", "af_nicole"],
        "blend_weights": [0.60, 0.25, 0.15],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.04,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "am_onyx": {
        "blend": ["am_onyx", "bf_emma"],
        "blend_weights": [0.72, 0.28],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.04,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "am_fenrir": {
        "blend": ["am_fenrir", "am_michael", "af_sarah"],
        "blend_weights": [0.55, 0.20, 0.25],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.04,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "am_michael": {
        "blend": ["am_michael", "bm_lewis"],
        "blend_weights": [0.75, 0.25],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.02,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "af_heart": {
        "blend": ["af_heart", "af_bella", "af_nicole"],
        "blend_weights": [0.55, 0.25, 0.20],
        "storytelling": {
            "speed_offset": -0.05,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.03,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "af_bella": {
        "blend": ["af_bella", "af_heart"],
        "blend_weights": [0.65, 0.35],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.03,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "af_nicole": {
        "blend": ["af_nicole", "af_heart"],
        "blend_weights": [0.75, 0.25],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.03,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "af_nova": {
        "blend": ["af_nova", "af_bella"],
        "blend_weights": [0.70, 0.30],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.03,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "af_sarah": {
        "blend": ["af_sarah", "af_nicole"],
        "blend_weights": [0.75, 0.25],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.03,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "bf_emma": {
        "blend": ["bf_emma", "bf_alice"],
        "blend_weights": [0.70, 0.30],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.04,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "bf_alice": {
        "blend": ["bf_alice", "bf_emma"],
        "blend_weights": [0.75, 0.25],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.04,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "bm_george": {
        "blend": ["bm_george", "bm_lewis"],
        "blend_weights": [0.70, 0.30],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.04,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
    "bm_lewis": {
        "blend": ["bm_lewis", "bm_george"],
        "blend_weights": [0.75, 0.25],
        "storytelling": {
            "speed_offset": 0.0,
            "split_pattern": r'\n\n+',
            "speed_fn": lambda base, n: base,
        },
        "shorts": {
            "speed_offset": +0.04,
            "split_pattern": r'\n+',
            "speed_fn": lambda base, n: base,
        },
    },
}


def blend_voice_tensors(pipeline, voice_id: str) -> torch.FloatTensor:
    """Blend multiple voice tensors for richer voice quality."""
    profile = VOICE_PROFILES.get(voice_id)
    if not profile or "blend" not in profile:
        return pipeline.load_single_voice(voice_id)

    tensors = [pipeline.load_single_voice(v) for v in profile["blend"]]
    weights = torch.tensor(profile["blend_weights"]).float()
    weights = weights / weights.sum()
    
    blended = torch.zeros_like(tensors[0])
    for w, t in zip(weights, tensors):
        blended += w * t
    
    return blended


def load_tuning_tensor(voice_id: str, tuning_id: int) -> torch.FloatTensor | None:
    tensor_path = settings.TUNING_DIR / voice_id / f"{tuning_id}.pt"
    if tensor_path.exists():
        return torch.load(str(tensor_path), weights_only=True)
    return None


class KokoroService:
    def __init__(self):
        self.pipelines = {}
        self.pipeline_errors = {}
        self.voices_config = self._load_voices_config()
        self._pipelines_loaded = False

    def _ensure_pipelines(self):
        if not self._pipelines_loaded:
            self._load_pipelines()
            self._pipelines_loaded = True

    def _load_voices_config(self) -> dict:
        config_path = Path(__file__).parent.parent / "core" / "voices.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_pipelines(self):
        for code in ['a', 'b']:
            try:
                self.pipelines[code] = KPipeline(lang_code=code)
                log.info(f"Loaded pipeline for lang_code={code}")
            except Exception as e:
                self.pipeline_errors[code] = str(e)
                log.error(f"Failed to load pipeline for lang_code={code}: {e}")

    def get_pipeline(self, lang_code: str = 'a') -> KPipeline:
        self._ensure_pipelines()
        pipeline = self.pipelines.get(lang_code, self.pipelines.get('a'))
        if pipeline is None:
            error_msg = self.pipeline_errors.get(lang_code, self.pipeline_errors.get('a', 'Unknown'))
            raise RuntimeError(f"TTS pipeline not available. Error: {error_msg}")
        return pipeline

    def _get_lang_code(self, voice_id: str) -> str:
        if voice_id.startswith('bm_') or voice_id.startswith('bf_'):
            return 'b'
        return 'a'

    def is_healthy(self) -> dict:
        self._ensure_pipelines()
        return {
            "kokoro": len(self.pipelines) > 0,
            "pipelines_loaded": list(self.pipelines.keys()),
            "errors": self.pipeline_errors
        }

    def _get_profile(self, voice_id: str, mode: str) -> dict:
        profile = VOICE_PROFILES.get(voice_id, {})
        return profile.get(mode, profile.get("storytelling", {}))

    def _generate_audio(
        self,
        text: str,
        voice: str,
        speed: float,
        mode: str = "storytelling",
        preset: str = "storytelling",
        tone: str = "natural",
        tuning_id: int | None = None,
    ) -> list:
        log.info(f"[TTS] Preprocessing text ({len(text)} chars) preset={preset} tone={tone}")
        text = preprocess_text(text, preset, tone)
        log.info(f"[TTS] After preprocess: {len(text)} chars")

        # Pre-analyze each chunk for emotion (so we can vary speed per chunk)
        chunk_emotions = self._analyze_chunks(text)

        profile = self._get_profile(voice, mode)
        pipeline = self.get_pipeline(self._get_lang_code(voice))

        if tuning_id:
            voice_tensor = load_tuning_tensor(voice, tuning_id)
            if voice_tensor is None:
                log.warning(f"[TTS] Tuning {tuning_id} not found for {voice}, falling back to default")
                voice_tensor = blend_voice_tensors(pipeline, voice)
        else:
            voice_tensor = blend_voice_tensors(pipeline, voice)

        base_speed = speed + profile.get("speed_offset", 0)
        base_speed = max(settings.MIN_SPEED, min(settings.MAX_SPEED, base_speed))
        character = CHARACTER_PROFILES.get(preset, CHARACTER_PROFILES['storytelling'])
        char_speed_scale = character.get('speed_scale', 1.0)

        speed_fn = profile.get("speed_fn")

        def _final_speed(n: int) -> float:
            # Length-based speed from voice profile
            s = speed_fn(base_speed, n) if speed_fn else base_speed

            # Emotion-based speed modulation (60% emotion, 40% length-based for natural variation)
            if chunk_emotions and n < len(chunk_emotions):
                emo = chunk_emotions[n]
                emo_speed = EMOTION_LEXICON[emo]['speed']
                s = (s * 0.4) + (s * (emo_speed / 1.0) * 0.6) if base_speed else s
            s *= char_speed_scale
            
            # Adaptive speed based on content complexity
            # (Applied after all other adjustments)
            return max(settings.MIN_SPEED, min(settings.MAX_SPEED, s))

        split_pattern = profile.get("split_pattern", r'\n\n+')

        audio_chunks = []
        log.info(f"[TTS] Running pipeline voice={voice} speed={base_speed:.2f} mode={mode}")
        generator = pipeline(
            text,
            voice=voice_tensor,
            speed=_final_speed,
            split_pattern=split_pattern,
        )

        MAX_CHUNKS = 200
        for i, (gs, ps, audio) in enumerate(generator):
            audio_chunks.append(audio)
            if i % 10 == 0:
                log.info(f"[TTS] Generated chunk {i+1} ({len(audio)/settings.SAMPLE_RATE:.1f}s)")
            if i >= MAX_CHUNKS:
                log.warning(f"[TTS] Hit max chunks ({MAX_CHUNKS}), stopping")
                break

        log.info(f"[TTS] Pipeline done: {len(audio_chunks)} chunks")
        if not audio_chunks:
            raise ValueError("No audio generated.")

        # Concatenate with gentle crossfade
        combined = _crossfade_audio(audio_chunks, fade_samples=480)
        
        # Safe output - only prevent clipping
        combined = _safe_audio_output(combined)

        return combined

    def _analyze_chunks(self, shaped_text: str) -> list[str]:
        """Split the emotion-shaped text by paragraph break and score each chunk's emotion.
        Returns a list of emotions aligned with the chunks Kokoro will produce."""
        if not shaped_text:
            return []
        chunks = [c.strip() for c in re.split(r'\n\n+', shaped_text) if c.strip()]
        if not chunks:
            return ['neutral']
        return [_score_emotion(c)[0] for c in chunks]

    def _generate_sentences_with_captions(
        self,
        text: str,
        voice: str,
        speed: float,
        mode: str = "storytelling",
        preset: str = "storytelling",
        tone: str = "natural",
        tuning_id: int | None = None,
        use_multi_pass: bool = True,
        use_enhancement: bool = True,
        ) -> tuple[list, list]:
        """Generate audio with parallel sentence processing for speed."""
        log.info(f"[TTS] Parallel generation preset={preset} tone={tone}")
        text = preprocess_text(text, preset, tone)
        
        sentences = _split_into_sentences(text)
        if not sentences:
            return [], []
    
        profile = self._get_profile(voice, mode)
        pipeline = self.get_pipeline(self._get_lang_code(voice))
    
        if tuning_id:
            voice_tensor = load_tuning_tensor(voice, tuning_id)
            if voice_tensor is None:
                voice_tensor = blend_voice_tensors(pipeline, voice)
        else:
            voice_tensor = blend_voice_tensors(pipeline, voice)
    
        base_speed = speed + profile.get("speed_offset", 0)
        base_speed = max(settings.MIN_SPEED, min(settings.MAX_SPEED, base_speed))
        character = CHARACTER_PROFILES.get(preset, CHARACTER_PROFILES['storytelling'])
        char_speed_scale = character.get('speed_scale', 1.0)
        const_speed = max(settings.MIN_SPEED, min(settings.MAX_SPEED, base_speed * char_speed_scale))

        # Prepare all sentences with prosody preprocessing
        processed_sentences = []
        for sentence in sentences:
            if not sentence.strip():
                continue
            emotion, score = _score_emotion(sentence)
            processed = _apply_emotion_prosody(sentence, emotion, score)
            processed = _emphasize_emotional_words(processed, emotion)
            processed = prosody_engine.analyze_and_enhance(processed, emotion, score, preset)
            processed_sentences.append((sentence, processed, emotion))

        if not processed_sentences:
            return [], []

        # Parallel generation function
        def generate_single(args):
            idx, (original, processed, emotion) = args
            try:
                gen = pipeline(
                    processed,
                    voice=voice_tensor,
                    speed=const_speed,
                    split_pattern=r'\n\n+',
                )
                chunks = [audio for _, _, audio in gen]
                if not chunks:
                    return idx, None, emotion
                combined = torch.cat(chunks) if len(chunks) > 1 else chunks[0]
                return idx, combined, emotion
            except Exception as e:
                log.warning(f"[TTS] Sentence {idx} failed: {e}")
                return idx, None, emotion

        # Run in parallel with thread pool
        num_workers = min(4, len(processed_sentences))
        results = {}
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(generate_single, (i, sent)): i 
                for i, sent in enumerate(processed_sentences)
            }
            for future in as_completed(futures):
                idx, audio, emotion = future.result()
                if audio is not None:
                    results[idx] = (audio, emotion)

        # Reassemble in order with natural pauses
        all_audio = []
        captions = []
        current_time = 0.0

        for i, (original, processed, emotion) in enumerate(processed_sentences):
            if i not in results:
                continue
            
            sentence_audio, _ = results[i]
            
            # Add gentle fade in/out to each sentence for smoother joins
            fade_len = min(int(settings.SAMPLE_RATE * 0.01), len(sentence_audio) // 8)  # 10ms fade
            if fade_len > 2:
                sentence_audio = sentence_audio.clone()
                sentence_audio[:fade_len] *= torch.linspace(0, 1, fade_len)
                sentence_audio[-fade_len:] *= torch.linspace(1, 0, fade_len)

            sentence_duration = len(sentence_audio) / settings.SAMPLE_RATE
            
            captions.append({
                'text': original,
                'start_time_ms': int(current_time * 1000),
                'duration_ms': int(sentence_duration * 1000),
                'emotion': emotion,
            })

            all_audio.append(sentence_audio)
            current_time += sentence_duration

            # Add natural pause between sentences
            if i < len(processed_sentences) - 1:
                # Pause based on punctuation and emotion
                pause_ms = 150  # Default pause
                if original.rstrip().endswith('...'):
                    pause_ms = 250  # Longer for suspense
                elif original.rstrip().endswith('!'):
                    pause_ms = 180  # Medium for exclamations
                elif original.rstrip().endswith('?'):
                    pause_ms = 200  # Slightly longer for questions
                elif emotion in ('suspense', 'fear', 'tension'):
                    pause_ms = 220  # Longer for dramatic moments
                elif emotion in ('joy', 'excitement'):
                    pause_ms = 120  # Shorter for excitement
                
                pause_samples = int(settings.SAMPLE_RATE * pause_ms / 1000)
                all_audio.append(torch.zeros(pause_samples))
                current_time += pause_ms / 1000

        return all_audio, captions


    def generate_speech(
        self,
        text: str,
        voice: str = "am_adam",
        speed: float = 1.0,
        mode: str = "storytelling",
        tone: str = "natural",
        preset: str = "storytelling",
        tuning_id: int | None = None,
        use_multi_pass: bool = True,
        use_enhancement: bool = True,
        enhancement_level: str = "balanced",
    ) -> tuple[str, str, float, list[dict]]:
        log.info(f"[TTS] generate_speech voice={voice} speed={speed} mode={mode} preset={preset} tone={tone} text_len={len(text)}")
        valid_voice_ids = {v["id"] for v in self.voices_config.get("voices", [])}
        if voice not in valid_voice_ids:
            raise ValueError(f"Voice '{voice}' not available. Options: {', '.join(sorted(valid_voice_ids))}")

        tone_offset = TONE_SPEED_OFFSETS.get(tone, 0.0)
        adjusted_speed = max(settings.MIN_SPEED, min(settings.MAX_SPEED, speed + tone_offset))

        job_id = str(uuid.uuid4())[:8]
        audio_chunks, captions = self._generate_sentences_with_captions(
            text, voice, adjusted_speed, mode, preset, tone=tone, tuning_id=tuning_id,
            use_multi_pass=use_multi_pass, use_enhancement=use_enhancement,
        )

        if not audio_chunks:
            raise ValueError("No audio generated.")

        # Concatenate with smooth crossfade
        combined = _crossfade_audio(audio_chunks, fade_samples=960)
        
        # Apply audio enhancement
        if use_enhancement:
            log.info(f"[TTS] Applying audio enhancement level={enhancement_level}")
            combined = audio_enhancer.enhance(
                combined,
                preset=preset,
                enhancement_level=enhancement_level,
            )
        else:
            combined = _safe_audio_output(combined)

        filename = f"{job_id}_{voice}.wav"
        filepath = settings.AUDIO_DIR / filename
        sf.write(str(filepath), combined.numpy(), settings.SAMPLE_RATE)

        duration = len(combined) / settings.SAMPLE_RATE
        return job_id, filename, duration, captions

    def generate_preview(self, text: str, voice: str = "am_adam", mode: str = "storytelling", tone: str = "natural", tuning_id: int | None = None) -> tuple[str, str]:
        valid_voice_ids = {v["id"] for v in self.voices_config.get("voices", [])}
        if voice not in valid_voice_ids:
            raise ValueError(f"Voice '{voice}' not available. Options: {', '.join(sorted(valid_voice_ids))}")

        job_id = str(uuid.uuid4())[:8]
        combined = self._generate_audio(text, voice, speed=1.0, mode=mode, preset=mode, tone=tone, tuning_id=tuning_id)
        
        # _generate_audio already applies _safe_audio_output, no need to apply again

        filename = f"preview_{job_id}_{voice}.wav"
        filepath = settings.PREVIEWS_DIR / filename
        sf.write(str(filepath), combined.numpy(), settings.SAMPLE_RATE)
        return job_id, filename

    def get_audio_path(self, filename: str) -> Path | None:
        path = settings.AUDIO_DIR / filename
        if path.exists():
            return path
        path = settings.PREVIEWS_DIR / filename
        if path.exists():
            return path
        return None

    def get_voices(self, gender: str = None, weight: str = None) -> list[dict]:
        voices = self.voices_config.get("voices", [])
        if gender:
            voices = [v for v in voices if v["gender"].lower() == gender.lower()]
        if weight:
            voices = [v for v in voices if v["weight"].lower() == weight.lower()]
        return voices

    def get_voice_by_id(self, voice_id: str) -> dict:
        for v in self.voices_config.get("voices", []):
            if v["id"] == voice_id:
                return v
        return None

    def get_tone_presets(self) -> dict:
        return TONE_PRESETS

    def get_voices_by_weight(self, weight: str) -> list[dict]:
        return [v for v in self.voices_config.get("voices", []) if v["weight"] == weight]

    def get_tuning_variations(self, voice_id: str) -> list[dict]:
        voice_dir = settings.TUNING_DIR / voice_id
        if not voice_dir.exists():
            return []
        meta_path = voice_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            return [{"id": int(k), "name": v["name"], "speed": v["speed"]} for k, v in meta.get("variations", {}).items()]
        variations = []
        for i in range(1, 11):
            pt = voice_dir / f"{i}.pt"
            if pt.exists():
                variations.append({"id": i, "name": f"variation_{i}", "speed": 1.0})
        return variations


kokoro_service = KokoroService()
