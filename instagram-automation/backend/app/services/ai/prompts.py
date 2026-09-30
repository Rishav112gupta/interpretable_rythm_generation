"""Versioned prompt builders. Bump PROMPT_VERSION whenever the wording changes
so every post records which prompt produced it."""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "post-v1"
IDEAS_PROMPT_VERSION = "ideas-v1"
INSIGHTS_PROMPT_VERSION = "insights-v1"

FACT_RULES = """STRICT FACT RULES (these override everything else):
- Never invent prices, fees, discounts, dates, exam dates, deadlines, course details, company claims,
  guarantees, results, rankings, statistics, testimonials, names of people, phone numbers, emails,
  addresses or links.
- You may state such a fact ONLY if it appears verbatim in VERIFIED COMPANY FACTS or in the POST INPUT.
- If the post needs a fact that was not provided, write the post without it (or use a clear placeholder
  in square brackets such as [EXAM DATE]) and add a short note to `missing_information` explaining what a
  human must supply.
- Do not promise outcomes ("guaranteed selection", "100% results") unless that exact claim is a verified fact.
- Do not copy or closely paraphrase competitor content. Competitor insights describe patterns only."""


def _brand_block(brand: dict[str, Any]) -> str:
    keys = [
        "company_name",
        "description",
        "target_audience",
        "brand_voice",
        "tone",
        "words_to_use",
        "words_to_avoid",
        "cta_style",
        "hashtag_strategy",
        "default_hashtags",
        "visual_style",
        "content_restrictions",
        "website",
        "contact_info",
    ]
    lines = []
    for k in keys:
        v = brand.get(k)
        if v in (None, "", []):
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        lines.append(f"- {k.replace('_', ' ')}: {v}")
    return "\n".join(lines) or "- (brand profile not configured yet)"


def _facts_block(brand: dict[str, Any]) -> str:
    facts = brand.get("knowledge") or []
    lines = [f"- {f.get('label', '').strip()}: {f.get('value', '').strip()}" for f in facts if f.get("value")]
    return "\n".join(lines) or "- (none provided - do not state any specific facts, prices or dates)"


def post_system_prompt() -> str:
    return (
        "You are an expert Instagram content writer for a company. You write original, engaging, "
        "on-brand posts. Output only JSON matching the provided schema.\n\n" + FACT_RULES + "\n\n"
        "Field guidance:\n"
        "- headline: short text for the image, max ~8 words, no hashtags.\n"
        "- subtitle: optional supporting line for the image, max ~15 words.\n"
        "- caption: the Instagram caption WITHOUT hashtags (they go in `hashtags`), under 1,800 characters, "
        "with line breaks for readability and the CTA near the end.\n"
        "- cta: the call to action sentence.\n"
        "- hashtags: 8-20 relevant hashtags without the # sign, no spaces.\n"
        "- image_prompt: a detailed prompt for an image generator describing the visual only; the image must "
        "NOT contain any text, letters, logos or numbers (text is added later by our template).\n"
        "- alternative_caption: a shorter alternative caption with a different angle.\n"
        "- content_summary: one sentence describing the post for internal use.\n"
        "- missing_information: list of facts a human must supply or verify (empty list if none)."
    )


def post_user_prompt(ctx: dict[str, Any]) -> str:
    brand = ctx.get("brand", {})
    parts = [
        "BRAND PROFILE:",
        _brand_block(brand),
        "",
        "VERIFIED COMPANY FACTS (the only facts you may state):",
        _facts_block(brand),
        "",
        f"CATEGORY: {ctx.get('category_name') or ctx.get('category_key') or 'General'}",
    ]
    if ctx.get("category_guidance"):
        parts.append(f"CATEGORY GUIDANCE: {ctx['category_guidance']}")
    post_input = {
        k: ctx.get(k)
        for k in (
            "topic",
            "target_audience",
            "tone",
            "objective",
            "important_info",
            "cta",
            "language",
            "brand_instructions",
            "reference_material",
            "image_instructions",
        )
        if ctx.get(k)
    }
    parts += ["", "POST INPUT:", json.dumps(post_input, ensure_ascii=False, indent=2)]
    if ctx.get("insights"):
        parts += [
            "",
            "CONTENT STRATEGY INSIGHTS (high-level patterns from competitor research - use for strategy only, never copy):",
            json.dumps(ctx["insights"], ensure_ascii=False),
        ]
    if ctx.get("previous_headline"):
        parts += ["", f"This is a regeneration. Take a clearly different angle from the previous headline: {ctx['previous_headline']!r}"]
    if ctx.get("feedback"):
        parts += ["", f"REVIEWER FEEDBACK TO APPLY: {ctx['feedback']}"]
    parts += ["", f"Write the post in {ctx.get('language') or brand.get('default_language') or 'English'}."]
    return "\n".join(parts)


def ideas_system_prompt() -> str:
    return "You are a content strategist for a company's Instagram account. Generate varied, original post ideas. Output only JSON matching the schema.\n" + FACT_RULES


def ideas_user_prompt(ctx: dict[str, Any]) -> str:
    return "\n".join(
        [
            "BRAND PROFILE:",
            _brand_block(ctx.get("brand", {})),
            "",
            f"Available category keys: {', '.join(ctx.get('category_keys', []))}",
            f"Theme / focus (optional): {ctx.get('theme') or 'none'}",
            f"Target audience (optional): {ctx.get('target_audience') or 'use brand audience'}",
            f"Recent topics to avoid repeating: {', '.join(ctx.get('recent_topics', [])[:30]) or 'none'}",
            f"Strategy insights: {json.dumps(ctx.get('insights') or {}, ensure_ascii=False)}",
            "",
            f"Return exactly {ctx.get('count', 7)} ideas. Mix formats (tips, myth vs fact, FAQ, checklists, stories that "
            "need real details from the team, announcements). category_key must be one of the available keys.",
        ]
    )


def insights_system_prompt() -> str:
    return (
        "You analyse notes about competitors' Instagram content to produce HIGH-LEVEL strategy insights "
        "(topics, gaps, themes, audience targeting, CTA patterns, visual trends). Never reproduce competitor "
        "captions or wording; describe patterns in your own words. Recommendations must lead to ORIGINAL content. "
        "Output only JSON matching the schema."
    )


def insights_user_prompt(ctx: dict[str, Any]) -> str:
    return "\n".join(
        [
            "OUR BRAND:",
            _brand_block(ctx.get("brand", {})),
            "",
            f"OUR RECENT TOPICS: {', '.join(ctx.get('our_recent_topics', [])[:40]) or 'none'}",
            "",
            "COMPETITOR OBSERVATIONS (JSON):",
            json.dumps(ctx.get("observations", []), ensure_ascii=False, indent=1),
        ]
    )
