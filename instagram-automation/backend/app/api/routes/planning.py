"""Ideas, recurring schedules and competitor research."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import admin, approver, editor, rate_limit, viewer
from app.core.errors import ValidationFailed
from app.database.session import get_db
from app.models import Competitor, CompetitorObservation, ContentIdea, IdeaStatus, RecurringSchedule, StrategyInsight, User
from app.schemas.api import (
    AnalyzeIn,
    CompetitorIn,
    CompetitorOut,
    IdeaOut,
    IdeasGenerateIn,
    InsightOut,
    ObservationIn,
    ObservationOut,
    PostDetailOut,
    PostOut,
    ScheduleBase,
    ScheduleOut,
    SchedulePreviewIn,
)
from app.services.competitors import analysis
from app.services.content import ideas as ideas_service
from app.services.scheduling import planner
from app.services.scheduling.recurrence import RecurrenceRule, next_occurrences

router = APIRouter()


# ------------------------------------------------------------------- ideas
@router.get("/ideas", response_model=list[IdeaOut], tags=["ideas"])
def list_ideas(status: str | None = "new", _: User = Depends(viewer), db: Session = Depends(get_db)):
    stmt = select(ContentIdea).order_by(ContentIdea.id.desc()).limit(200)
    if status:
        stmt = stmt.where(ContentIdea.status == status)
    return db.scalars(stmt).all()


@router.post("/ideas/generate", response_model=list[IdeaOut], tags=["ideas"])
def generate_ideas(body: IdeasGenerateIn, _: User = Depends(editor), db: Session = Depends(get_db), __=Depends(rate_limit("generate", "generation_rate_limit_per_minute"))):
    return ideas_service.generate_ideas(db, count=body.count, theme=body.theme, target_audience=body.target_audience)


@router.post("/ideas/{idea_id}/convert", response_model=PostDetailOut, tags=["ideas"])
def convert_idea(idea_id: int, user: User = Depends(editor), db: Session = Depends(get_db)):
    idea = db.get(ContentIdea, idea_id)
    if idea is None:
        raise HTTPException(404, "Idea not found.")
    post = ideas_service.idea_to_post(db, idea, user_id=user.id)
    return PostDetailOut(**PostOut.from_post(post).model_dump(), events=list(post.events))


@router.post("/ideas/{idea_id}/dismiss", response_model=IdeaOut, tags=["ideas"])
def dismiss_idea(idea_id: int, _: User = Depends(editor), db: Session = Depends(get_db)):
    idea = db.get(ContentIdea, idea_id)
    if idea is None:
        raise HTTPException(404, "Idea not found.")
    idea.status = IdeaStatus.DISMISSED
    db.commit()
    return idea


# --------------------------------------------------------------- schedules
def _schedule_out(s: RecurringSchedule) -> ScheduleOut:
    out = ScheduleOut.model_validate(s)
    try:
        out.next_slots = next_occurrences(planner.rule_for(s), datetime.now(UTC), 5)
    except ValueError:
        out.next_slots = []
    return out


@router.get("/schedules", response_model=list[ScheduleOut], tags=["schedules"])
def list_schedules(_: User = Depends(viewer), db: Session = Depends(get_db)):
    return [_schedule_out(s) for s in db.scalars(select(RecurringSchedule).order_by(RecurringSchedule.id)).all()]


@router.post("/schedules/preview", response_model=list[datetime], tags=["schedules"])
def preview_schedule(body: SchedulePreviewIn, _: User = Depends(viewer)):
    """Show the next N slot times for a proposed rule (so users can check what 'every 4th day' means)."""
    try:
        rule = RecurrenceRule(body.start_date, body.interval_days, body.post_time, body.timezone, body.mode, body.end_date)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    start = datetime.combine(body.start_date, body.post_time).replace(tzinfo=UTC)
    from datetime import timedelta

    return next_occurrences(rule, min(start - timedelta(days=2), datetime.now(UTC)), body.count)


@router.post("/schedules", response_model=ScheduleOut, status_code=201, tags=["schedules"])
def create_schedule(body: ScheduleBase, user: User = Depends(approver), db: Session = Depends(get_db)):
    planner.validate_schedule_input(body.mode, body.interval_days, body.timezone)
    s = RecurringSchedule(**body.model_dump(), created_by_id=user.id)
    db.add(s)
    db.commit()
    planner.plan_schedule(db, s)
    return _schedule_out(s)


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut, tags=["schedules"])
def update_schedule(schedule_id: int, body: ScheduleBase, _: User = Depends(approver), db: Session = Depends(get_db)):
    s = db.get(RecurringSchedule, schedule_id)
    if s is None:
        raise HTTPException(404, "Schedule not found.")
    planner.validate_schedule_input(body.mode, body.interval_days, body.timezone)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    if s.is_active:
        planner.plan_schedule(db, s)
    return _schedule_out(s)


@router.delete("/schedules/{schedule_id}", status_code=204, tags=["schedules"])
def delete_schedule(schedule_id: int, _: User = Depends(approver), db: Session = Depends(get_db)):
    s = db.get(RecurringSchedule, schedule_id)
    if s is None:
        raise HTTPException(404, "Schedule not found.")
    db.delete(s)
    db.commit()


@router.post("/schedules/run", tags=["schedules"])
def run_planner(_: User = Depends(admin), db: Session = Depends(get_db)):
    """Run the planner + due content generation now (normally done by the worker)."""
    planned = planner.plan_all(db)
    result = planner.generate_due_content(db)
    return {"planned": planned, **result}


# ------------------------------------------------------------- competitors
@router.get("/competitors", response_model=list[CompetitorOut], tags=["competitors"])
def list_competitors(_: User = Depends(viewer), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(CompetitorObservation.competitor_id, func.count()).group_by(CompetitorObservation.competitor_id)).all())
    out = []
    for c in db.scalars(select(Competitor).order_by(Competitor.name)).all():
        item = CompetitorOut.model_validate(c)
        item.observation_count = counts.get(c.id, 0)
        out.append(item)
    return out


@router.post("/competitors", response_model=CompetitorOut, status_code=201, tags=["competitors"])
def create_competitor(body: CompetitorIn, _: User = Depends(editor), db: Session = Depends(get_db)):
    c = Competitor(**body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.put("/competitors/{cid}", response_model=CompetitorOut, tags=["competitors"])
def update_competitor(cid: int, body: CompetitorIn, _: User = Depends(editor), db: Session = Depends(get_db)):
    c = db.get(Competitor, cid)
    if c is None:
        raise HTTPException(404, "Competitor not found.")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return c


@router.delete("/competitors/{cid}", status_code=204, tags=["competitors"])
def delete_competitor(cid: int, _: User = Depends(approver), db: Session = Depends(get_db)):
    c = db.get(Competitor, cid)
    if c is None:
        raise HTTPException(404, "Competitor not found.")
    db.delete(c)
    db.commit()


@router.get("/competitors/{cid}/observations", response_model=list[ObservationOut], tags=["competitors"])
def list_observations(cid: int, _: User = Depends(viewer), db: Session = Depends(get_db)):
    return db.scalars(select(CompetitorObservation).where(CompetitorObservation.competitor_id == cid).order_by(CompetitorObservation.id.desc())).all()


@router.post("/competitors/{cid}/observations", response_model=ObservationOut, status_code=201, tags=["competitors"])
def add_observation(cid: int, body: ObservationIn, _: User = Depends(editor), db: Session = Depends(get_db)):
    if db.get(Competitor, cid) is None:
        raise HTTPException(404, "Competitor not found.")
    o = CompetitorObservation(competitor_id=cid, **body.model_dump())
    db.add(o)
    db.commit()
    return o


@router.delete("/observations/{oid}", status_code=204, tags=["competitors"])
def delete_observation(oid: int, _: User = Depends(editor), db: Session = Depends(get_db)):
    o = db.get(CompetitorObservation, oid)
    if o is None:
        raise HTTPException(404, "Observation not found.")
    db.delete(o)
    db.commit()


@router.post("/competitors/import", tags=["competitors"])
async def import_csv(file: UploadFile = File(...), _: User = Depends(editor), db: Session = Depends(get_db)):
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise ValidationFailed("CSV file is larger than 2 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationFailed("CSV must be UTF-8 encoded.") from exc
    return {"imported": analysis.import_observations_csv(db, text)}


@router.post("/competitors/analyze", response_model=InsightOut, tags=["competitors"])
def analyze(body: AnalyzeIn, user: User = Depends(editor), db: Session = Depends(get_db), __=Depends(rate_limit("generate", "generation_rate_limit_per_minute"))):
    return analysis.analyze(db, competitor_ids=body.competitor_ids, user_id=user.id)


@router.get("/insights", response_model=list[InsightOut], tags=["competitors"])
def list_insights(_: User = Depends(viewer), db: Session = Depends(get_db)):
    return db.scalars(select(StrategyInsight).order_by(StrategyInsight.id.desc()).limit(20)).all()


@router.post("/insights/{iid}/toggle", response_model=InsightOut, tags=["competitors"])
def toggle_insight(iid: int, _: User = Depends(editor), db: Session = Depends(get_db)):
    i = db.get(StrategyInsight, iid)
    if i is None:
        raise HTTPException(404, "Insight not found.")
    i.use_in_generation = not i.use_in_generation
    db.commit()
    return i
