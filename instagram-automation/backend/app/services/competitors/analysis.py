"""Compliant competitor research.

What this module does NOT do: scrape Instagram or websites, download competitor
images, or store competitor captions verbatim. Users record *observations*
(topic, format, a summary in their own words, visual style, CTA pattern) from
content they are permitted to view, or import them from a CSV. The AI turns
those notes into high-level strategy insights that feed ORIGINAL content.

(If the company later uses the Instagram API with Facebook Login, Meta's
official Business Discovery API can provide basic public metrics of other
business accounts; that could be added as another observation source.)
"""

from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import LLMError, ValidationFailed
from app.models import Competitor, CompetitorObservation, Post, StrategyInsight
from app.services.ai import prompts
from app.services.ai.factory import get_llm_provider
from app.services.ai.schemas import INSIGHTS_JSON_SCHEMA, CompetitorInsightsOut, parse_model
from app.services.content.audit import log_integration
from app.services.content.generation import brand_dict, get_brand

MAX_SUMMARY = 500  # keep summaries short: we store descriptions, not copies


def analyze(db: Session, *, competitor_ids: list[int] | None = None, user_id: int | None = None) -> StrategyInsight:
    stmt = select(CompetitorObservation).join(Competitor)
    if competitor_ids:
        stmt = stmt.where(CompetitorObservation.competitor_id.in_(competitor_ids))
    observations = db.scalars(stmt.order_by(CompetitorObservation.id.desc()).limit(300)).all()
    if not observations:
        raise ValidationFailed("Add at least one competitor observation before running the analysis.")
    obs_data = [
        {
            "competitor": o.competitor.name,
            "content_topic": o.content_topic,
            "content_type": o.content_type,
            "caption_summary": o.caption_summary[:MAX_SUMMARY],
            "visual_style": o.visual_style,
            "posting_frequency": o.posting_frequency,
            "observed_strategy": o.observed_strategy,
            "cta_used": o.cta_used,
            "engagement_notes": o.engagement_notes,
        }
        for o in observations
    ]
    ctx = {
        "brand": brand_dict(get_brand(db)),
        "observations": obs_data,
        "our_recent_topics": [t for t in db.scalars(select(Post.topic).order_by(Post.id.desc()).limit(40)) if t],
    }
    provider = get_llm_provider()
    try:
        result = provider.complete_json(
            task="competitor_analysis",
            system=prompts.insights_system_prompt(),
            user=prompts.insights_user_prompt(ctx),
            schema=INSIGHTS_JSON_SCHEMA,
            context=ctx,
        )
        parsed: CompetitorInsightsOut = parse_model(CompetitorInsightsOut, result.data)
    except LLMError as err:
        log_integration(db, "llm", f"Competitor analysis failed: {err.message}")
        db.commit()
        raise
    insight = StrategyInsight(
        insights=parsed.model_dump(),
        observation_count=len(observations),
        llm_provider=result.provider,
        llm_model=result.model,
        created_by_id=user_id,
    )
    db.add(insight)
    db.commit()
    return insight


CSV_COLUMNS = [
    "competitor",
    "content_topic",
    "content_type",
    "caption_summary",
    "visual_style",
    "posting_frequency",
    "observed_strategy",
    "cta_used",
    "engagement_notes",
    "source_url",
    "observed_on",
    "notes",
]


def import_observations_csv(db: Session, text: str) -> int:
    """Import observations from CSV with the columns in CSV_COLUMNS (header row required)."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "competitor" not in [f.strip().lower() for f in reader.fieldnames]:
        raise ValidationFailed(f"CSV must have a header row including 'competitor'. Supported columns: {', '.join(CSV_COLUMNS)}")
    count = 0
    cache: dict[str, Competitor] = {}
    for raw in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        name = row.get("competitor")
        if not name:
            continue
        comp = cache.get(name.lower())
        if comp is None:
            comp = db.scalars(select(Competitor).where(Competitor.name == name)).first()
            if comp is None:
                comp = Competitor(name=name)
                db.add(comp)
                db.flush()
            cache[name.lower()] = comp
        observed_on = None
        if row.get("observed_on"):
            try:
                observed_on = date.fromisoformat(row["observed_on"])
            except ValueError:
                observed_on = None
        db.add(
            CompetitorObservation(
                competitor_id=comp.id,
                content_topic=row.get("content_topic", "")[:500],
                content_type=row.get("content_type", "image")[:50] or "image",
                caption_summary=row.get("caption_summary", "")[:MAX_SUMMARY],
                visual_style=row.get("visual_style", ""),
                posting_frequency=row.get("posting_frequency", "")[:100],
                observed_strategy=row.get("observed_strategy", ""),
                cta_used=row.get("cta_used", "")[:500],
                engagement_notes=row.get("engagement_notes", ""),
                source_url=row.get("source_url", "")[:1024],
                observed_on=observed_on,
                notes=row.get("notes", ""),
            )
        )
        count += 1
    db.commit()
    return count
