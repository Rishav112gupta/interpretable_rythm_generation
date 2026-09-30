"""Deterministic mock LLM so the whole app works without any API key.

It builds content from the structured inputs only. Like the real providers it
is instructed to never invent facts, so when a category needs information
that was not supplied (e.g. an exam date) it reports it in
`missing_information` instead of making it up.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from app.core.errors import LLMError
from app.services.ai.base import LLMProvider, LLMResult

_OPENERS = [
    "Here's something worth your time today.",
    "Quick one for you!",
    "Let's talk about something that really matters.",
    "Save this post for later.",
]

_IDEA_BANK = [
    ("Exam preparation tips", "Five practical habits for the final weeks before an exam.", "EXAM", "Carousel"),
    ("Student mistake of the week", "One common mistake students make and how to avoid it.", "NORMAL", "Single image"),
    ("Myth vs fact", "Bust a popular study myth with a clear, simple explanation.", "NORMAL", "Carousel"),
    ("Quick educational tip", "A 30-second concept explainer on a frequently confused topic.", "CLASS_SPECIFIC", "Single image"),
    ("Success story", "Feature a real student story (requires consent and real details from the team).", "PROMOTIONAL", "Single image"),
    ("FAQ", "Answer the most common question the team receives this month.", "NORMAL", "Carousel"),
    ("Promotional post", "Highlight an upcoming program - details must come from the company knowledge base.", "PROMOTIONAL", "Single image"),
    ("Batch kickoff message", "Welcome message and first-week checklist for a new batch.", "BATCH", "Single image"),
    ("Important announcement template", "Clear, scannable announcement layout for schedule changes.", "IMPORTANT", "Single image"),
    ("Revision checklist", "A printable revision checklist students can save.", "EXAM", "Carousel"),
]


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z0-9]+", text) if len(w) > 2]


class MockLLMProvider(LLMProvider):
    name = "mock"
    model = "mock-llm-v1"

    def __init__(self, *, fail_times: int = 0, return_invalid: bool = False) -> None:
        self.fail_times = fail_times
        self.return_invalid = return_invalid
        self.calls = 0

    def complete_json(self, *, task, system, user, schema, context, max_tokens=4000) -> LLMResult:
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise LLMError("Mock LLM failure (simulated).", transient=True)
        if self.return_invalid:
            return LLMResult(data={"headline": ""}, provider=self.name, model=self.model, duration_ms=1)
        if task == "post":
            data = self._post(context)
        elif task == "ideas":
            data = self._ideas(context)
        elif task == "competitor_analysis":
            data = self._insights(context)
        else:
            raise LLMError(f"Mock provider does not support task '{task}'.")
        return LLMResult(data=data, provider=self.name, model=self.model, duration_ms=5)

    # ------------------------------------------------------------------ post
    def _post(self, c: dict[str, Any]) -> dict[str, Any]:
        topic = (c.get("topic") or "Our latest update").strip()
        audience = c.get("target_audience") or c.get("brand", {}).get("target_audience") or "our community"
        category = (c.get("category_key") or "NORMAL").upper()
        brand = c.get("brand", {})
        company = brand.get("company_name") or "our team"
        variant = int(c.get("variant", 0))
        seed = int(hashlib.sha256(f"{topic}{variant}".encode()).hexdigest(), 16)
        opener = _OPENERS[seed % len(_OPENERS)]
        important = (c.get("important_info") or "").strip()
        cta = (c.get("cta") or "").strip()
        missing: list[str] = []

        body = [opener, "", f"{topic} - this one is for {audience}."]
        if c.get("objective"):
            body.append(f"Why it matters: {c['objective'].strip()}")
        if important:
            body += ["", important]
        else:
            if category in {"EXAM", "IMPORTANT", "BATCH", "CLASS_SPECIFIC"}:
                missing.append(
                    {
                        "EXAM": "Exam name/date details were not provided - add them or confirm the post is general.",
                        "IMPORTANT": "The actual announcement details (what, when, who) were not provided.",
                        "BATCH": "Batch name, timing or start date were not provided.",
                        "CLASS_SPECIFIC": "Class/course name and specifics were not provided.",
                    }[category]
                )
            if category == "PROMOTIONAL":
                missing.append("Offer details (program, price, deadline) were not provided - no prices were included.")
        body += ["", f"Follow {company} for more practical tips like this."]
        if cta:
            body += ["", f"👉 {cta}"]
        else:
            missing.append("No call to action was provided.")

        base_tags = ["education", "students", "learning"]
        if category == "EXAM":
            base_tags += ["exampreparation", "studytips"]
        tags = list(dict.fromkeys(brand.get("default_hashtags", []) + [w.lower() for w in _words(topic)][:4] + base_tags))

        visual = brand.get("visual_style") or "clean, modern, friendly flat illustration"
        image_instr = c.get("image_instructions") or ""
        return {
            "headline": topic[:1].upper() + topic[1:80],
            "subtitle": f"For {audience}"[:200],
            "caption": "\n".join(body).strip(),
            "cta": cta,
            "hashtags": tags[:15],
            "image_prompt": f"{visual}. Illustration representing '{topic}' for {audience}. {image_instr} No text in the image.".strip(),
            "alternative_caption": f"{topic}: a quick note for {audience}. {('👉 ' + cta) if cta else ''}".strip(),
            "content_summary": f"{category.title()} post about {topic} aimed at {audience}.",
            "missing_information": missing,
        }

    # ----------------------------------------------------------------- ideas
    def _ideas(self, c: dict[str, Any]) -> dict[str, Any]:
        count = int(c.get("count", 7))
        theme = (c.get("theme") or "").strip()
        allowed = set(c.get("category_keys") or [])
        ideas = []
        for i in range(count):
            title, desc, cat, fmt = _IDEA_BANK[(i + int(c.get("variant", 0))) % len(_IDEA_BANK)]
            if allowed and cat not in allowed:
                cat = "RANDOM" if "RANDOM" in allowed else sorted(allowed)[0]
            if theme:
                title = f"{title}: {theme}"
            ideas.append({"title": title, "description": desc, "category_key": cat, "suggested_format": fmt, "target_audience": c.get("target_audience", "")})
        return {"ideas": ideas}

    # -------------------------------------------------------------- insights
    def _insights(self, c: dict[str, Any]) -> dict[str, Any]:
        obs: list[dict[str, Any]] = c.get("observations", [])
        topics = Counter(o.get("content_topic", "").strip() for o in obs if o.get("content_topic"))
        types = Counter(o.get("content_type", "").strip() for o in obs if o.get("content_type"))
        ctas = Counter(o.get("cta_used", "").strip() for o in obs if o.get("cta_used"))
        visuals = [o.get("visual_style", "") for o in obs if o.get("visual_style")]
        our = {t.lower() for t in c.get("our_recent_topics", [])}
        gaps = [t for t, _ in topics.most_common() if t.lower() not in our][:5]
        return {
            "summary": f"Analysed {len(obs)} observations across {len({o.get('competitor') for o in obs})} competitors.",
            "common_topics": [f"{t} ({n}x)" for t, n in topics.most_common(5)],
            "content_gaps": [f"Competitors cover '{g}' - consider an original take" for g in gaps],
            "recurring_themes": [f"{t} format used {n}x" for t, n in types.most_common(3)],
            "audience_targeting": sorted({o.get("observed_strategy", "") for o in obs if o.get("observed_strategy")})[:5],
            "cta_patterns": [f"{t} ({n}x)" for t, n in ctas.most_common(5)],
            "visual_trends": visuals[:5],
            "recommendations": [
                "Create original posts on the highest-frequency topics with your own expertise and examples.",
                "Never reuse competitor captions or imagery; use them only to understand what the audience responds to.",
            ],
        }
