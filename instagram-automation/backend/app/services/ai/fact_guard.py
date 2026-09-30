"""Business-rule guard: AI must never invent prices, dates, claims, contacts...

After generation we scan the text for "risky" facts. Any risky fact that does
not appear in the verified sources (brand knowledge base + the human-written
post input) is flagged. Flagged posts can still be approved, but only after a
reviewer explicitly acknowledges the flags.

This is a safety net, not a guarantee - the human review step is the real
control, and the UI makes the flags impossible to miss.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("price", "Price / amount", re.compile(r"(?:₹|rs\.?|inr|\$|usd|€|£)\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:rupees|/-|lakhs?|crores?)", re.I)),
    ("percentage", "Percentage / statistic", re.compile(r"\d+(?:\.\d+)?\s?%|\d+(?:\.\d+)?\s?percent", re.I)),
    (
        "date",
        "Date",
        re.compile(
            rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}\b(?:,?\s+\d{{4}})?|\b{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?\b(?:,?\s+\d{{4}})?|\b\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}\b|\b20\d{{2}}-\d{{2}}-\d{{2}}\b",
            re.I,
        ),
    ),
    ("phone", "Phone number", re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){10,12}\b")),
    ("email", "Email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("url", "Link", re.compile(r"https?://\S+|www\.\S+", re.I)),
    ("discount", "Discount / offer", re.compile(r"\b(?:\d+\s?%\s?off|flat\s+\d+|discount|free\s+(?:class|course|trial|demo)|scholarship|offer\s+ends?)\b", re.I)),
    (
        "guarantee",
        "Guarantee / absolute claim",
        re.compile(r"\b(?:guarantee[ds]?|100\s?%|assured|sure[- ]shot|no\.?\s?1|number\s+one|#1|best\s+in|top\s+ranked|highest\s+results?)\b", re.I),
    ),
    ("statistic", "Numeric claim", re.compile(r"\b\d[\d,]*\+?\s+(?:students|selections|toppers|ranks?|years|learners|results|centres|centers|branches)\b", re.I)),
    ("testimonial", "Testimonial / quote", re.compile(r"[\"“][^\"”]{15,}[\"”]\s*[-–—]\s*\w+")),
]


@dataclass
class Flag:
    type: str
    label: str
    text: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"type": self.type, "label": self.label, "text": self.text, "message": self.message}


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[₹$€£,\s]|rs\.?|inr|usd", "", s)
    return s


def check_unverified_facts(generated_texts: list[str], verified_sources: list[str]) -> list[dict[str, str]]:
    """Return flags for risky facts in generated text that are absent from verified sources."""
    source_raw = "\n".join(s for s in verified_sources if s)
    source_norm = _norm(source_raw)
    flags: list[Flag] = []
    seen: set[tuple[str, str]] = set()
    for text in generated_texts:
        if not text:
            continue
        # Hashtags are not facts.
        text = re.sub(r"#\w+", "", text)
        for kind, label, pattern in RULES:
            for m in pattern.finditer(text):
                found = m.group(0).strip()
                if not found or (kind, found.lower()) in seen:
                    continue
                seen.add((kind, found.lower()))
                in_sources = found.lower() in source_raw.lower() or (_norm(found) and _norm(found) in source_norm)
                if in_sources:
                    continue
                flags.append(
                    Flag(
                        type=kind,
                        label=label,
                        text=found,
                        message=f"{label} '{found}' is not in the verified company facts or the post input. Verify or remove it.",
                    )
                )
    return [f.as_dict() for f in flags]


def placeholder_flags(texts: list[str]) -> list[dict[str, str]]:
    """Flag unfilled [PLACEHOLDER] markers the AI left for humans."""
    out = []
    for t in texts:
        for m in re.finditer(r"\[[A-Z][A-Z0-9 _/-]{2,40}\]", t or ""):
            out.append({"type": "placeholder", "label": "Placeholder", "text": m.group(0), "message": f"Replace {m.group(0)} with real information before publishing."})
    return out
