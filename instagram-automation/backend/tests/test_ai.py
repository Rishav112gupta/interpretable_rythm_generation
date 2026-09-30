import pytest

from app.core.errors import LLMError
from app.services.ai.fact_guard import check_unverified_facts, placeholder_flags
from app.services.ai.mock_provider import MockLLMProvider
from app.services.ai.schemas import (
    POST_JSON_SCHEMA,
    GeneratedPost,
    compose_caption,
    extract_json_object,
    parse_model,
    validate_caption_with_hashtags,
)

VALID = {
    "headline": "Beat exam stress",
    "subtitle": "",
    "caption": "Some caption",
    "cta": "Join now",
    "hashtags": ["#Exam Prep", "study", "study", "bad tag!", "#"],
    "image_prompt": "A calm desk",
    "alternative_caption": "",
    "content_summary": "",
    "missing_information": [],
}


def test_extract_json_plain_fenced_and_with_prose():
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json_object('Sure! Here it is: {"a": 3} hope it helps') == {"a": 3}


@pytest.mark.parametrize("bad", ["", "not json", "[1,2]", "{broken"])
def test_extract_json_rejects_invalid(bad):
    with pytest.raises(LLMError):
        extract_json_object(bad)


def test_generated_post_normalizes_hashtags():
    post = parse_model(GeneratedPost, VALID)
    assert post.hashtags == ["ExamPrep", "study"]


def test_generated_post_requires_headline_caption_prompt():
    for field in ("headline", "caption", "image_prompt"):
        with pytest.raises(LLMError):
            parse_model(GeneratedPost, {**VALID, field: "   "})


def test_generated_post_rejects_too_long_caption():
    with pytest.raises(LLMError):
        parse_model(GeneratedPost, {**VALID, "caption": "x" * 2201})


def test_hashtags_capped_at_instagram_limit():
    post = parse_model(GeneratedPost, {**VALID, "hashtags": [f"tag{i}" for i in range(50)]})
    assert len(post.hashtags) == 30


def test_caption_plus_hashtags_limit():
    assert validate_caption_with_hashtags("x" * 2100, ["a" * 50, "b" * 50]) != []
    assert validate_caption_with_hashtags("hello", ["a"]) == []
    assert compose_caption("Hi", ["a", "b"]) == "Hi\n\n#a #b"


def test_schema_is_strict_for_structured_outputs():
    assert POST_JSON_SCHEMA["additionalProperties"] is False
    assert set(POST_JSON_SCHEMA["required"]) == set(POST_JSON_SCHEMA["properties"])


def test_mock_provider_flags_missing_exam_info_instead_of_inventing():
    result = MockLLMProvider().complete_json(task="post", system="", user="", schema={}, context={"topic": "Exam tips", "category_key": "EXAM", "cta": ""})
    post = parse_model(GeneratedPost, result.data)
    assert any("Exam" in m for m in post.missing_information)
    assert any("call to action" in m for m in post.missing_information)


def test_fact_guard_flags_unverified_price_and_accepts_verified():
    text = "Enroll now for just ₹4,999! Call +91 98765 43210."
    flags = check_unverified_facts([text], ["Course fee: Rs 4999"])
    kinds = {f["type"] for f in flags}
    assert "price" not in kinds  # verified in knowledge base (normalised)
    assert "phone" in kinds


@pytest.mark.parametrize(
    "text,kind",
    [
        ("Exam on 12th March 2027", "date"),
        ("98% of our students succeed", "percentage"),
        ("Guaranteed selection!", "guarantee"),
        ("Flat 20% off this week", "discount"),
        ("Join 5000+ students", "statistic"),
        ("Visit https://example.com", "url"),
        ("Mail us at hi@example.com", "email"),
    ],
)
def test_fact_guard_detects_risky_claims(text, kind):
    flags = check_unverified_facts([text], ["unrelated fact"])
    assert kind in {f["type"] for f in flags}


def test_fact_guard_ignores_hashtags_and_plain_text():
    assert check_unverified_facts(["Study smart, not hard. #Top100 #2027goals"], []) == []


def test_placeholder_flags():
    flags = placeholder_flags(["The exam is on [EXAM DATE]."])
    assert flags and flags[0]["text"] == "[EXAM DATE]"
