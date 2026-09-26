"""
NVIDIA NIM API Client with Robust JSON Parsing
Handles thinking process prefixes, timeouts, and fallback strategies.
"""

import asyncio
import json
import logging
import re
import time
from typing import Dict, List, Optional, Any, get_type_hints

import httpx

from ..core.config import settings

log = logging.getLogger(__name__)


class NVIDIAClient:
    """Client for NVIDIA NIM API with robust JSON parsing and fallback strategies.

    Auto-falls back to local Ollama when NVIDIA_API_KEY is not configured,
    enabling development and testing without NVIDIA account/credits.
    """

    # The account currently exposes gpt-oss-20b; catalog-only models return 404.
    FALLBACK_MODELS: list[str] = []

    # Standardized payload schema keys per pipeline stage
    SCHEMA_DEFINITIONS = {
        "classification": {
            "type": "object",
            "required": [
                "hook_category",
                "sub_category",
                "emotional_driver",
                "tone",
                "target_audience",
                "lead_gender",
            ],
            "properties": {
                "hook_category": {"type": "string"},
                "sub_category": {"type": "string"},
                "emotional_driver": {"type": "string"},
                "tone": {"type": "string"},
                "target_audience": {"type": "string"},
                "lead_gender": {"enum": ["male", "female", "neutral", "unknown"]},
                "high_value_combinations": {"type": "array"},
                "curiosity_question": {"type": "string"},
            },
        },
        "cold_hooks": {
            "type": "array",
            "minItems": 5,
            "items": {
                "type": "object",
                "required": [
                    "text",
                    "hook_category",
                    "psychological_trigger",
                    "hook_type",
                ],
                "properties": {
                    "text": {"type": "string"},
                    "hook_category": {"type": "string"},
                    "psychological_trigger": {"type": "string"},
                    "pattern_formula": {"type": "string"},
                    "hook_type": {"type": "string"},
                },
            },
        },
        "retention_plan": {
            "type": "array",
            "minItems": 8,
            "items": {
                "type": "object",
                "required": [
                    "hook_technique",
                    "hook_category",
                    "placement",
                    "estimated_timecode",
                    "purpose",
                    "sample_line",
                ],
                "properties": {
                    "hook_technique": {"type": "string"},
                    "hook_category": {"type": "string"},
                    "placement": {"type": "string"},
                    "estimated_timecode": {"type": "string"},
                    "purpose": {"type": "string"},
                    "sample_line": {"type": "string"},
                },
            },
        },
        "architecture": {
            "type": "array",
            "minItems": 8,
            "items": {
                "type": "object",
                "required": [
                    "beat_number",
                    "timecode_start",
                    "timecode_end",
                    "purpose",
                    "content",
                    "emotion",
                    "micro_hook_technique",
                    "hook_category",
                ],
                "properties": {
                    "beat_number": {"type": "integer"},
                    "timecode_start": {"type": "string"},
                    "timecode_end": {"type": "string"},
                    "purpose": {"type": "string"},
                    "content": {"type": "string"},
                    "emotion": {"type": "string"},
                    "micro_hook_technique": {"type": "string"},
                    "hook_category": {"type": "string"},
                },
            },
        },
        "draft": {"type": "string"},
        "micro_hooks": {
            "type": "object",
            "required": [
                "optimized_script",
                "missing_hooks",
                "forced_hooks",
                "hook_categories_used",
            ],
            "properties": {
                "optimized_script": {"type": "string"},
                "missing_hooks": {"type": "array"},
                "forced_hooks": {"type": "array"},
                "hook_categories_used": {"type": "array"},
            },
        },
        "script_polish": {
            "type": "object",
            "required": ["improved_script"],
            "properties": {"improved_script": {"type": "string"}},
        },
        "enhancement_analysis": {
            "type": "object",
            "required": ["suggestions"],
            "properties": {
                "overall_score": {"type": "number", "minimum": 0, "maximum": 100},
                "score": {"type": "number", "minimum": 0, "maximum": 100},
                "suggestions": {"type": "array"},
            },
        },
        "quality_score": {
            "type": "object",
            "required": ["overall_score", "breakdown", "suggestions"],
            "properties": {
                "overall_score": {"type": "number", "minimum": 0, "maximum": 100},
                "breakdown": {"type": "object"},
                "suggestions": {"type": "array"},
                "verdict": {"type": "string"},
            },
        },
    }

    def __init__(self):
        self.api_key = settings.NVIDIA_API_KEY
        self.base_url = settings.NVIDIA_BASE_URL
        self.model = settings.NVIDIA_MODEL
        self.reasoning_effort = settings.NVIDIA_REASONING_EFFORT
        self.nvidia_timeout = settings.NVIDIA_TIMEOUT
        self.ollama_base_url = settings.OLLAMA_BASE_URL
        self.ollama_model = settings.OLLAMA_MODEL
        self.ollama_timeout = settings.OLLAMA_TIMEOUT
        self.max_tokens = settings.NVIDIA_MAX_TOKENS
        self.temperature = settings.NVIDIA_TEMPERATURE
        self._client: httpx.AsyncClient | None = None
        self.successful_parses = 0
        self.parse_failures = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    self.nvidia_timeout if self.api_key else self.ollama_timeout,
                    connect=10.0,
                ),
                limits=httpx.Limits(
                    max_connections=10, max_keepalive_connections=5, keepalive_expiry=30
                ),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str | None:
        """Generate text from NVIDIA model with full retry logic.

        Auto-falls back to local Ollama when NVIDIA_API_KEY is not configured.
        """
        use_ollama = not self.api_key

        if use_ollama:
            log.info(
                "[OLLAMA] No NVIDIA API key configured, using local Ollama fallback"
            )

        # Ollama fallback path
        if use_ollama:
            payload = {
                "model": self.ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                # Ollama uses native generation options rather than OpenAI's
                # max_tokens field. Without num_predict, Qwen may think/generate
                # until the HTTP timeout is reached.
                "options": {
                    "temperature": temperature
                    if temperature is not None
                    else self.temperature,
                    "num_predict": max_tokens
                    if max_tokens is not None
                    else self.max_tokens,
                },
                "think": False,
                "stream": False,
            }

            last_error = None
            for attempt in range(3):
                start = time.monotonic()
                try:
                    client = await self._get_client()
                    response = await client.post(
                        f"{self.ollama_base_url.rstrip('/')}/api/chat",
                        json=payload,
                    )
                    elapsed = time.monotonic() - start

                    if response.status_code != 200:
                        last_error = f"http_{response.status_code}"
                        log.warning(
                            "[OLLAMA] HTTP %s for model %s, attempt %d/3: %s",
                            response.status_code,
                            self.ollama_model,
                            attempt + 1,
                            response.text[:500],
                        )
                        # A missing model or endpoint will not recover by retrying.
                        if response.status_code in (400, 404, 405):
                            break
                        if attempt < 2:
                            await asyncio.sleep(2**attempt)
                        continue

                    data = response.json()
                    log.info(
                        "[OLLAMA] Request completed in %.1fs using model: %s",
                        elapsed,
                        self.ollama_model,
                    )
                    # Extract content from Ollama response
                    if isinstance(data, dict) and "message" in data:
                        content = data["message"].get("content", "")
                        if content:
                            # Strip thinking process prefixes
                            stripped = self._strip_thinking_process(content)
                            return stripped or content
                    return str(data) if data else None

                except Exception as e:
                    last_error = f"{type(e).__name__}: {e!r}"
                    log.error(
                        "[OLLAMA] Error on attempt %d/3: %s",
                        attempt + 1,
                        last_error,
                    )
                    if attempt < 2:
                        await asyncio.sleep(2**attempt)
                    continue

            log.error("[OLLAMA] All 3 attempts failed. Last error: %s", last_error)
            self.parse_failures += 1
            return None

        # Original NVIDIA path (unchanged below)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "top_p": 0.9,
            "stream": False,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        last_error = None
        models_to_try = [self.model] + [
            m for m in self.FALLBACK_MODELS if m != self.model
        ]

        for model in models_to_try:
            payload["model"] = model
            # Do not repeat expensive generation requests. StoryForge has a
            # deterministic fallback and can complete the pipeline immediately.
            for attempt in range(1):
                start = time.monotonic()
                try:
                    client = await self._get_client()
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self.headers,
                        json=payload,
                    )
                    elapsed = time.monotonic() - start

                    if response.status_code == 410:
                        log.warning(
                            f"[NVIDIA] Model {model} is deprecated (410), trying next model..."
                        )
                        last_error = f"http_410_{model}"
                        break

                    if response.status_code == 429:
                        retry_after = int(
                            response.headers.get("Retry-After", 2**attempt)
                        )
                        log.warning(
                            f"[NVIDIA] Rate limited (attempt {attempt + 1}/1)"
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    if response.status_code >= 500:
                        log.warning(
                            f"[NVIDIA] Server error {response.status_code}, no retry"
                        )
                        continue

                    response.raise_for_status()
                    data = response.json()
                    log.info(
                        f"[NVIDIA] Request completed in {elapsed:.1f}s using model: {model}"
                    )
                    self.successful_parses += 1
                    # Extract content string from API response wrapper
                    if isinstance(data, dict) and "choices" in data and data["choices"]:
                        msg = data["choices"][0].get("message", {})
                        content = msg.get("content", "")
                        if content:
                            # Strip thinking process prefixes (e.g., "Here's a thinking process:")
                            stripped = self._strip_thinking_process(content)
                            return stripped or content
                        log.warning(
                            "[NVIDIA] Model returned no assistant content "
                            "(finish_reason=%s)",
                            data["choices"][0].get("finish_reason"),
                        )
                        continue
                    return None

                except httpx.TimeoutException:
                    log.error(f"[NVIDIA] Timeout on attempt {attempt + 1}/3")
                    last_error = "timeout"
                    if attempt < 2:
                        await asyncio.sleep(2**attempt)
                    continue

                except httpx.HTTPStatusError as e:
                    log.error(
                        f"[NVIDIA] HTTP error {e.response.status_code}: {e.response.text[:500]}"
                    )
                    last_error = f"http_{e.response.status_code}"
                    if attempt < 2:
                        await asyncio.sleep(2**attempt)
                    continue

                except Exception as e:
                    log.error(f"[NVIDIA] Error on attempt {attempt + 1}/3: {e}")
                    last_error = str(e)
                    if attempt < 2:
                        await asyncio.sleep(2**attempt)
                    continue

        log.error(f"[NVIDIA] All models and attempts failed. Last error: {last_error}")
        self.parse_failures += 1
        return None

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_key: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict | list | str | None:
        """Generate AI response validated against a standardized schema.

        Ensures AI returns structured payload with expected keys for each pipeline stage.
        If AI fails to return valid structured data, returns default schema for that stage.
        """
        schema = self.SCHEMA_DEFINITIONS.get(schema_key, {})
        if not schema:
            log.error(f"[NVIDIA] Unknown schema key: {schema_key}")
            return None

        # Step 1: Generate response from model
        response = await self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )

        if not response:
            self.parse_failures += 1
            log.warning(
                f"[NVIDIA] generate_structured: No response for schema {schema_key}"
            )
            return self._get_default_payload(schema_key)

        log.info(
            f"[NVIDIA] generate_structured({schema_key}): response type={type(response).__name__}, len={len(str(response))}"
        )

        # Step 2: Extract JSON using robust parser
        parsed = self._extract_json(response)
        parsed = self._normalize_schema_shape(parsed, schema)
        log.info(
            f"[NVIDIA] generate_structured({schema_key}): extracted type={type(parsed).__name__ if parsed else 'None'}, "
            f"keys={list(parsed.keys())[:8] if isinstance(parsed, dict) else ('len=' + str(len(parsed)) if isinstance(parsed, list) else 'N/A')}"
        )

        if parsed is not None:
            # Validate against schema if it's a dict/list
            if isinstance(parsed, (dict, list)):
                if self._validate_against_schema(parsed, schema):
                    self.successful_parses += 1
                    log.info(f"[NVIDIA] ✅ Parsed structured JSON for {schema_key}")
                    return parsed
                else:
                    log.error(
                        f"[NVIDIA] {schema_key}: JSON parsed but schema validation failed, using defaults"
                    )
            else:
                # Non-dict/list response (e.g., string draft)
                self.successful_parses += 1
                log.info(f"[NVIDIA] ✅ Parsed {schema_key}: non-JSON response")
                return parsed

        # Step 3: Fallback - try direct parse on original response
        try:
            # Only attempt json.loads if response is a string, not a dict
            if isinstance(response, str):
                direct = json.loads(response)
                direct = self._normalize_schema_shape(direct, schema)
                if isinstance(direct, (dict, list)):
                    if self._validate_against_schema(direct, schema):
                        self.successful_parses += 1
                        log.warning(
                            f"[NVIDIA] 📥 Parsed JSON directly for {schema_key} (model complied)"
                        )
                        return direct
                    else:
                        log.warning(
                            f"[NVIDIA] {schema_key}: Direct JSON failed schema validation"
                        )
            elif isinstance(response, dict):
                # Response is already a dict - check if it validates
                if self._validate_against_schema(response, schema):
                    self.successful_parses += 1
                    log.warning(
                        f"[NVIDIA] 📥 Response is dict, validated directly for {schema_key}"
                    )
                    return response
                else:
                    log.warning(
                        f"[NVIDIA] {schema_key}: Dict response failed schema validation"
                    )
        except (json.JSONDecodeError, Exception):
            pass

        # Step 4: Fallback - strip thinking process prefix and retry
        try:
            # Only strip thinking process if response is a string
            if isinstance(response, str):
                cleaned = self._strip_thinking_process(response)
                if cleaned:
                    parsed = json.loads(cleaned)
                    parsed = self._normalize_schema_shape(parsed, schema)
                    if isinstance(parsed, (dict, list)):
                        if self._validate_against_schema(parsed, schema):
                            self.successful_parses += 1
                            log.warning(
                                f"[NVIDIA] Parsed JSON after stripping thinking process for {schema_key}"
                            )
                            return parsed
        except (json.JSONDecodeError, Exception):
            pass

        # Step 5: Last resort - regex search for JSON-like structure
        try:
            parsed = self._extract_json_regex(response)
            if parsed is not None:
                if isinstance(parsed, (dict, list)):
                    if self._validate_against_schema(parsed, schema):
                        log.warning(
                            f"[NVIDIA] 🔍 Extracted JSON via regex for {schema_key}"
                        )
                        self.successful_parses += 1
                        return parsed
                    else:
                        log.warning(
                            f"[NVIDIA] {schema_key}: Regex extraction failed schema validation"
                        )
        except Exception as e:
            log.error(
                f"[NVIDIA] {schema_key}: regex extraction fallback crashed: {e}"
            )
        # Step 6: Return default payload for this schema
        log.error(
            f"[NVIDIA] ❌ Failed to parse structured JSON for {schema_key} ({len(response) if response else 0} chars). Using defaults."
        )
        self.parse_failures += 1
        return self._get_default_payload(schema_key)

    def _normalize_schema_shape(self, data: Any, schema: dict) -> Any:
        """Normalize small shape/metadata omissions without hiding bad payloads."""
        if schema.get("type") == "object" and isinstance(data, dict):
            if "lead_gender" in data and isinstance(data["lead_gender"], str):
                data["lead_gender"] = data["lead_gender"].strip().lower()
            if "high_value_combinations" in data and isinstance(
                data["high_value_combinations"], str
            ):
                data["high_value_combinations"] = [data["high_value_combinations"]]
            return data

        if schema.get("type") != "array":
            return data

        item_properties = schema.get("items", {}).get("properties", {})
        if isinstance(data, dict) and item_properties:
            if any(key in data for key in item_properties):
                log.warning(
                    "[NVIDIA] Model returned one %s item instead of an array; normalizing",
                    "structured",
                )
                data = [data]
            else:
                # Model wrapped the payload, e.g. {"beats": [...]} / {"hooks": [...]}.
                # Unwrap the first list value rather than failing schema validation.
                for value in data.values():
                    if isinstance(value, list):
                        log.warning(
                            "[NVIDIA] Model wrapped array payload; unwrapping to a list",
                        )
                        data = value
                        break

        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                # Hook text is the meaningful output. These fields are
                # metadata used for display and can be safely completed.
                if "text" in item:
                    item.setdefault("hook_category", "curiosity")
                    item.setdefault("psychological_trigger", "curiosity")
                    item.setdefault("hook_type", "cold_open")
                    item.setdefault(
                        "pattern_formula",
                        "Specific discovery creates an unanswered question",
                    )
                elif "hook_technique" in item:
                    item.setdefault("hook_category", "mystery")
                    item.setdefault("estimated_timecode", item.get("timecode", "0:00"))
                    item.setdefault("sample_line", "Then I noticed one detail.")
                elif "beat_number" in item:
                    item.setdefault("micro_hook_technique", "curiosity")
                    item.setdefault("hook_category", "mystery")

            # Preserve a valid generated hook when the model returns fewer
            # than five variants; complete the list with deterministic hooks.
            min_items = schema.get("minItems")
            if min_items == 5 and data and all(
                isinstance(item, dict) and item.get("text") for item in data
            ):
                defaults = self._get_default_payload("cold_hooks") or []
                for item in defaults:
                    if len(data) >= min_items:
                        break
                    if isinstance(item, dict):
                        data.append(dict(item))
        elif isinstance(data, dict) and schema.get("type") == "object":
            if "optimized_script" in data:
                data.setdefault("missing_hooks", [])
                data.setdefault("forced_hooks", [])
                data.setdefault("hook_categories_used", [])
        return data

    def _validate_against_schema(self, data: dict | list, schema: dict) -> bool:
        """Validate parsed JSON against standardized schema requirements."""
        try:
            if schema.get("type") == "array":
                if not isinstance(data, list):
                    log.warning("[NVIDIA] Schema validation: expected an array")
                    return False
                min_items = schema.get("minItems")
                if min_items is not None and len(data) < min_items:
                    log.warning(
                        "[NVIDIA] Schema validation: expected at least %d items, got %d",
                        min_items,
                        len(data),
                    )
                    return False
                items_schema = schema.get("items", {})
                for item in data:
                    if not self._validate_value(item, items_schema):
                        return False
                return True

            if schema.get("type") == "object" and not isinstance(data, dict):
                log.warning("[NVIDIA] Schema validation: expected an object")
                return False

            field_aliases = {"overall_score": ["score"]}
            if isinstance(data, dict):
                for field, aliases in field_aliases.items():
                    if field not in data:
                        for alias in aliases:
                            if alias in data:
                                data[field] = data[alias]
                                break
            return self._validate_value(data, schema)
        except Exception as e:
            log.warning(f"[NVIDIA] Schema validation error: {e}")
            return False

    def _validate_value(self, value: Any, schema: dict) -> bool:
        expected_type = schema.get("type")
        if expected_type == "object":
            if not isinstance(value, dict):
                return False
            for field in schema.get("required", []):
                if field not in value:
                    log.warning(
                        "[NVIDIA] Schema validation: missing required field '%s'",
                        field,
                    )
                    return False
            for key, definition in schema.get("properties", {}).items():
                if key in value and not self._validate_value(value[key], definition):
                    return False
        elif expected_type == "array":
            if not isinstance(value, list):
                return False
            if len(value) < schema.get("minItems", 0):
                return False
            item_schema = schema.get("items")
            if item_schema and any(not self._validate_value(item, item_schema) for item in value):
                return False
        elif expected_type == "string":
            if not isinstance(value, str):
                return False
        elif expected_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return False
        elif expected_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
            if not isinstance(value, (int, float)) or value != value:
                return False

        if "enum" in schema and value not in schema["enum"]:
            log.warning(
                "[NVIDIA] Schema validation: value %r is not in enum %r",
                value,
                schema["enum"],
            )
            return False
        if "minimum" in schema and value < schema["minimum"]:
            return False
        if "maximum" in schema and value > schema["maximum"]:
            return False
        return True

    def _get_default_payload(self, schema_key: str) -> dict | list | str | None:
        """Return default payload when AI fails to produce structured output."""
        defaults = {
            "classification": {
                "hook_category": "mystery",
                "sub_category": "unknown",
                "emotional_driver": "curiosity",
                "tone": "suspenseful",
                "target_audience": "general",
                "lead_gender": "male",
                "high_value_combinations": [],
                "curiosity_question": "What happened next?",
            },
            "cold_hooks": [
                {
                    "text": "I discovered something that changed everything.",
                    "hook_category": "curiosity",
                    "psychological_trigger": "curiosity_gap",
                    "pattern_formula": "I discovered something about X that changed everything",
                    "hook_type": "cold_open",
                },
                {
                    "text": "The person I trusted was living a double life.",
                    "hook_category": "shock",
                    "psychological_trigger": "betrayal",
                    "pattern_formula": "The [person] I trusted was living a double life",
                    "hook_type": "cold_open",
                },
                {
                    "text": "Nobody was supposed to find out what I discovered.",
                    "hook_category": "mystery",
                    "psychological_trigger": "open_loop",
                    "pattern_formula": "Nobody was supposed to find out about X",
                    "hook_type": "cold_open",
                },
                {
                    "text": "I found one detail that made the whole story worse.",
                    "hook_category": "reveal",
                    "psychological_trigger": "surprise",
                    "pattern_formula": "I found one detail that changed everything",
                    "hook_type": "cold_open",
                },
                {
                    "text": "The warning arrived after it was already too late.",
                    "hook_category": "consequence",
                    "psychological_trigger": "fear",
                    "pattern_formula": "The warning came after it was too late",
                    "hook_type": "cold_open",
                },
            ],
            "retention_plan": [
                {
                    "hook_technique": "But Then...",
                    "hook_category": "escalation",
                    "placement": "after context",
                    "estimated_timecode": "0:08",
                    "purpose": "Create anticipation",
                    "sample_line": "But then I noticed one detail.",
                },
                {
                    "hook_technique": "There Was Just One Problem...",
                    "hook_category": "conflict",
                    "placement": "before conflict",
                    "estimated_timecode": "0:15",
                    "purpose": "Introduce tension",
                    "sample_line": "There was just one problem.",
                },
                {
                    "hook_technique": "Then Everything Changed...",
                    "hook_category": "escalation",
                    "placement": "during escalation",
                    "estimated_timecode": "0:25",
                    "purpose": "Raise stakes",
                    "sample_line": "Then everything changed.",
                },
                {
                    "hook_technique": "Then I Found Out...",
                    "hook_category": "reveal",
                    "placement": "before reveal",
                    "estimated_timecode": "0:35",
                    "purpose": "Build curiosity",
                    "sample_line": "Then I found out who was involved.",
                },
                {
                    "hook_technique": "And That Is When...",
                    "hook_category": "twist",
                    "placement": "at twist",
                    "estimated_timecode": "0:45",
                    "purpose": "Deliver the turn",
                    "sample_line": "And that was when I understood.",
                },
                {
                    "hook_technique": "The Evidence...",
                    "hook_category": "evidence",
                    "placement": "before confrontation",
                    "estimated_timecode": "0:55",
                    "purpose": "Prove the suspicion",
                    "sample_line": "The evidence was right in front of me.",
                },
                {
                    "hook_technique": "One Last Question...",
                    "hook_category": "curiosity",
                    "placement": "before climax",
                    "estimated_timecode": "1:05",
                    "purpose": "Delay the answer",
                    "sample_line": "There was one question I still could not answer.",
                },
                {
                    "hook_technique": "The Truth Was...",
                    "hook_category": "truth_reveal",
                    "placement": "final reveal",
                    "estimated_timecode": "1:15",
                    "purpose": "Reveal the truth",
                    "sample_line": "The truth was worse than I imagined.",
                },
                {
                    "hook_technique": "Looking Back...",
                    "hook_category": "reflection",
                    "placement": "aftermath",
                    "estimated_timecode": "1:25",
                    "purpose": "Leave a lasting implication",
                    "sample_line": "Looking back, I should have known.",
                },
            ],
            "architecture": [
                {
                    "beat_number": 1,
                    "timecode_start": "0:00",
                    "timecode_end": "0:02",
                    "purpose": "Stop the scroll",
                    "content": "I discovered something that changed everything.",
                    "emotion": "intrigue",
                    "micro_hook_technique": "cold_open",
                    "hook_category": "cold_open",
                },
                {
                    "beat_number": 2,
                    "timecode_start": "0:02",
                    "timecode_end": "0:08",
                    "purpose": "Context",
                    "content": "I explained what life had been like before the discovery.",
                    "emotion": "curiosity",
                    "micro_hook_technique": "But Then",
                    "hook_category": "context",
                },
                {
                    "beat_number": 3,
                    "timecode_start": "0:08",
                    "timecode_end": "0:15",
                    "purpose": "Conflict",
                    "content": "One detail made me question everything I believed.",
                    "emotion": "tension",
                    "micro_hook_technique": "One Problem",
                    "hook_category": "conflict",
                },
                {
                    "beat_number": 4,
                    "timecode_start": "0:15",
                    "timecode_end": "0:25",
                    "purpose": "Investigation",
                    "content": "I searched for evidence and found a second clue.",
                    "emotion": "determination",
                    "micro_hook_technique": "Evidence",
                    "hook_category": "mystery",
                },
                {
                    "beat_number": 5,
                    "timecode_start": "0:25",
                    "timecode_end": "0:35",
                    "purpose": "Escalation",
                    "content": "The person I trusted gave me an answer that raised more questions.",
                    "emotion": "betrayal",
                    "micro_hook_technique": "Then Everything Changed",
                    "hook_category": "betrayal",
                },
                {
                    "beat_number": 6,
                    "timecode_start": "0:35",
                    "timecode_end": "0:45",
                    "purpose": "Reveal",
                    "content": "The hidden truth finally connected every strange detail.",
                    "emotion": "shock",
                    "micro_hook_technique": "Then I Found Out",
                    "hook_category": "reveal",
                },
                {
                    "beat_number": 7,
                    "timecode_start": "0:45",
                    "timecode_end": "0:55",
                    "purpose": "Confrontation",
                    "content": "I confronted the person responsible and demanded the truth.",
                    "emotion": "anger",
                    "micro_hook_technique": "The Evidence",
                    "hook_category": "justice",
                },
                {
                    "beat_number": 8,
                    "timecode_start": "0:55",
                    "timecode_end": "1:05",
                    "purpose": "Aftermath",
                    "content": "I understood what it meant and could never see things the same way.",
                    "emotion": "reflection",
                    "micro_hook_technique": "Looking Back",
                    "hook_category": "emotional_reveal",
                },
            ],
            "draft": "I discovered something that changed everything. But then I noticed something nobody else had. There was just one problem. Nobody believed what I found. I kept digging. Then everything changed. The truth was worse than I imagined. Then I found out who was really behind it. And that's when the whole thing unraveled.",
            "micro_hooks": {
                "optimized_script": "I discovered something that changed everything. Then I noticed what nobody else had.",
                "missing_hooks": [],
                "forced_hooks": [],
                "hook_categories_used": ["curiosity", "mystery"],
            },
            "script_polish": {
                "improved_script": "I discovered something that changed everything. Then I noticed what nobody else had."
            },
            "enhancement_analysis": {
                "overall_score": 70,
                "score": 70,
                "suggestions": [],
            },
            "quality_score": {
                "overall_score": 70,
                "breakdown": {
                    "hook_strength": 70,
                    "pacing": 70,
                    "emotional_impact": 70,
                    "clarity": 80,
                    "originality": 65,
                    "memorability": 70,
                },
                "suggestions": ["Quality scoring: AI failed, using default score"],
                "verdict": "decent",
            },
        }
        return defaults.get(schema_key)

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Return the payload inside markdown code fences, or the input unchanged."""
        if not isinstance(text, str) or "```" not in text:
            return text
        start = text.find("```")
        end = text.rfind("```")
        if end <= start:
            return text
        inner = text[start + 3 : end]
        first_nl = inner.find("\n")
        if first_nl != -1:
            inner = inner[first_nl + 1 :]
        return inner.strip()

    def _extract_json(self, text: str | dict) -> dict | list | None:
        """Extract JSON from response using bracket-counting method."""
        if isinstance(text, dict):
            # A dict that already *is* the payload must be returned as-is. Check this
            # before the "content" branch, otherwise payloads containing a "content"
            # field (e.g. a single story beat) get stringified and destroyed.
            if "choices" not in text and any(
                k in text
                for k in (
                    "hook_category",
                    "category",
                    "beat_number",
                    "text",
                    "theme",
                    "title",
                    "optimized_script",
                    "overall_score",
                )
            ):
                return text
            # If it's an API response wrapper (has choices), extract the actual content
            if "choices" in text and text["choices"]:
                msg = text["choices"][0].get("message", {})
                content = msg.get("content", "")
                if content and isinstance(content, str):
                    # Try parsing the content string as JSON
                    try:
                        result = json.loads(content)
                        if isinstance(result, (dict, list)):
                            return result
                    except (json.JSONDecodeError, TypeError):
                        pass
                    # Fall through to bracket-counting on the content string
                    text = content
                else:
                    # Content is already a dict (some models return it this way)
                    if isinstance(content, dict):
                        return content
            elif "content" in text and isinstance(text["content"], str):
                # Direct content dict
                try:
                    result = json.loads(text["content"])
                    if isinstance(result, (dict, list)):
                        return result
                except (json.JSONDecodeError, TypeError):
                    pass
            # Fall through to process as string
            text = str(text) if text else ""
        else:
            text = text.strip()

        if not text:
            return None

        # Strategy 0: Direct json.loads (fastest, works for clean JSON)
        try:
            result = json.loads(text)
            if isinstance(result, (dict, list)):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        # Strategy 0b: retry after removing markdown code fences (```json ... ```)
        fence_stripped = self._strip_markdown_fences(text)
        if fence_stripped != text:
            try:
                result = json.loads(fence_stripped)
                if isinstance(result, (dict, list)):
                    return result
            except (json.JSONDecodeError, TypeError):
                pass

        # Strategy 1: Find all balanced JSON values and keep the richest one.
        # Model output is frequently prose- or fence-wrapped, so bracket scanning is
        # the workhorse. Arrays are scanned first because most schemas are arrays and
        # a single element object must never be mistaken for the whole payload.
        import re

        candidates: list[tuple[int, Any]] = []
        max_candidates = 32
        for open_ch, close_ch, result_type in (("[", "]", list), ("{", "}", dict)):
            if len(candidates) >= max_candidates:
                break
            for match in re.finditer(re.escape(open_ch), text):
                if len(candidates) >= max_candidates:
                    break
                json_start = match.start()
                depth = 0
                for i in range(json_start, len(text)):
                    ch = text[i]
                    if ch == open_ch:
                        depth += 1
                    elif ch == close_ch:
                        depth -= 1
                        if depth == 0:
                            raw = text[json_start : i + 1]
                            try:
                                result = json.loads(raw)
                            except json.JSONDecodeError:
                                result = None
                            else:
                                if isinstance(result, result_type):
                                    # Track source length so the outermost (most
                                    # complete) value wins over nested fragments.
                                    candidates.append((len(raw), result))
                            break

        if candidates:
            # Longest source span == outermost, most complete payload. A full beat
            # array is always longer than any single beat object inside it.
            _, best = max(candidates, key=lambda c: c[0])
            return best

        # Strategy 2: Search for JSON with story-related keys
        dict_pattern = r'\{(?:[^{}]*"(?:category|hook|title|theme|tone|purpose|content|beat)[^{}]*)*\}'
        match = re.search(dict_pattern, text)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        # Strategy 3: Balanced brace search - find any balanced JSON
        for open_ch, close_ch in [("{", "}"), ("[", "]")]:
            depth = 0
            start = -1
            for i, ch in enumerate(text):
                if ch == open_ch:
                    if depth == 0:
                        start = i
                if ch == close_ch:
                    depth -= 1
                    if depth == 0 and start >= 0:
                        candidate = text[start : i + 1]
                        try:
                            result = json.loads(candidate)
                            if isinstance(result, (dict, list)):
                                return result
                        except json.JSONDecodeError:
                            start = -1
                    elif depth < 0:
                        depth = 0
                        start = -1

        return None

    def _strip_thinking_process(self, text: str) -> str | None:
        """Strip thinking/reasoning prefixes that some models prepend to their output."""
        import re

        if not text or not isinstance(text, str):
            return None
        # Common patterns: "Here's a thinking process:", "Let me think...", etc.
        patterns = [
            r"(?:Here'?s?\s+(?:a\s+)?thinking\s+process[:\s]*\n+)",
            r"(?:Let me think(?:\s+about this)?[:\s]*\n+)",
            r"(?:I'?ll\s+(?:think|analyze|consider)[^.]*[:\s]*\n+)",
            r"(?:Step\s+\d+[:\s]+\n+)",
        ]
        cleaned = text
        for p in patterns:
            cleaned = re.sub(p, "", cleaned, count=1, flags=re.IGNORECASE)
        # If we stripped something, return the cleaned text
        if cleaned != text:
            return cleaned.strip()
        return None

    def _extract_json_regex(self, text: str) -> dict | list | None:
        """Extract JSON using regex patterns as last resort."""
        import re

        # Strip thinking process prefix first, then markdown fences
        text = self._strip_thinking_process(text) or text
        text = self._strip_markdown_fences(text)

        # Pattern for JSON array of beat objects (pretty-printed or compact)
        beat_pattern = r'\[\s*\{.*"beat_number".*\}\s*\]'
        match = re.search(beat_pattern, text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list) and len(result) > 0:
                    return result
            except json.JSONDecodeError:
                pass

        # Pattern for JSON object with essential keys
        essential_keys = [
            "category",
            "hook",
            "title",
            "theme",
            "tone",
            "purpose",
            "content",
        ]
        # Build regex pattern that matches JSON with any of the essential keys
        key_alt = "|".join([re.escape(k) for k in essential_keys])
        # key_alt must be wrapped: otherwise `|` splits the whole non-capturing group
        dict_pattern = r'\{(?:[^{}]*(?:' + key_alt + r')[^{}]*)\}'
        dynamic_pattern = re.compile(dict_pattern, re.IGNORECASE)
        match = dynamic_pattern.search(text)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        return None
