"""Structured output contracts for every LLM task, plus validation.

Each task has (a) a JSON Schema sent to the provider so it returns structured
JSON, and (b) a Pydantic model that validates the response *again* before
anything is saved - providers can and do return malformed output.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.errors import LLMError

# Instagram limits (documented by Meta): captions up to 2,200 characters,
# at most 30 hashtags per post.
INSTAGRAM_CAPTION_MAX = 2200
INSTAGRAM_HASHTAG_MAX = 30

_HASHTAG_RE = re.compile(r"^[\wऀ-ॿ]+$", re.UNICODE)  # letters/digits/_ incl. Devanagari


def normalize_hashtag(tag: str) -> str:
    tag = tag.strip().lstrip("#").strip()
    tag = re.sub(r"\s+", "", tag)
    return tag


class GeneratedPost(BaseModel):
    headline: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=200)
    caption: str = Field(min_length=1, max_length=INSTAGRAM_CAPTION_MAX)
    cta: str = Field(default="", max_length=300)
    hashtags: list[str] = Field(default_factory=list)
    image_prompt: str = Field(min_length=1, max_length=4000)
    alternative_caption: str = Field(default="", max_length=INSTAGRAM_CAPTION_MAX)
    content_summary: str = Field(default="", max_length=1000)
    missing_information: list[str] = Field(default_factory=list)

    @field_validator("headline", "caption", "image_prompt")
    @classmethod
    def _strip_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("hashtags")
    @classmethod
    def _clean_hashtags(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in v:
            tag = normalize_hashtag(str(raw))
            if not tag or not _HASHTAG_RE.match(tag):
                continue
            if tag.lower() in seen:
                continue
            seen.add(tag.lower())
            cleaned.append(tag)
        return cleaned[:INSTAGRAM_HASHTAG_MAX]

    @field_validator("missing_information")
    @classmethod
    def _clean_missing(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if isinstance(s, str) and s.strip()][:20]


class ContentIdeaOut(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    category_key: str = Field(default="RANDOM", max_length=50)
    suggested_format: str = Field(default="", max_length=100)
    target_audience: str = Field(default="", max_length=500)


class IdeasResponse(BaseModel):
    ideas: list[ContentIdeaOut] = Field(min_length=1, max_length=30)


class CompetitorInsightsOut(BaseModel):
    summary: str = ""
    common_topics: list[str] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)
    recurring_themes: list[str] = Field(default_factory=list)
    audience_targeting: list[str] = Field(default_factory=list)
    cta_patterns: list[str] = Field(default_factory=list)
    visual_trends: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


def _strict_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}

POST_JSON_SCHEMA = _strict_schema(
    {
        "headline": _STR,
        "subtitle": _STR,
        "caption": _STR,
        "cta": _STR,
        "hashtags": _STR_LIST,
        "image_prompt": _STR,
        "alternative_caption": _STR,
        "content_summary": _STR,
        "missing_information": _STR_LIST,
    }
)

IDEAS_JSON_SCHEMA = _strict_schema(
    {
        "ideas": {
            "type": "array",
            "items": _strict_schema(
                {
                    "title": _STR,
                    "description": _STR,
                    "category_key": _STR,
                    "suggested_format": _STR,
                    "target_audience": _STR,
                }
            ),
        }
    }
)

INSIGHTS_JSON_SCHEMA = _strict_schema(
    {
        "summary": _STR,
        "common_topics": _STR_LIST,
        "content_gaps": _STR_LIST,
        "recurring_themes": _STR_LIST,
        "audience_targeting": _STR_LIST,
        "cta_patterns": _STR_LIST,
        "visual_trends": _STR_LIST,
        "recommendations": _STR_LIST,
    }
)


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from raw model text (tolerates ``` fences and leading prose)."""
    if not text or not text.strip():
        raise LLMError("The AI returned an empty response.")
    candidate = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("The AI response was not valid JSON.") from None
        try:
            data = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("The AI response was not valid JSON.") from exc
    if not isinstance(data, dict):
        raise LLMError("The AI response was JSON but not an object.")
    return data


def parse_model(model: type[BaseModel], data: dict[str, Any]):
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])
        raise LLMError(f"The AI response did not match the expected format ({problems}).") from exc


def validate_caption_with_hashtags(caption: str, hashtags: list[str]) -> list[str]:
    """Return human-readable problems with the final Instagram caption, if any."""
    problems: list[str] = []
    full = compose_caption(caption, hashtags)
    if len(full) > INSTAGRAM_CAPTION_MAX:
        problems.append(f"Caption plus hashtags is {len(full)} characters; Instagram allows {INSTAGRAM_CAPTION_MAX}.")
    if len(hashtags) > INSTAGRAM_HASHTAG_MAX:
        problems.append(f"{len(hashtags)} hashtags; Instagram allows {INSTAGRAM_HASHTAG_MAX}.")
    mentions = re.findall(r"(?<!\w)@\w+", caption)
    if len(mentions) > 20:
        problems.append("More than 20 @mentions in caption.")
    return problems


def compose_caption(caption: str, hashtags: list[str]) -> str:
    caption = caption.rstrip()
    if not hashtags:
        return caption
    return f"{caption}\n\n" + " ".join(f"#{t}" for t in hashtags)
